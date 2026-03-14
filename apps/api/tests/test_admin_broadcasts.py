from __future__ import annotations

from datetime import UTC, datetime, timedelta
import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    Account,
    AccountStatus,
    AdminActionLog,
    Broadcast,
    BroadcastDelivery,
    BroadcastDeliveryStatus,
    BroadcastRun,
    BroadcastRunType,
    Notification,
    NotificationType,
)
from app.db.session import get_session
from app.main import create_app
from app.services.admin_auth import create_admin


class DummyCache:
    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class FakeTelegramClient:
    def __init__(self) -> None:
        self.sent_messages: list[dict] = []
        self.sent_photos: list[dict] = []

    async def send_message(
        self,
        *,
        telegram_id: int,
        text: str,
        parse_mode: str | None = None,
        disable_web_page_preview: bool | None = None,
        reply_markup: dict | None = None,
    ) -> str:
        self.sent_messages.append(
            {
                "telegram_id": telegram_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": disable_web_page_preview,
                "reply_markup": reply_markup,
            }
        )
        return f"msg-{len(self.sent_messages)}"

    async def send_photo(
        self,
        *,
        telegram_id: int,
        photo_url: str,
        caption: str | None = None,
        parse_mode: str | None = None,
        reply_markup: dict | None = None,
    ) -> str:
        self.sent_photos.append(
            {
                "telegram_id": telegram_id,
                "photo_url": photo_url,
                "caption": caption,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
            }
        )
        return f"photo-{len(self.sent_photos)}"

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
        import app.services.broadcasts as broadcasts_service

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

        self._broadcasts_service = broadcasts_service
        self._original_telegram_client_factory = broadcasts_service.get_telegram_notification_client
        self._fake_telegram_client = FakeTelegramClient()
        broadcasts_service.get_telegram_notification_client = lambda: self._fake_telegram_client

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
        self._broadcasts_service.get_telegram_notification_client = self._original_telegram_client_factory
        await self._engine.dispose()
        self._tmpdir.cleanup()

    async def _create_admin_token(self, *, is_superuser: bool = True, username: str = "root") -> str:
        async with self._session_factory() as session:
            admin = await create_admin(
                session,
                username=username,
                password="secret-password",
                email=f"{username}@example.com",
                full_name="Root Admin",
                is_superuser=is_superuser,
            )
            await session.commit()
            await session.refresh(admin)

        response = await self.client.post(
            "/api/v1/admin/auth/login",
            json={"login": username, "password": "secret-password"},
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

    async def test_estimate_broadcast_audience_does_not_create_draft(self) -> None:
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
                        subscription_expires_at=now - timedelta(days=3),
                    ),
                    Account(
                        email="blocked@example.com",
                        status=AccountStatus.BLOCKED,
                        telegram_id=333003,
                    ),
                ]
            )
            await session.commit()

        response = await self.client.post(
            "/api/v1/admin/broadcasts/estimate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "channels": ["in_app", "telegram"],
                "audience": {"segment": "expired", "exclude_blocked": True},
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["estimated_total_accounts"], 1)
        self.assertEqual(body["estimated_in_app_recipients"], 1)
        self.assertEqual(body["estimated_telegram_recipients"], 1)
        self.assertEqual(body["channels"], ["in_app", "telegram"])
        self.assertEqual(body["audience"]["segment"], "expired")

        async with self._session_factory() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(Broadcast)), 0)
            self.assertEqual(await session.scalar(select(func.count()).select_from(AdminActionLog)), 0)

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

    async def test_test_send_broadcast_delivers_to_local_account_and_direct_telegram(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email="receiver@example.com",
                status=AccountStatus.ACTIVE,
                telegram_id=111001,
            )
            session.add(account)
            await session.commit()

        create_response = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Test send draft",
                "title": "Тестовая рассылка",
                "body_html": "<b>Проверка</b> и <a href=\"https://example.com/test\">ссылка</a>",
                "content_type": "photo",
                "image_url": "https://example.com/banner.png",
                "channels": ["in_app", "telegram"],
                "buttons": [{"text": "Открыть", "url": "https://example.com/test"}],
                "audience": {"segment": "all", "exclude_blocked": True},
            },
        )
        self.assertEqual(create_response.status_code, 201)
        broadcast_id = create_response.json()["id"]

        response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/test-send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "emails": ["receiver@example.com"],
                "telegram_ids": [999888777],
                "comment": "Проверка доставки перед запуском",
                "idempotency_key": "broadcast-test-send-1",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["broadcast_id"], broadcast_id)
        self.assertEqual(body["total_targets"], 2)
        self.assertEqual(body["sent_targets"], 2)
        self.assertEqual(body["resolved_account_targets"], 1)
        self.assertEqual(body["direct_telegram_targets"], 1)
        self.assertEqual(body["in_app_notifications_created"], 1)
        self.assertEqual(body["telegram_targets_sent"], 2)
        self.assertEqual(body["items"][0]["resolution"], "account")
        self.assertEqual(body["items"][1]["resolution"], "telegram_direct")

        duplicate_response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/test-send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "emails": ["receiver@example.com"],
                "telegram_ids": [999888777],
                "comment": "Проверка доставки перед запуском",
                "idempotency_key": "broadcast-test-send-1",
            },
        )
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertEqual(duplicate_response.json()["audit_log_id"], body["audit_log_id"])

        self.assertEqual(len(self._fake_telegram_client.sent_photos), 2)
        self.assertEqual(len(self._fake_telegram_client.sent_messages), 0)
        self.assertEqual(self._fake_telegram_client.sent_photos[0]["telegram_id"], 111001)
        self.assertEqual(self._fake_telegram_client.sent_photos[1]["telegram_id"], 999888777)
        self.assertEqual(
            self._fake_telegram_client.sent_photos[0]["reply_markup"],
            {"inline_keyboard": [[{"text": "Открыть", "url": "https://example.com/test"}]]},
        )
        self.assertEqual(self._fake_telegram_client.sent_photos[0]["parse_mode"], "HTML")
        self.assertIn("Тестовая рассылка", self._fake_telegram_client.sent_photos[0]["caption"])

        async with self._session_factory() as session:
            notifications = list(
                (
                    await session.execute(
                        select(Notification).where(Notification.type == NotificationType.BROADCAST)
                    )
                ).scalars().all()
            )
            self.assertEqual(len(notifications), 1)
            self.assertEqual(notifications[0].title, "Тестовая рассылка")
            self.assertEqual(notifications[0].body, "Проверка и ссылка")
            self.assertEqual(notifications[0].action_label, "Открыть")
            self.assertEqual(notifications[0].action_url, "https://example.com/test")
            self.assertEqual(notifications[0].payload["content_type"], "photo")
            self.assertEqual(notifications[0].payload["image_url"], "https://example.com/banner.png")

            self.assertEqual(await session.scalar(select(func.count()).select_from(AdminActionLog)), 2)

    async def test_send_now_broadcast_creates_run_and_worker_delivers_runtime_targets(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            session.add_all(
                [
                    Account(
                        email="first@example.com",
                        display_name="Первый",
                        status=AccountStatus.ACTIVE,
                        telegram_id=111001,
                    ),
                    Account(
                        email="second@example.com",
                        display_name="Второй",
                        status=AccountStatus.ACTIVE,
                        telegram_id=None,
                    ),
                ]
            )
            await session.commit()

        create_response = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Runtime launch",
                "title": "Запуск сейчас",
                "body_html": "<b>Полный запуск</b> для web и Telegram",
                "content_type": "photo",
                "image_url": "https://example.com/runtime.png",
                "channels": ["in_app", "telegram"],
                "buttons": [{"text": "Открыть", "url": "https://example.com/runtime"}],
                "audience": {"segment": "all", "exclude_blocked": True},
            },
        )
        self.assertEqual(create_response.status_code, 201)
        broadcast_id = create_response.json()["id"]

        launch_response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/send-now",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "comment": "Боевой запуск для smoke",
                "idempotency_key": "broadcast-send-now-1",
            },
        )
        self.assertEqual(launch_response.status_code, 200)
        body = launch_response.json()
        self.assertEqual(body["status"], "running")
        self.assertIsNotNone(body["latest_run"])
        self.assertEqual(body["latest_run"]["run_type"], "send_now")
        self.assertEqual(body["latest_run"]["snapshot_total_accounts"], 2)
        self.assertEqual(body["latest_run"]["total_deliveries"], 3)

        async with self._session_factory() as session:
            result = await self._broadcasts_service.process_pending_broadcast_deliveries(
                session,
                limit=20,
            )
            await session.commit()

        self.assertEqual(result.processed, 3)
        self.assertEqual(result.delivered, 3)
        self.assertEqual(result.terminal_failed, 0)

        detail_response = await self.client.get(
            f"/api/v1/admin/broadcasts/{broadcast_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(detail_response.status_code, 200)
        detail_body = detail_response.json()
        self.assertEqual(detail_body["status"], "completed")
        self.assertEqual(detail_body["latest_run"]["status"], "completed")
        self.assertEqual(detail_body["latest_run"]["delivered_deliveries"], 3)
        self.assertEqual(detail_body["latest_run"]["telegram_delivered"], 1)
        self.assertEqual(detail_body["latest_run"]["in_app_delivered"], 2)

        runs_response = await self.client.get(
            "/api/v1/admin/broadcasts/runs?limit=10&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(runs_response.status_code, 200)
        runs_body = runs_response.json()
        self.assertEqual(runs_body["total"], 1)
        self.assertEqual(runs_body["items"][0]["broadcast_id"], broadcast_id)

        run_id = runs_body["items"][0]["id"]
        run_detail_response = await self.client.get(
            f"/api/v1/admin/broadcasts/runs/{run_id}?limit=10&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(run_detail_response.status_code, 200)
        run_detail_body = run_detail_response.json()
        self.assertEqual(run_detail_body["total_deliveries"], 3)
        self.assertEqual(len(run_detail_body["deliveries"]), 3)

        self.assertEqual(len(self._fake_telegram_client.sent_photos), 1)
        self.assertEqual(len(self._fake_telegram_client.sent_messages), 0)
        self.assertEqual(
            self._fake_telegram_client.sent_photos[0]["reply_markup"],
            {"inline_keyboard": [[{"text": "Открыть", "url": "https://example.com/runtime"}]]},
        )

        async with self._session_factory() as session:
            notifications = list(
                (
                    await session.execute(
                        select(Notification).where(Notification.type == NotificationType.BROADCAST)
                    )
                ).scalars().all()
            )
            self.assertEqual(len(notifications), 2)
            self.assertEqual(notifications[0].payload["content_type"], "photo")
            self.assertEqual(await session.scalar(select(func.count()).select_from(BroadcastRun)), 1)
            self.assertEqual(await session.scalar(select(func.count()).select_from(BroadcastDelivery)), 3)

    async def test_schedule_and_cancel_broadcast_runtime(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            session.add(
                Account(email="receiver@example.com", status=AccountStatus.ACTIVE, telegram_id=111001)
            )
            await session.commit()

        create_response = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Scheduled campaign",
                "title": "По расписанию",
                "body_html": "Старт по времени",
                "content_type": "text",
                "channels": ["telegram"],
                "buttons": [],
                "audience": {"segment": "all", "exclude_blocked": True},
            },
        )
        self.assertEqual(create_response.status_code, 201)
        broadcast_id = create_response.json()["id"]

        schedule_response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/schedule",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "scheduled_at": "2026-03-14T23:59:00+03:00",
                "comment": "Поставить на вечер",
                "idempotency_key": "broadcast-schedule-1",
            },
        )
        self.assertEqual(schedule_response.status_code, 200)
        self.assertEqual(schedule_response.json()["status"], "scheduled")

        pause_response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/pause",
            headers={"Authorization": f"Bearer {token}"},
            json={"comment": "Временно пауза", "idempotency_key": "broadcast-pause-1"},
        )
        self.assertEqual(pause_response.status_code, 200)
        self.assertEqual(pause_response.json()["status"], "paused")

        resume_response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/resume",
            headers={"Authorization": f"Bearer {token}"},
            json={"comment": "Продолжаем", "idempotency_key": "broadcast-resume-1"},
        )
        self.assertEqual(resume_response.status_code, 200)
        self.assertEqual(resume_response.json()["status"], "scheduled")

        cancel_response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/cancel",
            headers={"Authorization": f"Bearer {token}"},
            json={"comment": "Отмена кампании", "idempotency_key": "broadcast-cancel-1"},
        )
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.json()["status"], "cancelled")

    async def test_non_superuser_cannot_launch_broadcast(self) -> None:
        token = await self._create_admin_token(is_superuser=False, username="operator")

        create_response = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Operator draft",
                "title": "Черновик оператора",
                "body_html": "Только draft",
                "content_type": "text",
                "channels": ["in_app"],
                "buttons": [],
                "audience": {"segment": "all", "exclude_blocked": True},
            },
        )
        self.assertEqual(create_response.status_code, 201)
        broadcast_id = create_response.json()["id"]

        response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/send-now",
            headers={"Authorization": f"Bearer {token}"},
            json={"comment": "Не должно пройти", "idempotency_key": "broadcast-send-now-operator"},
        )
        self.assertEqual(response.status_code, 403)

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
