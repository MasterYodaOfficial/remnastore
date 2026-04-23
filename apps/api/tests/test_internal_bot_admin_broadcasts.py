from __future__ import annotations

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
    Broadcast,
    BroadcastDelivery,
    BroadcastRun,
    BroadcastStatus,
)
from app.db.session import get_session
from app.main import create_app


class DummyCache:
    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class FakeTelegramClient:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, object]] = []
        self.sent_photos: list[dict[str, object]] = []
        self.copied_messages: list[dict[str, object]] = []
        self.copied_media_groups: list[dict[str, object]] = []

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

    async def copy_message(
        self,
        *,
        telegram_id: int,
        from_chat_id: int,
        message_id: int,
        disable_notification: bool | None = True,
    ) -> str:
        self.copied_messages.append(
            {
                "telegram_id": telegram_id,
                "from_chat_id": from_chat_id,
                "message_id": message_id,
                "disable_notification": disable_notification,
            }
        )
        return f"copy-{len(self.copied_messages)}"

    async def copy_messages(
        self,
        *,
        telegram_id: int,
        from_chat_id: int,
        message_ids: list[int],
        disable_notification: bool | None = True,
    ) -> list[str]:
        self.copied_media_groups.append(
            {
                "telegram_id": telegram_id,
                "from_chat_id": from_chat_id,
                "message_ids": list(message_ids),
                "disable_notification": disable_notification,
            }
        )
        return [f"copy-group-{index}" for index, _ in enumerate(message_ids, start=1)]


class InternalBotAdminBroadcastTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = (
            Path(self._tmpdir.name) / "internal-bot-admin-broadcasts.sqlite3"
        )
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.broadcasts as broadcasts_service
        import app.services.cache as cache_module
        import app.api.v1.endpoints.internal as internal_endpoints

        self._broadcasts_service = broadcasts_service
        self._cache_module = cache_module
        self._internal_endpoints = internal_endpoints
        self._original_cache = cache_module._cache
        self._original_api_token = internal_endpoints.settings.api_token
        self._original_bot_admin_ids = internal_endpoints.settings.bot_admin_ids
        self._original_bot_admin_ids_broadcasts = (
            broadcasts_service.settings.bot_admin_ids
        )
        self._original_telegram_client_factory = (
            broadcasts_service.get_telegram_notification_client
        )
        cache_module._cache = DummyCache()
        internal_endpoints.settings.api_token = "internal-token"
        internal_endpoints.settings.bot_admin_ids = "101"
        broadcasts_service.settings.bot_admin_ids = "101"
        self._fake_telegram_client = FakeTelegramClient()
        broadcasts_service.get_telegram_notification_client = lambda: (
            self._fake_telegram_client
        )

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
        self._internal_endpoints.settings.api_token = self._original_api_token
        self._internal_endpoints.settings.bot_admin_ids = self._original_bot_admin_ids
        self._broadcasts_service.settings.bot_admin_ids = (
            self._original_bot_admin_ids_broadcasts
        )
        self._broadcasts_service.get_telegram_notification_client = (
            self._original_telegram_client_factory
        )
        await self._engine.dispose()
        self._tmpdir.cleanup()

    async def test_preview_endpoint_sends_test_message_to_admin(self) -> None:
        response = await self.client.post(
            "/api/v1/internal/bot/admin/broadcasts/test",
            headers={"Authorization": "Bearer internal-token"},
            json={
                "admin_telegram_id": 101,
                "source_chat_id": 101,
                "source_message_ids": [55],
                "media_group_id": None,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["content_type"], "telegram_copy")
        self.assertEqual(body["telegram_message_ids"], ["copy-1"])
        self.assertEqual(len(self._fake_telegram_client.copied_messages), 1)
        self.assertEqual(
            self._fake_telegram_client.copied_messages[0]["telegram_id"], 101
        )
        self.assertEqual(
            self._fake_telegram_client.copied_messages[0]["from_chat_id"], 101
        )
        self.assertEqual(
            self._fake_telegram_client.copied_messages[0]["message_id"], 55
        )

    async def test_send_now_endpoint_creates_broadcast_and_pending_deliveries(
        self,
    ) -> None:
        async with self._session_factory() as session:
            session.add_all(
                [
                    Account(
                        email="active1@example.com",
                        status=AccountStatus.ACTIVE,
                        telegram_id=700001,
                    ),
                    Account(
                        email="active2@example.com",
                        status=AccountStatus.ACTIVE,
                        telegram_id=700002,
                    ),
                    Account(
                        email="blocked@example.com",
                        status=AccountStatus.BLOCKED,
                        telegram_id=700003,
                    ),
                ]
            )
            await session.commit()

        response = await self.client.post(
            "/api/v1/internal/bot/admin/broadcasts/send-now",
            headers={"Authorization": "Bearer internal-token"},
            json={
                "admin_telegram_id": 101,
                "source_chat_id": 101,
                "source_message_ids": [77, 78],
                "media_group_id": "album-1",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], BroadcastStatus.RUNNING.value)
        self.assertEqual(body["latest_run_status"], "running")
        self.assertEqual(body["estimated_telegram_recipients"], 2)
        self.assertEqual(body["pending_deliveries"], 2)

        async with self._session_factory() as session:
            self.assertEqual(
                await session.scalar(select(func.count()).select_from(Broadcast)), 1
            )
            self.assertEqual(
                await session.scalar(select(func.count()).select_from(BroadcastRun)), 1
            )
            self.assertEqual(
                await session.scalar(
                    select(func.count()).select_from(BroadcastDelivery)
                ),
                2,
            )

        status_response = await self.client.get(
            "/api/v1/internal/bot/admin/broadcasts?admin_telegram_id=101&limit=5",
            headers={"Authorization": "Bearer internal-token"},
        )
        self.assertEqual(status_response.status_code, 200)
        items = status_response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["broadcast_id"], body["broadcast_id"])
        self.assertEqual(items[0]["pending_deliveries"], 2)
        self.assertEqual(items[0]["content_type"], "telegram_copy")

        import app.services.broadcasts as broadcasts_service

        async with self._session_factory() as session:
            result = await broadcasts_service.process_pending_broadcast_deliveries(
                session,
                limit=10,
            )
            await session.commit()

        self.assertEqual(result.delivered, 2)
        self.assertEqual(len(self._fake_telegram_client.copied_media_groups), 2)
        self.assertEqual(
            self._fake_telegram_client.copied_media_groups[0]["message_ids"],
            [77, 78],
        )

    async def test_stats_summary_endpoint_returns_dashboard_metrics(self) -> None:
        async with self._session_factory() as session:
            session.add_all(
                [
                    Account(
                        email="active@example.com",
                        status=AccountStatus.ACTIVE,
                        telegram_id=700101,
                        subscription_status="active",
                    ),
                    Account(
                        email="blocked@example.com",
                        status=AccountStatus.BLOCKED,
                        telegram_id=None,
                    ),
                ]
            )
            await session.commit()

        response = await self.client.get(
            "/api/v1/internal/bot/admin/stats/summary?admin_telegram_id=101",
            headers={"Authorization": "Bearer internal-token"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_accounts"], 2)
        self.assertEqual(body["active_subscriptions"], 1)
        self.assertEqual(body["accounts_with_telegram"], 1)
        self.assertEqual(body["blocked_accounts"], 1)
        self.assertEqual(body["new_accounts_last_7d"], 2)


if __name__ == "__main__":
    unittest.main()
