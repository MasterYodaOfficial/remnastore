from datetime import UTC, datetime
import tempfile
import unittest
import uuid
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_account
from app.core.config import settings
from app.db.base import Base
from app.db.models import (
    Account,
    AuthAccount,
    AuthLinkToken,
    AuthProvider,
    LinkType,
    Withdrawal,
    WithdrawalDestinationType,
    WithdrawalStatus,
)
from app.db.session import get_session
from app.main import create_app
from app.services import account_linking
from app.services.account_linking import create_telegram_link_token


class DummyCache:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def auth_token_account_key(self, access_token: str) -> str:
        return f"auth:{access_token}"

    def account_response_key(self, account_id: str) -> str:
        return f"account:{account_id}"

    async def get_str(self, key: str) -> str | None:
        return self._values.get(key)

    async def set_str(self, key: str, value: str, ttl_seconds: int) -> None:
        del ttl_seconds
        self._values[key] = value

    async def get_json(self, key: str):
        del key
        return None

    async def set_json(self, key: str, value, ttl_seconds: int) -> None:
        del key, value, ttl_seconds

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._values.pop(key, None)


class AccountLinkingFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "account-linking.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._current_account_id: uuid.UUID | None = None

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()

        self._original_webapp_url = settings.webapp_url
        self._original_bot_username = settings.telegram_bot_username
        settings.webapp_url = "https://webapp.test"
        settings.telegram_bot_username = "test_bot"

        self._original_utcnow = account_linking._utcnow
        account_linking._utcnow = lambda: datetime.now(UTC).replace(tzinfo=None)

        self.app = create_app()

        async def override_get_session():
            async with self._session_factory() as session:
                yield session

        async def override_get_current_account():
            if self._current_account_id is None:
                raise AssertionError("current account is not configured for test request")

            async with self._session_factory() as session:
                account = await session.get(Account, self._current_account_id)
                if account is None:
                    raise AssertionError(f"account not found: {self._current_account_id}")
                return account

        self.app.dependency_overrides[get_session] = override_get_session
        self.app.dependency_overrides[get_current_account] = override_get_current_account
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        settings.webapp_url = self._original_webapp_url
        settings.telegram_bot_username = self._original_bot_username
        account_linking._utcnow = self._original_utcnow
        self._cache_module._cache = self._original_cache
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
        email: str | None = None,
        display_name: str | None = None,
    ) -> AuthAccount:
        async with self._session_factory() as session:
            auth_account = AuthAccount(
                account_id=account_id,
                provider=provider,
                provider_uid=provider_uid,
                email=email,
                display_name=display_name,
            )
            session.add(auth_account)
            await session.commit()
            await session.refresh(auth_account)
            return auth_account

    async def _get_account(self, account_id: uuid.UUID) -> Account | None:
        async with self._session_factory() as session:
            return await session.get(Account, account_id)

    async def _get_link_token(self, link_token: str) -> AuthLinkToken | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AuthLinkToken).where(AuthLinkToken.link_token == link_token)
            )
            return result.scalar_one_or_none()

    async def _get_auth_accounts(self, account_id: uuid.UUID) -> list[AuthAccount]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AuthAccount).where(AuthAccount.account_id == account_id)
            )
            return list(result.scalars().all())

    async def _create_withdrawal(
        self,
        *,
        account_id: uuid.UUID,
        amount: int,
        destination_type: WithdrawalDestinationType = WithdrawalDestinationType.CARD,
        destination_value: str = "2200123412341234",
    ) -> Withdrawal:
        async with self._session_factory() as session:
            withdrawal = Withdrawal(
                account_id=account_id,
                amount=amount,
                destination_type=destination_type,
                destination_value=destination_value,
                status=WithdrawalStatus.NEW,
            )
            session.add(withdrawal)
            await session.commit()
            await session.refresh(withdrawal)
            return withdrawal

    async def _get_withdrawal(self, withdrawal_id: int) -> Withdrawal | None:
        async with self._session_factory() as session:
            return await session.get(Withdrawal, withdrawal_id)

    async def test_browser_to_telegram_flow_and_token_reuse(self) -> None:
        browser_account = await self._create_account(
            email="browser@example.com",
            display_name="Browser User",
            balance=15,
        )
        self._current_account_id = browser_account.id

        response = await self.client.post("/api/v1/accounts/link-telegram")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["expires_in_seconds"], 3600)
        self.assertEqual(body["link_url"], f"https://t.me/test_bot?start={body['link_token']}")

        token = await self._get_link_token(body["link_token"])
        self.assertIsNotNone(token)
        assert token is not None
        self.assertEqual(token.account_id, browser_account.id)
        self.assertEqual(token.link_type, LinkType.TELEGRAM_FROM_BROWSER)

        confirm_response = await self.client.post(
            "/api/v1/accounts/link-telegram-confirm",
            json={
                "link_token": body["link_token"],
                "telegram_id": 100500,
                "username": "linked_telegram",
                "first_name": "Telegram",
                "last_name": "User",
                "is_premium": True,
            },
        )
        self.assertEqual(confirm_response.status_code, 200)
        confirm_body = confirm_response.json()
        self.assertEqual(confirm_body["id"], str(browser_account.id))
        self.assertEqual(confirm_body["telegram_id"], 100500)
        self.assertEqual(confirm_body["username"], "linked_telegram")
        self.assertEqual(confirm_body["last_login_source"], "browser_oauth")

        stored_account = await self._get_account(browser_account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.telegram_id, 100500)
        self.assertEqual(stored_account.username, "linked_telegram")

        consumed_token = await self._get_link_token(body["link_token"])
        self.assertIsNotNone(consumed_token)
        assert consumed_token is not None
        self.assertIsNotNone(consumed_token.consumed_at)

        reused_response = await self.client.post(
            "/api/v1/accounts/link-telegram-confirm",
            json={
                "link_token": body["link_token"],
                "telegram_id": 100500,
            },
        )
        self.assertEqual(reused_response.status_code, 400)
        self.assertEqual(reused_response.json()["detail"], "Link token already used")

    async def test_browser_to_telegram_merges_existing_telegram_account(self) -> None:
        browser_account = await self._create_account(
            email="browser@example.com",
            display_name="Browser User",
            balance=11,
            referral_earnings=4,
        )
        telegram_account = await self._create_account(
            telegram_id=200200,
            first_name="Existing Telegram",
            balance=9,
            referral_earnings=6,
            referrals_count=3,
        )
        await self._create_auth_account(
            account_id=telegram_account.id,
            provider=AuthProvider.SUPABASE,
            provider_uid="telegram-existing",
        )
        pending_withdrawal = await self._create_withdrawal(account_id=telegram_account.id, amount=5)

        self._current_account_id = browser_account.id
        token_response = await self.client.post("/api/v1/accounts/link-telegram")
        self.assertEqual(token_response.status_code, 200)
        link_token = token_response.json()["link_token"]

        confirm_response = await self.client.post(
            "/api/v1/accounts/link-telegram-confirm",
            json={
                "link_token": link_token,
                "telegram_id": 200200,
                "username": "merged_account",
                "first_name": "Merged",
            },
        )
        self.assertEqual(confirm_response.status_code, 200)
        confirm_body = confirm_response.json()
        self.assertEqual(confirm_body["id"], str(browser_account.id))
        self.assertEqual(confirm_body["balance"], 20)
        self.assertEqual(confirm_body["referral_earnings"], 10)
        self.assertEqual(confirm_body["referrals_count"], 3)

        merged_account = await self._get_account(browser_account.id)
        self.assertIsNotNone(merged_account)
        assert merged_account is not None
        self.assertEqual(merged_account.balance, 20)
        self.assertEqual(merged_account.referral_earnings, 10)
        self.assertEqual(merged_account.referrals_count, 3)
        self.assertEqual(merged_account.telegram_id, 200200)

        removed_source_account = await self._get_account(telegram_account.id)
        self.assertIsNone(removed_source_account)

        auth_accounts = await self._get_auth_accounts(browser_account.id)
        self.assertEqual(len(auth_accounts), 1)
        self.assertEqual(auth_accounts[0].provider_uid, "telegram-existing")

        moved_withdrawal = await self._get_withdrawal(pending_withdrawal.id)
        self.assertIsNotNone(moved_withdrawal)
        assert moved_withdrawal is not None
        self.assertEqual(moved_withdrawal.account_id, browser_account.id)

    async def test_telegram_to_browser_flow_and_token_reuse(self) -> None:
        telegram_account = await self._create_account(
            telegram_id=300300,
            username="telegram_owner",
            first_name="Telegram",
            balance=12,
            referral_earnings=5,
            referrals_count=2,
        )
        browser_account = await self._create_account(
            email="browser@example.com",
            display_name="Browser User",
            balance=8,
            referral_earnings=1,
        )
        await self._create_auth_account(
            account_id=browser_account.id,
            provider=AuthProvider.SUPABASE,
            provider_uid="browser-user-1",
            email="browser@example.com",
        )

        self._current_account_id = telegram_account.id
        token_response = await self.client.post("/api/v1/accounts/link-browser")
        self.assertEqual(token_response.status_code, 200)
        token_body = token_response.json()
        self.assertIn("link_flow=browser", token_body["link_url"])
        self.assertTrue(token_body["link_token"].endswith("_BROWSER"))

        link_token = await self._get_link_token(token_body["link_token"])
        self.assertIsNotNone(link_token)
        assert link_token is not None
        self.assertEqual(link_token.link_type, LinkType.BROWSER_FROM_TELEGRAM)

        self._current_account_id = browser_account.id
        complete_response = await self.client.post(
            "/api/v1/accounts/link-browser-complete",
            headers={"Authorization": "Bearer browser-session-token"},
            json={"link_token": token_body["link_token"]},
        )
        self.assertEqual(complete_response.status_code, 200)
        complete_body = complete_response.json()
        self.assertEqual(complete_body["id"], str(telegram_account.id))
        self.assertEqual(complete_body["balance"], 20)
        self.assertEqual(complete_body["referral_earnings"], 6)
        self.assertEqual(complete_body["referrals_count"], 2)
        self.assertEqual(complete_body["last_login_source"], "browser_oauth")

        merged_telegram_account = await self._get_account(telegram_account.id)
        self.assertIsNotNone(merged_telegram_account)
        assert merged_telegram_account is not None
        self.assertEqual(merged_telegram_account.balance, 20)
        self.assertEqual(merged_telegram_account.referral_earnings, 6)

        removed_browser_account = await self._get_account(browser_account.id)
        self.assertIsNone(removed_browser_account)

        moved_auth_accounts = await self._get_auth_accounts(telegram_account.id)
        self.assertEqual(len(moved_auth_accounts), 1)
        self.assertEqual(moved_auth_accounts[0].provider_uid, "browser-user-1")

        consumed_token = await self._get_link_token(token_body["link_token"])
        self.assertIsNotNone(consumed_token)
        assert consumed_token is not None
        self.assertIsNotNone(consumed_token.consumed_at)

        self._current_account_id = telegram_account.id
        reused_response = await self.client.post(
            "/api/v1/accounts/link-browser-complete",
            headers={"Authorization": "Bearer browser-session-token"},
            json={"link_token": token_body["link_token"]},
        )
        self.assertEqual(reused_response.status_code, 400)
        self.assertEqual(reused_response.json()["detail"], "Link token already used")

    async def test_expired_link_token_is_rejected(self) -> None:
        browser_account = await self._create_account(email="browser@example.com")

        async with self._session_factory() as session:
            link_token, _ = await create_telegram_link_token(
                session,
                account_id=browser_account.id,
                ttl_seconds=-1,
            )
            await session.commit()

        expired_response = await self.client.post(
            "/api/v1/accounts/link-telegram-confirm",
            json={
                "link_token": link_token,
                "telegram_id": 404404,
            },
        )
        self.assertEqual(expired_response.status_code, 400)
        self.assertEqual(expired_response.json()["detail"], "Link token expired")


if __name__ == "__main__":
    unittest.main()
