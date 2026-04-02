from __future__ import annotations

from datetime import UTC, datetime, timedelta
import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    Account,
    AccountStatus,
    Payment,
    Withdrawal,
    WithdrawalDestinationType,
    WithdrawalStatus,
)
from app.db.session import get_session
from app.domain.payments import PaymentFlowType, PaymentProvider, PaymentStatus
from app.main import create_app
from app.services.i18n import translate
from app.services.admin_auth import create_admin


class DummyCache:
    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class AdminAuthFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "admin-auth.sqlite3"
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
        self._original_bootstrap_username = (
            admin_auth_service.settings.admin_bootstrap_username
        )
        self._original_bootstrap_password = (
            admin_auth_service.settings.admin_bootstrap_password
        )
        self._original_bootstrap_email = (
            admin_auth_service.settings.admin_bootstrap_email
        )
        self._original_bootstrap_full_name = (
            admin_auth_service.settings.admin_bootstrap_full_name
        )
        admin_auth_service.settings.admin_bootstrap_username = ""
        admin_auth_service.settings.admin_bootstrap_password = ""
        admin_auth_service.settings.admin_bootstrap_email = ""
        admin_auth_service.settings.admin_bootstrap_full_name = ""

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
        self._admin_auth_service.settings.admin_bootstrap_username = (
            self._original_bootstrap_username
        )
        self._admin_auth_service.settings.admin_bootstrap_password = (
            self._original_bootstrap_password
        )
        self._admin_auth_service.settings.admin_bootstrap_email = (
            self._original_bootstrap_email
        )
        self._admin_auth_service.settings.admin_bootstrap_full_name = (
            self._original_bootstrap_full_name
        )
        await self._engine.dispose()
        self._tmpdir.cleanup()

    async def _create_admin(self):
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
            return admin

    async def test_admin_login_returns_token_and_profile(self) -> None:
        await self._create_admin()

        with self.assertLogs("app.audit", level="INFO") as captured:
            response = await self.client.post(
                "/api/v1/admin/auth/login",
                json={"login": "root", "password": "secret-password"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["token_type"], "bearer")
        self.assertTrue(body["access_token"])
        self.assertEqual(body["admin"]["username"], "root")
        self.assertTrue(body["admin"]["is_active"])
        self.assertTrue(
            any(
                "event=admin.login" in line and "outcome=success" in line
                for line in captured.output
            )
        )

    async def test_admin_login_failure_emits_audit_log(self) -> None:
        await self._create_admin()

        with self.assertLogs("app.audit", level="WARNING") as captured:
            response = await self.client.post(
                "/api/v1/admin/auth/login",
                json={"login": "root", "password": "wrong-password"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {
                "detail": translate("api.admin.errors.invalid_credentials"),
                "error_code": "admin_invalid_credentials",
            },
        )
        self.assertTrue(
            any(
                "event=admin.login" in line and "outcome=failure" in line
                for line in captured.output
            )
        )

    async def test_admin_me_rejects_invalid_token_with_error_code(self) -> None:
        response = await self.client.get(
            "/api/v1/admin/auth/me",
            headers={"Authorization": "Bearer invalid-admin-token"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {
                "detail": translate("api.admin.errors.invalid_token"),
                "error_code": "admin_invalid_token",
            },
        )

    async def test_admin_me_requires_admin_token(self) -> None:
        await self._create_admin()
        login_response = await self.client.post(
            "/api/v1/admin/auth/login",
            json={"login": "root@example.com", "password": "secret-password"},
        )
        token = login_response.json()["access_token"]

        response = await self.client.get(
            "/api/v1/admin/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "root")

    async def test_admin_dashboard_summary_returns_counts(self) -> None:
        await self._create_admin()
        now = datetime.now(UTC)

        async with self._session_factory() as session:
            account_one = Account(
                email="a@example.com",
                subscription_status="active",
                balance=700,
                referral_earnings=150,
                created_at=now - timedelta(days=3),
            )
            account_two = Account(
                email="b@example.com",
                subscription_status="inactive",
                balance=200,
                referral_earnings=20,
                status=AccountStatus.BLOCKED,
                created_at=now - timedelta(days=15),
            )
            session.add_all([account_one, account_two])
            await session.flush()
            session.add(
                Withdrawal(
                    account_id=account_one.id,
                    amount=300,
                    destination_type=WithdrawalDestinationType.SBP,
                    destination_value="+79990000000",
                    status=WithdrawalStatus.NEW,
                )
            )
            session.add(
                Withdrawal(
                    account_id=account_two.id,
                    amount=150,
                    destination_type=WithdrawalDestinationType.CARD,
                    destination_value="2200123412341234",
                    status=WithdrawalStatus.PAID,
                    processed_at=now - timedelta(days=4),
                )
            )
            session.add(
                Payment(
                    account_id=account_two.id,
                    provider=PaymentProvider.YOOKASSA,
                    flow_type=PaymentFlowType.WALLET_TOPUP,
                    status=PaymentStatus.PENDING,
                    amount=500,
                    currency="RUB",
                    provider_payment_id="admin-summary-payment",
                )
            )
            session.add(
                Payment(
                    account_id=account_one.id,
                    provider=PaymentProvider.YOOKASSA,
                    flow_type=PaymentFlowType.WALLET_TOPUP,
                    status=PaymentStatus.SUCCEEDED,
                    amount=900,
                    currency="RUB",
                    provider_payment_id="admin-summary-wallet-topup",
                    finalized_at=now - timedelta(days=2),
                )
            )
            session.add(
                Payment(
                    account_id=account_one.id,
                    provider=PaymentProvider.TELEGRAM_STARS,
                    flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                    status=PaymentStatus.SUCCEEDED,
                    amount=1200,
                    currency="RUB",
                    provider_payment_id="admin-summary-direct-plan",
                    finalized_at=now - timedelta(days=1),
                )
            )
            await session.commit()

        login_response = await self.client.post(
            "/api/v1/admin/auth/login",
            json={"login": "root", "password": "secret-password"},
        )
        token = login_response.json()["access_token"]

        response = await self.client.get(
            "/api/v1/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "total_accounts": 2,
                "active_subscriptions": 1,
                "pending_withdrawals": 1,
                "pending_payments": 1,
                "blocked_accounts": 1,
                "new_accounts_last_7d": 1,
                "total_wallet_balance": 900,
                "total_referral_earnings": 170,
                "pending_withdrawals_amount": 300,
                "paid_withdrawals_amount_last_30d": 150,
                "successful_payments_last_30d": 2,
                "successful_payments_amount_last_30d": 2100,
                "wallet_topups_amount_last_30d": 900,
                "direct_plan_revenue_last_30d": 1200,
            },
        )
