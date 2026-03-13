from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.db.models import (
    Account,
    AdminActionLog,
    LedgerEntry,
    LedgerEntryType,
    Notification,
    NotificationType,
    Withdrawal,
    WithdrawalDestinationType,
    WithdrawalStatus,
)
from app.db.session import get_session
from app.main import create_app
from app.services.admin_auth import create_admin
from app.services.withdrawals import create_withdrawal_request


class DummyCache:
    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def account_response_key(self, account_id: str) -> str:
        return f"account:{account_id}"

    async def delete(self, *keys: str) -> None:
        return None


class AdminWithdrawalEndpointsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "admin-withdrawals.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module
        import app.services.admin_auth as admin_auth_service

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()

        self._admin_auth_service = admin_auth_service
        self._original_bootstrap_username = admin_auth_service.settings.admin_bootstrap_username
        self._original_bootstrap_password = admin_auth_service.settings.admin_bootstrap_password
        self._original_bootstrap_email = admin_auth_service.settings.admin_bootstrap_email
        self._original_bootstrap_full_name = admin_auth_service.settings.admin_bootstrap_full_name
        admin_auth_service.settings.admin_bootstrap_username = ""
        admin_auth_service.settings.admin_bootstrap_password = ""
        admin_auth_service.settings.admin_bootstrap_email = ""
        admin_auth_service.settings.admin_bootstrap_full_name = ""

        self._original_min_withdrawal_amount_rub = settings.min_withdrawal_amount_rub
        settings.min_withdrawal_amount_rub = 30

        self.app = create_app()

        async def override_get_session():
            async with self._session_factory() as session:
                yield session

        self.app.dependency_overrides[get_session] = override_get_session
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        self._cache_module._cache = self._original_cache
        self._admin_auth_service.settings.admin_bootstrap_username = self._original_bootstrap_username
        self._admin_auth_service.settings.admin_bootstrap_password = self._original_bootstrap_password
        self._admin_auth_service.settings.admin_bootstrap_email = self._original_bootstrap_email
        self._admin_auth_service.settings.admin_bootstrap_full_name = self._original_bootstrap_full_name
        settings.min_withdrawal_amount_rub = self._original_min_withdrawal_amount_rub
        await self._engine.dispose()
        self._tmpdir.cleanup()

    async def _create_admin_token(self) -> str:
        async with self._session_factory() as session:
            admin = await create_admin(
                session,
                username="root",
                password="secret-password",
                email="root@example.com",
                full_name="Root Admin",
            )
            await session.commit()
            await session.refresh(admin)

        response = await self.client.post(
            "/api/v1/admin/auth/login",
            json={"login": "root", "password": "secret-password"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    async def _create_account(self, **values) -> Account:
        async with self._session_factory() as session:
            account = Account(**values)
            session.add(account)
            await session.commit()
            await session.refresh(account)
            return account

    async def _create_withdrawal(
        self,
        *,
        account_id: uuid.UUID,
        amount: int,
        destination_type: WithdrawalDestinationType = WithdrawalDestinationType.SBP,
        destination_value: str = "+79990000000",
        user_comment: str | None = None,
    ) -> Withdrawal:
        async with self._session_factory() as session:
            withdrawal = await create_withdrawal_request(
                session,
                account_id=account_id,
                amount=amount,
                destination_type=destination_type,
                destination_value=destination_value,
                user_comment=user_comment,
            )
            await session.commit()
            await session.refresh(withdrawal)
            return withdrawal

    async def _get_account(self, account_id: uuid.UUID) -> Account | None:
        async with self._session_factory() as session:
            return await session.get(Account, account_id)

    async def _get_withdrawal(self, withdrawal_id: int) -> Withdrawal | None:
        async with self._session_factory() as session:
            return await session.get(Withdrawal, withdrawal_id)

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

    async def test_list_admin_withdrawals_returns_pending_queue(self) -> None:
        token = await self._create_admin_token()
        first_account = await self._create_account(
            email="queue-first@example.com",
            display_name="Queue First",
            balance=120,
            referral_earnings=120,
            telegram_id=700100200,
        )
        second_account = await self._create_account(
            email="queue-second@example.com",
            username="queue_second",
            balance=160,
            referral_earnings=160,
        )
        first_withdrawal = await self._create_withdrawal(account_id=first_account.id, amount=40)
        second_withdrawal = await self._create_withdrawal(account_id=second_account.id, amount=60)

        async with self._session_factory() as session:
            stored_second = await session.get(Withdrawal, second_withdrawal.id)
            assert stored_second is not None
            stored_second.status = WithdrawalStatus.IN_PROGRESS
            await session.commit()

        response = await self.client.get(
            "/api/v1/admin/withdrawals",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual([item["id"] for item in body["items"]], [first_withdrawal.id, second_withdrawal.id])
        self.assertEqual(body["items"][0]["account_email"], "queue-first@example.com")
        self.assertEqual(body["items"][1]["status"], WithdrawalStatus.IN_PROGRESS.value)

    async def test_reject_withdrawal_releases_reserve_and_is_idempotent(self) -> None:
        token = await self._create_admin_token()
        account = await self._create_account(
            email="reject-withdraw@example.com",
            balance=100,
            referral_earnings=100,
        )
        withdrawal = await self._create_withdrawal(
            account_id=account.id,
            amount=40,
            user_comment="Верните на карту",
        )

        payload = {
            "status": WithdrawalStatus.REJECTED.value,
            "comment": "Реквизиты не прошли проверку",
            "idempotency_key": "admin-withdrawal-reject-1",
        }

        response = await self.client.post(
            f"/api/v1/admin/withdrawals/{withdrawal.id}/status",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["withdrawal_id"], withdrawal.id)
        self.assertEqual(body["previous_status"], WithdrawalStatus.NEW.value)
        self.assertEqual(body["status"], WithdrawalStatus.REJECTED.value)
        self.assertIsNotNone(body["released_ledger_entry_id"])

        duplicate_response = await self.client.post(
            f"/api/v1/admin/withdrawals/{withdrawal.id}/status",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(duplicate_response.status_code, 200)
        duplicate_body = duplicate_response.json()
        self.assertEqual(duplicate_body["audit_log_id"], body["audit_log_id"])
        self.assertEqual(duplicate_body["released_ledger_entry_id"], body["released_ledger_entry_id"])

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 100)

        stored_withdrawal = await self._get_withdrawal(withdrawal.id)
        self.assertIsNotNone(stored_withdrawal)
        assert stored_withdrawal is not None
        self.assertEqual(stored_withdrawal.status, WithdrawalStatus.REJECTED)
        self.assertEqual(stored_withdrawal.admin_comment, "Реквизиты не прошли проверку")

        ledger_entries = await self._get_ledger_entries(account.id)
        self.assertEqual([entry.entry_type for entry in ledger_entries], [
            LedgerEntryType.WITHDRAWAL_RESERVE,
            LedgerEntryType.WITHDRAWAL_RELEASE,
        ])
        self.assertEqual(ledger_entries[1].amount, 40)

        notifications = await self._get_notifications(account.id)
        self.assertEqual([notification.type for notification in notifications], [
            NotificationType.WITHDRAWAL_CREATED,
            NotificationType.WITHDRAWAL_REJECTED,
        ])

        async with self._session_factory() as session:
            audit_logs = list(
                (
                    await session.execute(
                        select(AdminActionLog).where(AdminActionLog.target_account_id == account.id)
                    )
                ).scalars()
            )
            self.assertEqual(len(audit_logs), 1)

    async def test_mark_withdrawal_paid_updates_status_and_keeps_reserved_balance(self) -> None:
        token = await self._create_admin_token()
        account = await self._create_account(
            email="paid-withdraw@example.com",
            balance=100,
            referral_earnings=100,
        )
        withdrawal = await self._create_withdrawal(
            account_id=account.id,
            amount=40,
            user_comment="Выплатить на СБП",
        )

        response = await self.client.post(
            f"/api/v1/admin/withdrawals/{withdrawal.id}/status",
            json={
                "status": WithdrawalStatus.PAID.value,
                "comment": "Выплачено вручную через банк",
                "idempotency_key": "admin-withdrawal-paid-1",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], WithdrawalStatus.PAID.value)
        self.assertIsNone(body["released_ledger_entry_id"])

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 60)

        stored_withdrawal = await self._get_withdrawal(withdrawal.id)
        self.assertIsNotNone(stored_withdrawal)
        assert stored_withdrawal is not None
        self.assertEqual(stored_withdrawal.status, WithdrawalStatus.PAID)

        ledger_entries = await self._get_ledger_entries(account.id)
        self.assertEqual(len(ledger_entries), 1)
        self.assertEqual(ledger_entries[0].entry_type, LedgerEntryType.WITHDRAWAL_RESERVE)

        notifications = await self._get_notifications(account.id)
        self.assertEqual([notification.type for notification in notifications], [
            NotificationType.WITHDRAWAL_CREATED,
            NotificationType.WITHDRAWAL_PAID,
        ])


if __name__ == "__main__":
    unittest.main()
