import tempfile
import unittest
import uuid
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_account
from app.db.base import Base
from app.db.models import Account, LedgerEntry, LedgerEntryType, LoginSource
from app.db.session import get_session
from app.main import create_app
from app.services.account_linking import merge_accounts
from app.services.ledger import (
    InsufficientFundsError,
    LedgerCommentRequiredError,
    admin_adjust_balance,
    credit_balance,
    debit_balance,
)


class DummyCache:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def account_response_key(self, account_id: str) -> str:
        return f"account:{account_id}"

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._values.pop(key, None)


class LedgerFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "ledger.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._current_account_id: uuid.UUID | None = None

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()

        self.app = create_app()

        async def override_get_session():
            async with self._session_factory() as session:
                yield session

        async def override_get_current_account():
            if self._current_account_id is None:
                raise AssertionError(
                    "current account is not configured for test request"
                )

            async with self._session_factory() as session:
                account = await session.get(Account, self._current_account_id)
                if account is None:
                    raise AssertionError(
                        f"account not found: {self._current_account_id}"
                    )
                return account

        self.app.dependency_overrides[get_session] = override_get_session
        self.app.dependency_overrides[get_current_account] = (
            override_get_current_account
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.dependency_overrides.clear()
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

    async def _get_account(self, account_id: uuid.UUID) -> Account | None:
        async with self._session_factory() as session:
            return await session.get(Account, account_id)

    async def _get_entries(self, account_id: uuid.UUID) -> list[LedgerEntry]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(LedgerEntry)
                .where(LedgerEntry.account_id == account_id)
                .order_by(LedgerEntry.id.asc())
            )
            return list(result.scalars().all())

    async def test_credit_balance_updates_snapshot_and_creates_entry(self) -> None:
        account = await self._create_account(balance=10)

        async with self._session_factory() as session:
            entry = await credit_balance(
                session,
                account_id=account.id,
                amount=7,
                entry_type=LedgerEntryType.TOPUP_MANUAL,
                reference_type="manual_topup",
                reference_id="topup-1",
            )

        self.assertEqual(entry.amount, 7)
        self.assertEqual(entry.balance_before, 10)
        self.assertEqual(entry.balance_after, 17)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 17)

    async def test_debit_balance_rejects_insufficient_funds(self) -> None:
        account = await self._create_account(balance=5)

        async with self._session_factory() as session:
            with self.assertRaises(InsufficientFundsError):
                await debit_balance(
                    session,
                    account_id=account.id,
                    amount=10,
                    entry_type=LedgerEntryType.SUBSCRIPTION_DEBIT,
                    reference_type="subscription_purchase",
                    reference_id="plan-1",
                )

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 5)
        self.assertEqual(await self._get_entries(account.id), [])

    async def test_credit_balance_is_idempotent(self) -> None:
        account = await self._create_account(balance=0)

        async with self._session_factory() as session:
            first = await credit_balance(
                session,
                account_id=account.id,
                amount=15,
                entry_type=LedgerEntryType.TOPUP_PAYMENT,
                reference_type="payment",
                reference_id="payment-1",
                idempotency_key="payment-1-credit",
            )

        async with self._session_factory() as session:
            second = await credit_balance(
                session,
                account_id=account.id,
                amount=15,
                entry_type=LedgerEntryType.TOPUP_PAYMENT,
                reference_type="payment",
                reference_id="payment-1",
                idempotency_key="payment-1-credit",
            )

        self.assertEqual(first.id, second.id)
        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 15)
        self.assertEqual(len(await self._get_entries(account.id)), 1)

    async def test_admin_adjust_balance_requires_comment(self) -> None:
        account = await self._create_account(balance=10)

        async with self._session_factory() as session:
            with self.assertRaises(LedgerCommentRequiredError):
                await admin_adjust_balance(
                    session,
                    account_id=account.id,
                    amount=5,
                    admin_id=uuid.uuid4(),
                    comment="   ",
                )

    async def test_ledger_history_endpoint_returns_newest_first(self) -> None:
        account = await self._create_account(balance=20)
        self._current_account_id = account.id

        async with self._session_factory() as session:
            await credit_balance(
                session,
                account_id=account.id,
                amount=5,
                entry_type=LedgerEntryType.TOPUP_MANUAL,
                reference_type="manual_topup",
                reference_id="topup-2",
            )

        async with self._session_factory() as session:
            await debit_balance(
                session,
                account_id=account.id,
                amount=8,
                entry_type=LedgerEntryType.SUBSCRIPTION_DEBIT,
                reference_type="subscription_purchase",
                reference_id="purchase-1",
            )

        response = await self.client.get("/api/v1/ledger/entries?limit=10&offset=0")
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["total"], 2)
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual(body["items"][0]["entry_type"], "subscription_debit")
        self.assertEqual(body["items"][1]["entry_type"], "topup_manual")

    async def test_merge_accounts_moves_balance_through_ledger_entries(self) -> None:
        source_account = await self._create_account(
            balance=12, referral_code="ref-source"
        )
        target_account = await self._create_account(
            balance=8, referral_code="ref-target"
        )

        async with self._session_factory() as session:
            merged_account = await merge_accounts(
                session,
                source_account_id=source_account.id,
                target_account_id=target_account.id,
                last_login_source=LoginSource.BROWSER_OAUTH,
            )
            await session.commit()
            await session.refresh(merged_account)

        self.assertEqual(merged_account.balance, 20)
        self.assertIsNone(await self._get_account(source_account.id))

        async with self._session_factory() as session:
            result = await session.execute(
                select(LedgerEntry)
                .where(LedgerEntry.reference_type == "account_merge")
                .order_by(LedgerEntry.id.asc())
            )
            merge_entries = list(result.scalars().all())

        self.assertEqual(len(merge_entries), 2)
        self.assertEqual([entry.amount for entry in merge_entries], [-12, 12])
        self.assertEqual(
            {entry.entry_type for entry in merge_entries},
            {LedgerEntryType.MERGE_DEBIT, LedgerEntryType.MERGE_CREDIT},
        )
