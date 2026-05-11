import tempfile
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Account, AccountStatus, AuthAccount, AuthProvider, LoginSource
from app.integrations.supabase.models import SupabaseIdentity, SupabaseUser
from app.services.accounts import (
    AccountBlockedError,
    AccountIdentityConflictError,
    _build_supabase_identity_links,
    _identity_display_name,
    _map_supabase_identity_provider,
    get_account_by_id,
    mark_telegram_account_reachable,
    mark_telegram_bot_blocked,
    upsert_supabase_account,
    upsert_telegram_account,
)


class _DummySession:
    def __init__(self) -> None:
        self.rollback = AsyncMock()


class _DummyCache:
    def __init__(self) -> None:
        self.deleted_keys: list[tuple[str, ...]] = []

    def account_response_key(self, account_id: str) -> str:
        return f"account:{account_id}"

    async def delete(self, *keys: str) -> None:
        self.deleted_keys.append(keys)


class UpsertSupabaseAccountTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_on_auth_provider_unique_violation(self) -> None:
        session = _DummySession()
        expected_account = object()
        integrity_error = IntegrityError(
            "INSERT",
            {},
            Exception("uq_auth_provider_uid"),
        )

        with patch(
            "app.services.accounts._upsert_supabase_account_once",
            new=AsyncMock(side_effect=[integrity_error, expected_account]),
        ) as upsert_once:
            result = await upsert_supabase_account(session, supabase_user=object())

        self.assertIs(result, expected_account)
        session.rollback.assert_awaited_once()
        self.assertEqual(upsert_once.await_count, 2)

    async def test_raises_conflict_after_second_unique_violation(self) -> None:
        session = _DummySession()
        integrity_error = IntegrityError(
            "INSERT",
            {},
            Exception("uq_auth_provider_uid"),
        )

        with patch(
            "app.services.accounts._upsert_supabase_account_once",
            new=AsyncMock(side_effect=[integrity_error, integrity_error]),
        ):
            with self.assertRaises(AccountIdentityConflictError):
                await upsert_supabase_account(session, supabase_user=object())

        self.assertEqual(session.rollback.await_count, 2)


class AccountServiceFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "accounts.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._cache = _DummyCache()
        self._cache_patcher = patch(
            "app.services.accounts.get_cache", return_value=self._cache
        )
        self._cache_patcher.start()

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self) -> None:
        self._cache_patcher.stop()
        await self._engine.dispose()
        self._tmpdir.cleanup()

    async def _create_account(self, **values) -> Account:
        async with self._session_factory() as session:
            account = Account(**values)
            session.add(account)
            await session.commit()
            await session.refresh(account)
            return account

    async def _create_auth_account(
        self,
        *,
        account_id: uuid.UUID,
        provider: AuthProvider,
        provider_uid: str,
    ) -> AuthAccount:
        async with self._session_factory() as session:
            auth_account = AuthAccount(
                account_id=account_id,
                provider=provider,
                provider_uid=provider_uid,
            )
            session.add(auth_account)
            await session.commit()
            await session.refresh(auth_account)
            return auth_account

    async def test_get_account_by_id_returns_none_for_invalid_values(self) -> None:
        async with self._session_factory() as session:
            self.assertIsNone(await get_account_by_id(session, "not-a-uuid"))
            self.assertIsNone(await get_account_by_id(session, None))

    def test_supabase_identity_helpers_cover_mapping_links_and_names(self) -> None:
        self.assertEqual(
            _map_supabase_identity_provider(" Google "),
            AuthProvider.GOOGLE,
        )
        self.assertEqual(
            _map_supabase_identity_provider("YANDEX"),
            AuthProvider.YANDEX,
        )
        self.assertIsNone(_map_supabase_identity_provider("vk"))
        self.assertIsNone(_map_supabase_identity_provider(None))

        supabase_user = SupabaseUser(
            id="supabase-user",
            user_metadata={"display_name": "User Display"},
            identities=[
                SupabaseIdentity(
                    provider="google",
                    identity_data={"sub": "google-user"},
                ),
                SupabaseIdentity(
                    provider="google",
                    identity_data={"sub": "google-user"},
                ),
                SupabaseIdentity(
                    provider="yandex",
                    identity_data={"provider_id": "yandex-user"},
                ),
                SupabaseIdentity(
                    provider="vk",
                    identity_data={"sub": "vk-user"},
                ),
            ],
        )

        self.assertEqual(
            _build_supabase_identity_links(supabase_user),
            [
                (AuthProvider.SUPABASE, "supabase-user"),
                (AuthProvider.GOOGLE, "google-user"),
                (AuthProvider.YANDEX, "yandex-user"),
            ],
        )
        self.assertEqual(_identity_display_name(supabase_user), "User Display")
        self.assertEqual(
            _identity_display_name(
                SupabaseUser(
                    id="supabase-user",
                    identities=[],
                ),
                SupabaseIdentity(
                    provider="google",
                    identity_data={"full_name": "Identity Name"},
                ),
            ),
            "Identity Name",
        )

    async def test_upsert_supabase_account_creates_account_and_auth_links(self) -> None:
        supabase_user = SupabaseUser(
            id="supabase-user",
            email="user@example.com",
            user_metadata={"display_name": "User Name", "locale": "ru"},
            identities=[
                SupabaseIdentity(
                    provider="google",
                    identity_data={"sub": "google-user"},
                )
            ],
        )

        async with self._session_factory() as session:
            account = await upsert_supabase_account(
                session, supabase_user=supabase_user
            )

        self.assertEqual(account.email, "user@example.com")
        self.assertEqual(account.display_name, "User Name")
        self.assertEqual(account.locale, "ru")
        self.assertEqual(account.last_login_source, LoginSource.BROWSER_OAUTH)
        self.assertTrue(
            account.referral_code and account.referral_code.startswith("ref-")
        )
        self.assertEqual(self._cache.deleted_keys, [(f"account:{account.id}",)])

        async with self._session_factory() as session:
            auth_links = (
                await session.execute(
                    AuthAccount.__table__.select().where(
                        AuthAccount.account_id == account.id
                    )
                )
            ).all()

        self.assertEqual(len(auth_links), 2)

    async def test_upsert_supabase_account_reuses_confirmed_email_account(self) -> None:
        existing_account = await self._create_account(
            email="existing@example.com",
            display_name="Old Name",
            status=AccountStatus.ACTIVE,
        )
        supabase_user = SupabaseUser(
            id="supabase-user",
            email="existing@example.com",
            email_confirmed_at=datetime.now(UTC),
            user_metadata={"display_name": "New Name"},
            identities=[
                SupabaseIdentity(
                    provider="google",
                    identity_data={"sub": "google-user"},
                )
            ],
        )

        async with self._session_factory() as session:
            account = await upsert_supabase_account(
                session, supabase_user=supabase_user
            )

        self.assertEqual(account.id, existing_account.id)
        self.assertEqual(account.display_name, "New Name")

    async def test_upsert_supabase_account_detects_conflicting_identity_links(
        self,
    ) -> None:
        first_account = await self._create_account(email="first@example.com")
        second_account = await self._create_account(email="second@example.com")
        await self._create_auth_account(
            account_id=first_account.id,
            provider=AuthProvider.SUPABASE,
            provider_uid="supabase-user",
        )
        await self._create_auth_account(
            account_id=second_account.id,
            provider=AuthProvider.GOOGLE,
            provider_uid="google-user",
        )

        supabase_user = SupabaseUser(
            id="supabase-user",
            email="user@example.com",
            identities=[
                SupabaseIdentity(
                    provider="google",
                    identity_data={"sub": "google-user"},
                )
            ],
        )

        async with self._session_factory() as session:
            with self.assertRaises(AccountIdentityConflictError):
                await upsert_supabase_account(session, supabase_user=supabase_user)

    async def test_mark_telegram_bot_blocked_marks_once_and_invalidates_cache(
        self,
    ) -> None:
        async with self._session_factory() as session:
            account = Account(telegram_id=100500)
            session.add(account)
            await session.commit()
            await session.refresh(account)

            await mark_telegram_bot_blocked(session, account=account)
            blocked_at = account.telegram_bot_blocked_at
            self.assertIsNotNone(blocked_at)

            await mark_telegram_bot_blocked(session, account=account)
            self.assertEqual(account.telegram_bot_blocked_at, blocked_at)

        self.assertEqual(self._cache.deleted_keys, [(f"account:{account.id}",)])

    async def test_mark_telegram_account_reachable_updates_existing_account(
        self,
    ) -> None:
        account = await self._create_account(
            telegram_id=42,
            telegram_bot_blocked_at=datetime.now(UTC),
        )

        async with self._session_factory() as session:
            updated = await mark_telegram_account_reachable(session, telegram_id=42)
            self.assertIsNotNone(updated)
            assert updated is not None
            self.assertIsNone(updated.telegram_bot_blocked_at)
            self.assertIsNotNone(updated.last_seen_at)

        async with self._session_factory() as session:
            self.assertIsNone(
                await mark_telegram_account_reachable(session, telegram_id=999999)
            )

        self.assertEqual(self._cache.deleted_keys, [(f"account:{account.id}",)])

    async def test_upsert_telegram_account_creates_and_updates_records(self) -> None:
        async with self._session_factory() as session:
            account = await upsert_telegram_account(
                session,
                telegram_id=777000111,
                username="first-user",
                first_name="First",
                last_name="User",
                is_premium=True,
                locale="ru",
                email="user@example.com",
                display_name="First User",
                last_login_source=LoginSource.TELEGRAM_WEBAPP,
            )

        self.assertEqual(account.telegram_id, 777000111)
        self.assertTrue(
            account.referral_code and account.referral_code.startswith("ref-")
        )
        self.assertEqual(account.last_login_source, LoginSource.TELEGRAM_WEBAPP)

        async with self._session_factory() as session:
            stored_account = await session.get(Account, account.id)
            assert stored_account is not None
            stored_account.telegram_bot_blocked_at = datetime.now(UTC)
            await session.commit()

        async with self._session_factory() as session:
            updated = await upsert_telegram_account(
                session,
                telegram_id=777000111,
                username=None,
                first_name=None,
                last_name="Updated",
                is_premium=False,
                locale=None,
                email=None,
                display_name=None,
                last_login_source=LoginSource.TELEGRAM_BOT_START,
            )

        self.assertEqual(updated.id, account.id)
        self.assertEqual(updated.username, "first-user")
        self.assertEqual(updated.last_name, "Updated")
        self.assertTrue(updated.is_premium)
        self.assertIsNone(updated.telegram_bot_blocked_at)
        self.assertEqual(updated.last_login_source, LoginSource.TELEGRAM_BOT_START)

    async def test_upsert_telegram_account_rejects_blocked_accounts(self) -> None:
        await self._create_account(
            telegram_id=123456,
            status=AccountStatus.BLOCKED,
        )

        async with self._session_factory() as session:
            with self.assertRaises(AccountBlockedError):
                await upsert_telegram_account(
                    session,
                    telegram_id=123456,
                    username="blocked-user",
                    first_name="Blocked",
                    last_name="User",
                    is_premium=False,
                    locale="ru",
                    email=None,
                    display_name=None,
                    last_login_source=LoginSource.TELEGRAM_WEBAPP,
                )
