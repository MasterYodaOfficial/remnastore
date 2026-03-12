from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    Account,
    Payment,
    Withdrawal,
    WithdrawalDestinationType,
    WithdrawalStatus,
)
from app.db.session import get_session
from app.domain.payments import PaymentFlowType, PaymentProvider, PaymentStatus
from app.main import create_app
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
        self._original_bootstrap_username = admin_auth_service.settings.admin_bootstrap_username
        self._original_bootstrap_password = admin_auth_service.settings.admin_bootstrap_password
        self._original_bootstrap_email = admin_auth_service.settings.admin_bootstrap_email
        self._original_bootstrap_full_name = admin_auth_service.settings.admin_bootstrap_full_name
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
        self._admin_auth_service.settings.admin_bootstrap_username = self._original_bootstrap_username
        self._admin_auth_service.settings.admin_bootstrap_password = self._original_bootstrap_password
        self._admin_auth_service.settings.admin_bootstrap_email = self._original_bootstrap_email
        self._admin_auth_service.settings.admin_bootstrap_full_name = self._original_bootstrap_full_name
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

        async with self._session_factory() as session:
            account_one = Account(email="a@example.com", subscription_status="active")
            account_two = Account(email="b@example.com", subscription_status="inactive")
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
            },
        )
