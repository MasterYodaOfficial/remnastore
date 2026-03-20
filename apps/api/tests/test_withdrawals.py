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
    AccountEventLog,
    LedgerEntry,
    LedgerEntryType,
    Notification,
    NotificationType,
    Withdrawal,
)
from app.db.session import get_session
from app.main import create_app
from app.services.i18n import translate


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


class WithdrawalFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "withdrawals.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._current_account_id: uuid.UUID | None = None

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()

        self._original_min_withdrawal_amount_rub = settings.min_withdrawal_amount_rub
        settings.min_withdrawal_amount_rub = 30

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
        settings.min_withdrawal_amount_rub = self._original_min_withdrawal_amount_rub
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

    async def _get_withdrawals(self, account_id: uuid.UUID) -> list[Withdrawal]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Withdrawal)
                .where(Withdrawal.account_id == account_id)
                .order_by(Withdrawal.id.asc())
            )
            return list(result.scalars().all())

    async def _get_ledger_entries(self, account_id: uuid.UUID) -> list[LedgerEntry]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(LedgerEntry)
                .where(LedgerEntry.account_id == account_id)
                .order_by(LedgerEntry.id.asc())
            )
            return list(result.scalars().all())

    async def _get_notifications(self, account_id: uuid.UUID) -> list[Notification]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Notification)
                .where(Notification.account_id == account_id)
                .order_by(Notification.id.asc())
            )
            return list(result.scalars().all())

    async def _get_account_event_logs(
        self, account_id: uuid.UUID
    ) -> list[AccountEventLog]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AccountEventLog)
                .where(AccountEventLog.account_id == account_id)
                .order_by(AccountEventLog.id.asc())
            )
            return list(result.scalars().all())

    async def test_create_withdrawal_reserves_balance_and_updates_summary(self) -> None:
        account = await self._create_account(
            balance=90, referral_earnings=90, referral_code="withdraw-ref"
        )
        self._current_account_id = account.id

        response = await self.client.post(
            "/api/v1/withdrawals",
            json={
                "amount": 40,
                "destination_type": "sbp",
                "destination_value": "+79990000000",
                "user_comment": "Основная карта",
            },
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["amount"], 40)
        self.assertEqual(body["status"], "new")
        self.assertEqual(body["destination_type"], "sbp")
        self.assertEqual(body["destination_value"], "+7••••00")
        self.assertIsNotNone(body["reserved_ledger_entry_id"])

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 50)
        self.assertEqual(stored_account.referral_earnings, 90)

        withdrawals = await self._get_withdrawals(account.id)
        self.assertEqual(len(withdrawals), 1)
        self.assertEqual(
            withdrawals[0].reserved_ledger_entry_id, body["reserved_ledger_entry_id"]
        )

        ledger_entries = await self._get_ledger_entries(account.id)
        self.assertEqual(len(ledger_entries), 1)
        self.assertEqual(
            ledger_entries[0].entry_type, LedgerEntryType.WITHDRAWAL_RESERVE
        )
        self.assertEqual(ledger_entries[0].amount, -40)

        notifications = await self._get_notifications(account.id)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].type, NotificationType.WITHDRAWAL_CREATED)
        self.assertEqual(notifications[0].payload["withdrawal_id"], body["id"])

        event_logs = await self._get_account_event_logs(account.id)
        self.assertEqual(
            [item.event_type for item in event_logs], ["withdrawal.created"]
        )
        self.assertEqual(event_logs[0].payload["withdrawal_id"], body["id"])
        self.assertEqual(event_logs[0].payload["destination_value"], "+7••••00")

        summary_response = await self.client.get("/api/v1/referrals/summary")
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.json()["available_for_withdraw"], 50)

    async def test_create_withdrawal_rejects_below_minimum_amount(self) -> None:
        account = await self._create_account(balance=100, referral_earnings=100)
        self._current_account_id = account.id

        response = await self.client.post(
            "/api/v1/withdrawals",
            json={
                "amount": 20,
                "destination_type": "card",
                "destination_value": "4242 4242 4242 4242",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            translate("api.withdrawals.errors.minimum_amount", amount=30),
        )
        self.assertEqual(response.json()["error_code"], "minimum_amount")
        self.assertEqual(response.json()["error_params"], {"amount": 30})

    async def test_create_withdrawal_rejects_when_referral_availability_is_lower_than_balance(
        self,
    ) -> None:
        account = await self._create_account(balance=200, referral_earnings=35)
        self._current_account_id = account.id

        response = await self.client.post(
            "/api/v1/withdrawals",
            json={
                "amount": 40,
                "destination_type": "card",
                "destination_value": "4242 4242 4242 4242",
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            translate("api.withdrawals.errors.insufficient_available"),
        )
        self.assertEqual(response.json()["error_code"], "insufficient_available")

    async def test_create_withdrawal_rejects_invalid_card_number(self) -> None:
        account = await self._create_account(balance=120, referral_earnings=120)
        self._current_account_id = account.id

        response = await self.client.post(
            "/api/v1/withdrawals",
            json={
                "amount": 40,
                "destination_type": "card",
                "destination_value": "4242 4242 4242 4241",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            translate("api.withdrawals.errors.invalid_card"),
        )
        self.assertEqual(response.json()["error_code"], "invalid_card")

    async def test_list_withdrawals_returns_newest_first_with_availability(
        self,
    ) -> None:
        account = await self._create_account(balance=120, referral_earnings=120)
        self._current_account_id = account.id

        first_response = await self.client.post(
            "/api/v1/withdrawals",
            json={
                "amount": 30,
                "destination_type": "card",
                "destination_value": "4242 4242 4242 4242",
            },
        )
        self.assertEqual(first_response.status_code, 201)

        second_response = await self.client.post(
            "/api/v1/withdrawals",
            json={
                "amount": 40,
                "destination_type": "sbp",
                "destination_value": "+79995554433",
            },
        )
        self.assertEqual(second_response.status_code, 201)

        response = await self.client.get("/api/v1/withdrawals?limit=10&offset=0")
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["total"], 2)
        self.assertEqual(body["available_for_withdraw"], 50)
        self.assertEqual(body["minimum_amount_rub"], 30)
        self.assertEqual(body["items"][0]["amount"], 40)
        self.assertEqual(body["items"][1]["amount"], 30)
        self.assertEqual(body["items"][1]["destination_value"], "**** **** **** 4242")


if __name__ == "__main__":
    unittest.main()
