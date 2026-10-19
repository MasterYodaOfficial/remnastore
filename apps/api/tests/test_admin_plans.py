from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plan_fixtures import TEST_PLANS, seed_subscription_plans

from app.api.dependencies import get_current_account
from app.db.base import Base
from app.db.models import Account, Payment, SubscriptionPlanRecord
from app.db.session import get_session
from app.domain.payments import PaymentFlowType, PaymentProvider, PaymentStatus
from app.main import create_app
from app.services.admin_auth import create_admin
from app.services.promos import resolve_plan_checkout_amount


class DummyCache:
    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class AdminPlansEndpointsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "admin-plans.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await seed_subscription_plans(conn, (TEST_PLANS[1], TEST_PLANS[2]))

        import app.services.admin_auth as admin_auth_service
        import app.services.cache as cache_module

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

        async def override_get_current_account():
            return Account(id=uuid.uuid4())

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

    async def test_list_subscription_plans_returns_catalog(self) -> None:
        token = await self._create_admin_token()

        response = await self.client.get(
            "/api/v1/admin/plans",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 2)
        self.assertEqual(body[0]["code"], "plan_1m")
        self.assertEqual(body[1]["popular"], True)

    async def test_create_and_update_subscription_plan_persist_to_database(
        self,
    ) -> None:
        token = await self._create_admin_token()

        create_response = await self.client.post(
            "/api/v1/admin/plans",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "code": "plan_12m",
                "name": "12 месяцев",
                "price_rub": 1990,
                "extra_device_price_rub": 480,
                "price_stars": 999,
                "duration_days": 365,
                "features": ["Год доступа", "Максимальная выгода"],
                "device_limit": 3,
                "popular": False,
            },
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_response.json()["device_limit"], 3)
        self.assertEqual(create_response.json()["extra_device_price_rub"], 480)

        update_response = await self.client.put(
            "/api/v1/admin/plans/plan_12m",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "12 месяцев плюс",
                "price_rub": 2190,
                "extra_device_price_rub": 450,
                "price_stars": 1099,
                "duration_days": 365,
                "features": ["Год доступа", "Поддержка без очереди"],
                "device_limit": 5,
                "popular": True,
            },
        )

        self.assertEqual(update_response.status_code, 200)
        updated = update_response.json()
        self.assertEqual(updated["name"], "12 месяцев плюс")
        self.assertEqual(updated["price_rub"], 2190)
        self.assertEqual(updated["device_limit"], 5)
        self.assertEqual(updated["popular"], True)

        async with self._session_factory() as session:
            persisted = await session.get(SubscriptionPlanRecord, "plan_12m")
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted.name, updated["name"])
            self.assertEqual(persisted.device_limit, 5)
            self.assertEqual(persisted.extra_device_price_rub, 450)
            self.assertEqual(persisted.features, updated["features"])

        public_response = await self.client.get("/api/v1/payments/plans")
        public_plan = next(
            item for item in public_response.json() if item["code"] == "plan_12m"
        )
        self.assertEqual(public_plan["price_rub"], 2190)
        self.assertEqual(public_plan["duration_days"], 365)
        self.assertEqual(public_plan["extra_device_price_rub"], 450)

        async with self._session_factory() as session:
            self.assertEqual(
                await resolve_plan_checkout_amount(
                    session, plan_code="plan_12m", currency="RUB"
                ),
                2190,
            )
            self.assertEqual(
                await resolve_plan_checkout_amount(
                    session, plan_code="plan_12m", currency="XTR"
                ),
                1099,
            )

    async def test_delete_subscription_plan_blocks_used_plan(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            session.add(
                Payment(
                    account_id=uuid.uuid4(),
                    provider=PaymentProvider.YOOKASSA,
                    flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                    status=PaymentStatus.PENDING,
                    amount=199,
                    currency="RUB",
                    provider_payment_id="payment-1",
                    plan_code="plan_1m",
                )
            )
            await session.commit()

        response = await self.client.delete(
            "/api/v1/admin/plans/plan_1m",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error_code"], "admin_plan_in_use")

    async def test_delete_subscription_plan_removes_unused_plan(self) -> None:
        token = await self._create_admin_token()

        response = await self.client.delete(
            "/api/v1/admin/plans/plan_3m",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 204)
        async with self._session_factory() as session:
            self.assertIsNone(await session.get(SubscriptionPlanRecord, "plan_3m"))
            self.assertIsNotNone(await session.get(SubscriptionPlanRecord, "plan_1m"))

    async def test_empty_catalog_can_be_managed_without_json_fallback(self) -> None:
        token = await self._create_admin_token()
        async with self._session_factory() as session:
            await session.execute(delete(SubscriptionPlanRecord))
            await session.commit()

        response = await self.client.get("/api/v1/payments/plans")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        headers = {"Authorization": f"Bearer {token}"}
        response = await self.client.post(
            "/api/v1/admin/plans",
            headers=headers,
            json={
                "code": "first_plan",
                "name": "Первый тариф",
                "price_rub": 150,
                "duration_days": 14,
                "features": ["Все серверы"],
                "device_limit": 0,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["device_limit"], 0)
        response = await self.client.delete(
            "/api/v1/admin/plans/first_plan", headers=headers
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error_code"], "admin_plan_in_use")

    async def test_duplicate_code_does_not_change_existing_plan(self) -> None:
        token = await self._create_admin_token()
        response = await self.client.post(
            "/api/v1/admin/plans",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "code": "plan_1m",
                "name": "Другой тариф",
                "price_rub": 1,
                "duration_days": 1,
                "features": ["Доступ"],
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error_code"], "admin_plan_conflict")
        async with self._session_factory() as session:
            plan = await session.get(SubscriptionPlanRecord, "plan_1m")
            self.assertEqual(plan.price_rub, 199)

    async def test_database_changes_are_visible_in_bot_catalog(self) -> None:
        from app.core.config import settings

        async with self._session_factory() as session:
            plan = await session.get(SubscriptionPlanRecord, "plan_1m")
            plan.price_rub = 299
            plan.duration_days = 31
            await session.commit()

        with patch.object(settings, "api_token", "plans-test-token"):
            response = await self.client.get(
                "/api/v1/internal/bot/plans",
                headers={"Authorization": "Bearer plans-test-token"},
            )
        self.assertEqual(response.status_code, 200)
        plan = response.json()["items"][0]
        self.assertEqual(plan["price_rub"], 299)
        self.assertEqual(plan["duration_days"], 31)
