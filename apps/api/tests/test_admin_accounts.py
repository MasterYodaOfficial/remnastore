from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import tempfile
import unittest
import uuid
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    Account,
    AccountStatus,
    AdminActionLog,
    AuthAccount,
    AuthProvider,
    LedgerEntry,
    LedgerEntryType,
    Payment,
    SubscriptionGrant,
    Withdrawal,
    WithdrawalDestinationType,
    WithdrawalStatus,
)
from app.db.session import get_session
from app.domain.payments import PaymentFlowType, PaymentProvider, PaymentStatus
from app.integrations.remnawave.client import RemnawaveUser
from app.main import create_app
from app.services.admin_auth import create_admin


class DummyCache:
    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def account_response_key(self, account_id: str) -> str:
        return f"account:{account_id}"

    async def delete(self, *keys: str) -> None:
        return None


@dataclass
class FakeRemnawaveGateway:
    users: dict[uuid.UUID, RemnawaveUser]

    async def provision_user(
        self,
        *,
        user_uuid: uuid.UUID,
        expire_at: datetime,
        email: str | None,
        telegram_id: int | None,
        is_trial: bool,
    ) -> RemnawaveUser:
        user = RemnawaveUser(
            uuid=user_uuid,
            username=f"acc_{user_uuid.hex}",
            status="ACTIVE",
            expire_at=expire_at,
            subscription_url=f"https://panel.test/sub/{user_uuid.hex[:8]}",
            telegram_id=telegram_id,
            email=email,
            tag="TRIAL" if is_trial else None,
        )
        self.users[user_uuid] = user
        return user


class AdminAccountEndpointsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "admin-accounts.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._fake_gateway = FakeRemnawaveGateway(users={})

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module
        import app.services.admin_auth as admin_auth_service
        import app.services.admin_subscriptions as admin_subscriptions_service

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

        self._admin_subscriptions_service = admin_subscriptions_service
        self._original_admin_gateway_factory = admin_subscriptions_service.get_remnawave_gateway
        admin_subscriptions_service.get_remnawave_gateway = lambda: self._fake_gateway

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
        self._admin_subscriptions_service.get_remnawave_gateway = self._original_admin_gateway_factory
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

    async def test_search_accounts_by_auth_email_and_telegram_id(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email=None,
                display_name="Search Target",
                telegram_id=777000111,
                username="search_target",
                balance=900,
            )
            session.add(account)
            await session.flush()
            session.add(
                AuthAccount(
                    account_id=account.id,
                    provider=AuthProvider.GOOGLE,
                    provider_uid="google-search-target",
                    email="search-target@example.com",
                    display_name="Search Target",
                )
            )
            await session.commit()

        response_by_email = await self.client.get(
            "/api/v1/admin/accounts/search",
            params={"query": "search-target@example.com"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response_by_email.status_code, 200)
        body = response_by_email.json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["username"], "search_target")
        self.assertEqual(body["items"][0]["telegram_id"], 777000111)

        response_by_telegram = await self.client.get(
            "/api/v1/admin/accounts/search",
            params={"query": "777000111"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response_by_telegram.status_code, 200)
        self.assertEqual(len(response_by_telegram.json()["items"]), 1)

    async def test_subscription_plans_endpoint_returns_catalog(self) -> None:
        token = await self._create_admin_token()

        response = await self.client.get(
            "/api/v1/admin/accounts/subscription-plans",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(len(body), 1)
        self.assertIsInstance(body[0]["code"], str)
        self.assertIsInstance(body[0]["duration_days"], int)

    async def test_account_detail_returns_recent_finance_and_subscription_blocks(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email="detail@example.com",
                display_name="Detail User",
                telegram_id=555444333,
                username="detail_user",
                first_name="Detail",
                last_name="User",
                locale="ru",
                status=AccountStatus.ACTIVE,
                balance=1300,
                referral_code="DETAILCODE",
                referral_earnings=400,
                referrals_count=2,
                subscription_status="active",
                subscription_is_trial=False,
            )
            session.add(account)
            await session.flush()

            session.add(
                AuthAccount(
                    account_id=account.id,
                    provider=AuthProvider.SUPABASE,
                    provider_uid="supabase-detail-user",
                    email="detail@example.com",
                    display_name="Detail User",
                )
            )
            session.add(
                LedgerEntry(
                    account_id=account.id,
                    entry_type=LedgerEntryType.TOPUP_PAYMENT,
                    amount=500,
                    currency="RUB",
                    balance_before=800,
                    balance_after=1300,
                    reference_type="payment",
                    reference_id="pay-1",
                    comment="Пополнение",
                )
            )
            session.add(
                Payment(
                    account_id=account.id,
                    provider=PaymentProvider.YOOKASSA,
                    flow_type=PaymentFlowType.WALLET_TOPUP,
                    status=PaymentStatus.PENDING,
                    amount=500,
                    currency="RUB",
                    provider_payment_id="detail-payment",
                    description="Пополнение баланса",
                )
            )
            session.add(
                Withdrawal(
                    account_id=account.id,
                    amount=300,
                    destination_type=WithdrawalDestinationType.SBP,
                    destination_value="+79990000000",
                    status=WithdrawalStatus.NEW,
                    user_comment="Нужен вывод",
                )
            )
            await session.commit()
            account_id = str(account.id)

        response = await self.client.get(
            f"/api/v1/admin/accounts/{account_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], account_id)
        self.assertEqual(body["email"], "detail@example.com")
        self.assertEqual(body["balance"], 1300)
        self.assertEqual(body["subscription_status"], "active")
        self.assertEqual(body["ledger_entries_count"], 1)
        self.assertEqual(body["payments_count"], 1)
        self.assertEqual(body["pending_payments_count"], 1)
        self.assertEqual(body["withdrawals_count"], 1)
        self.assertEqual(body["pending_withdrawals_count"], 1)
        self.assertEqual(len(body["auth_accounts"]), 1)
        self.assertEqual(len(body["recent_ledger_entries"]), 1)
        self.assertEqual(len(body["recent_payments"]), 1)
        self.assertEqual(len(body["recent_withdrawals"]), 1)
        self.assertEqual(body["recent_ledger_entries"][0]["comment"], "Пополнение")
        self.assertEqual(body["recent_payments"][0]["status"], PaymentStatus.PENDING.value)
        self.assertEqual(body["recent_withdrawals"][0]["status"], WithdrawalStatus.NEW.value)

    async def test_balance_adjustment_updates_balance_and_is_idempotent(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email="adjust@example.com",
                display_name="Adjust User",
                balance=1000,
            )
            session.add(account)
            await session.commit()
            account_id = str(account.id)

        payload = {
            "amount": 250,
            "comment": "Ручная корректировка по сверке",
            "idempotency_key": "admin-adjust-1",
        }

        response = await self.client.post(
            f"/api/v1/admin/accounts/{account_id}/balance-adjustments",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["account_id"], account_id)
        self.assertEqual(body["balance"], 1250)
        self.assertEqual(body["ledger_entry"]["entry_type"], LedgerEntryType.ADMIN_CREDIT.value)
        self.assertEqual(body["ledger_entry"]["amount"], 250)
        self.assertEqual(body["ledger_entry"]["comment"], "Ручная корректировка по сверке")

        duplicate_response = await self.client.post(
            f"/api/v1/admin/accounts/{account_id}/balance-adjustments",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(duplicate_response.status_code, 200)
        duplicate_body = duplicate_response.json()
        self.assertEqual(duplicate_body["ledger_entry"]["id"], body["ledger_entry"]["id"])
        self.assertEqual(duplicate_body["balance"], 1250)

        async with self._session_factory() as session:
            stored_account = await session.get(Account, uuid.UUID(account_id))
            assert stored_account is not None
            self.assertEqual(stored_account.balance, 1250)

            result = await session.execute(
                select(LedgerEntry)
                .where(LedgerEntry.account_id == stored_account.id)
                .order_by(LedgerEntry.id.asc())
            )
            entries = list(result.scalars().all())
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].entry_type, LedgerEntryType.ADMIN_CREDIT)

    async def test_balance_adjustment_rejects_insufficient_funds(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email="debit@example.com",
                display_name="Debit User",
                balance=120,
            )
            session.add(account)
            await session.commit()
            account_id = str(account.id)

        response = await self.client.post(
            f"/api/v1/admin/accounts/{account_id}/balance-adjustments",
            json={
                "amount": -300,
                "comment": "Списать ошибочное начисление",
                "idempotency_key": "admin-adjust-2",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "insufficient funds")

        async with self._session_factory() as session:
            stored_account = await session.get(Account, uuid.UUID(account_id))
            assert stored_account is not None
            self.assertEqual(stored_account.balance, 120)

            result = await session.execute(
                select(LedgerEntry).where(LedgerEntry.account_id == stored_account.id)
            )
            self.assertEqual(list(result.scalars().all()), [])

    async def test_subscription_grant_updates_subscription_and_is_idempotent(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email="grant@example.com",
                display_name="Grant User",
                telegram_id=700100200,
                balance=0,
            )
            session.add(account)
            await session.commit()
            account_id = str(account.id)

        response = await self.client.post(
            f"/api/v1/admin/accounts/{account_id}/subscription-grants",
            json={
                "plan_code": "plan_1m",
                "comment": "Выдали доступ после офлайн-оплаты",
                "idempotency_key": "admin-subscription-grant-1",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["account_id"], account_id)
        self.assertEqual(body["plan_code"], "plan_1m")
        self.assertEqual(body["subscription_status"], "ACTIVE")
        self.assertTrue(body["subscription_url"].startswith("https://panel.test/sub/"))

        duplicate_response = await self.client.post(
            f"/api/v1/admin/accounts/{account_id}/subscription-grants",
            json={
                "plan_code": "plan_1m",
                "comment": "Выдали доступ после офлайн-оплаты",
                "idempotency_key": "admin-subscription-grant-1",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(duplicate_response.status_code, 200)
        duplicate_body = duplicate_response.json()
        self.assertEqual(duplicate_body["subscription_grant_id"], body["subscription_grant_id"])
        self.assertEqual(duplicate_body["audit_log_id"], body["audit_log_id"])

        async with self._session_factory() as session:
            stored_account = await session.get(Account, uuid.UUID(account_id))
            assert stored_account is not None
            self.assertEqual(stored_account.subscription_status, "ACTIVE")
            self.assertFalse(stored_account.subscription_is_trial)
            self.assertIsNotNone(stored_account.subscription_expires_at)

            grants_result = await session.execute(
                select(SubscriptionGrant)
                .where(SubscriptionGrant.account_id == stored_account.id)
                .order_by(SubscriptionGrant.id.asc())
            )
            grants = list(grants_result.scalars().all())
            self.assertEqual(len(grants), 1)
            self.assertEqual(grants[0].purchase_source, "admin")
            self.assertEqual(grants[0].amount, 0)
            self.assertIsNotNone(grants[0].applied_at)

            logs_result = await session.execute(
                select(AdminActionLog)
                .where(AdminActionLog.target_account_id == stored_account.id)
                .order_by(AdminActionLog.id.asc())
            )
            logs = list(logs_result.scalars().all())
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].comment, "Выдали доступ после офлайн-оплаты")
            self.assertEqual(logs[0].payload["plan_code"], "plan_1m")
            self.assertEqual(logs[0].payload["subscription_grant_id"], grants[0].id)
