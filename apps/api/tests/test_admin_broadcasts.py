from __future__ import annotations

from datetime import UTC, datetime, timedelta
import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Account, AccountStatus, AdminActionLog, Broadcast
from app.db.session import get_session
from app.main import create_app
from app.services.admin_auth import create_admin


class DummyCache:
    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class AdminBroadcastEndpointsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "admin-broadcasts.sqlite3"
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

    async def test_create_broadcast_draft_returns_estimates(self) -> None:
        token = await self._create_admin_token()
        now = datetime.now(UTC)

        async with self._session_factory() as session:
            session.add_all(
                [
                    Account(email="a@example.com", status=AccountStatus.ACTIVE, telegram_id=111001),
                    Account(email="b@example.com", status=AccountStatus.ACTIVE, telegram_id=None),
                    Account(
                        email="blocked@example.com",
                        status=AccountStatus.BLOCKED,
                        telegram_id=222002,
                    ),
                    Account(
                        email="expired@example.com",
                        status=AccountStatus.ACTIVE,
                        telegram_id=333003,
                        subscription_expires_at=now - timedelta(days=2),
                    ),
                ]
            )
            await session.commit()

        response = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Spring promo",
                "title": "Весеннее обновление",
                "body_html": "<b>Скидка</b> на продление и <a href=\"https://example.com/pay\">ссылка</a>",
                "content_type": "text",
                "channels": ["in_app", "telegram"],
                "buttons": [{"text": "Открыть", "url": "https://example.com/pay"}],
                "audience": {"segment": "all", "exclude_blocked": True},
            },
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "draft")
        self.assertEqual(body["estimated_total_accounts"], 3)
        self.assertEqual(body["estimated_in_app_recipients"], 3)
        self.assertEqual(body["estimated_telegram_recipients"], 2)
        self.assertEqual(body["channels"], ["in_app", "telegram"])
        self.assertEqual(body["buttons"][0]["text"], "Открыть")

        async with self._session_factory() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(Broadcast)), 1)
            self.assertEqual(await session.scalar(select(func.count()).select_from(AdminActionLog)), 1)

    async def test_update_broadcast_draft_recalculates_estimates(self) -> None:
        token = await self._create_admin_token()
        now = datetime.now(UTC)

        async with self._session_factory() as session:
            session.add_all(
                [
                    Account(email="active@example.com", status=AccountStatus.ACTIVE, telegram_id=111001),
                    Account(
                        email="expired@example.com",
                        status=AccountStatus.ACTIVE,
                        telegram_id=222002,
                        subscription_expires_at=now - timedelta(days=5),
                    ),
                    Account(
                        email="future@example.com",
                        status=AccountStatus.ACTIVE,
                        telegram_id=333003,
                        subscription_expires_at=now + timedelta(days=5),
                    ),
                ]
            )
            await session.commit()

        create_response = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Draft one",
                "title": "Черновик",
                "body_html": "Первый текст",
                "content_type": "text",
                "channels": ["in_app"],
                "buttons": [],
                "audience": {"segment": "all", "exclude_blocked": True},
            },
        )
        self.assertEqual(create_response.status_code, 201)
        broadcast_id = create_response.json()["id"]

        update_response = await self.client.put(
            f"/api/v1/admin/broadcasts/{broadcast_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Expired photo campaign",
                "title": "Истекшие подписки",
                "body_html": "<i>Вернитесь</i> по ссылке",
                "content_type": "photo",
                "image_url": "https://example.com/banner.png",
                "channels": ["telegram"],
                "buttons": [{"text": "Продлить", "url": "https://example.com/renew"}],
                "audience": {"segment": "expired", "exclude_blocked": True},
            },
        )

        self.assertEqual(update_response.status_code, 200)
        body = update_response.json()
        self.assertEqual(body["content_type"], "photo")
        self.assertEqual(body["estimated_total_accounts"], 1)
        self.assertEqual(body["estimated_in_app_recipients"], 0)
        self.assertEqual(body["estimated_telegram_recipients"], 1)
        self.assertEqual(body["image_url"], "https://example.com/banner.png")

    async def test_create_broadcast_rejects_invalid_html(self) -> None:
        token = await self._create_admin_token()

        response = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Bad html",
                "title": "Ошибка",
                "body_html": "<script>alert(1)</script>",
                "content_type": "text",
                "channels": ["telegram"],
                "buttons": [],
                "audience": {"segment": "with_telegram", "exclude_blocked": True},
            },
        )

        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertTrue(detail)
        self.assertIn("unsupported telegram html tag", detail[0]["msg"])

    async def test_list_broadcasts_returns_saved_items(self) -> None:
        token = await self._create_admin_token()

        first = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "One",
                "title": "Первая",
                "body_html": "Текст один",
                "content_type": "text",
                "channels": ["in_app"],
                "buttons": [],
                "audience": {"segment": "all", "exclude_blocked": True},
            },
        )
        second = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Two",
                "title": "Вторая",
                "body_html": "Текст два",
                "content_type": "text",
                "channels": ["telegram"],
                "buttons": [],
                "audience": {"segment": "with_telegram", "exclude_blocked": True},
            },
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

        response = await self.client.get(
            "/api/v1/admin/broadcasts?limit=10&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual(body["items"][0]["name"], "Two")


if __name__ == "__main__":
    unittest.main()
