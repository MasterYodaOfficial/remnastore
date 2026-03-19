from __future__ import annotations

from datetime import UTC, datetime, timedelta
import tempfile
import unittest
from pathlib import Path
import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    Account,
    AccountStatus,
    AdminActionLog,
    Broadcast,
    BroadcastAudiencePreset,
    BroadcastChannel,
    BroadcastContentType,
    BroadcastDelivery,
    BroadcastDeliveryStatus,
    BroadcastRun,
    BroadcastRunType,
    BroadcastStatus,
    Notification,
    NotificationType,
    Payment,
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

    async def test_create_broadcast_draft_excludes_telegram_bot_blocked_accounts_from_telegram_estimate(self) -> None:
        token = await self._create_admin_token()
        now = datetime.now(UTC)

        async with self._session_factory() as session:
            session.add_all(
                [
                    Account(email="active@example.com", status=AccountStatus.ACTIVE, telegram_id=111001),
                    Account(
                        email="bot-blocked@example.com",
                        status=AccountStatus.ACTIVE,
                        telegram_id=222002,
                        telegram_bot_blocked_at=now,
                    ),
                ]
            )
            await session.commit()

        response = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Telegram reachability",
                "title": "Проверка Telegram",
                "body_html": "Только доступным в Telegram",
                "content_type": "text",
                "channels": ["in_app", "telegram"],
                "buttons": [],
                "audience": {"segment": "all", "exclude_blocked": True},
            },
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["estimated_total_accounts"], 2)
        self.assertEqual(body["estimated_in_app_recipients"], 2)
        self.assertEqual(body["estimated_telegram_recipients"], 1)

    async def test_manage_broadcast_audience_presets_crud(self) -> None:
        token = await self._create_admin_token()

        create_response = await self.client.post(
            "/api/v1/admin/broadcasts/audiences",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "  Expired 30+  ",
                "description": "  Win-back после долгого перерыва  ",
                "audience": {
                    "segment": "expired",
                    "exclude_blocked": True,
                    "subscription_expired_from_days": 30,
                    "subscription_expired_to_days": 90,
                    "cooldown_days": 7,
                    "cooldown_key": "WinBack_Expired",
                    "telegram_quiet_hours_start": "22:00",
                    "telegram_quiet_hours_end": "09:00",
                },
            },
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertEqual(created["name"], "Expired 30+")
        self.assertEqual(created["description"], "Win-back после долгого перерыва")
        self.assertEqual(created["audience"]["segment"], "expired")
        self.assertEqual(created["audience"]["subscription_expired_from_days"], 30)
        self.assertEqual(created["audience"]["subscription_expired_to_days"], 90)
        self.assertEqual(created["audience"]["cooldown_days"], 7)
        self.assertEqual(created["audience"]["cooldown_key"], "winback_expired")
        self.assertEqual(created["audience"]["telegram_quiet_hours_start"], "22:00")
        self.assertEqual(created["audience"]["telegram_quiet_hours_end"], "09:00")
        preset_id = created["id"]

        list_response = await self.client.get(
            "/api/v1/admin/broadcasts/audiences?limit=50&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(list_response.status_code, 200)
        listed = list_response.json()
        self.assertEqual(listed["total"], 1)
        self.assertEqual(len(listed["items"]), 1)
        self.assertEqual(listed["items"][0]["id"], preset_id)

        update_response = await self.client.put(
            f"/api/v1/admin/broadcasts/audiences/{preset_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Payment recovery",
                "description": None,
                "audience": {
                    "segment": "failed_payment",
                    "exclude_blocked": True,
                    "failed_payment_within_last_days": 14,
                    "cooldown_days": 3,
                    "cooldown_key": "Payment Recovery",
                },
            },
        )
        self.assertEqual(update_response.status_code, 200)
        updated = update_response.json()
        self.assertEqual(updated["id"], preset_id)
        self.assertEqual(updated["name"], "Payment recovery")
        self.assertIsNone(updated["description"])
        self.assertEqual(updated["audience"]["segment"], "failed_payment")
        self.assertEqual(updated["audience"]["failed_payment_within_last_days"], 14)
        self.assertEqual(updated["audience"]["cooldown_days"], 3)
        self.assertEqual(updated["audience"]["cooldown_key"], "payment recovery")
        self.assertIsNone(updated["audience"]["telegram_quiet_hours_start"])
        self.assertIsNone(updated["audience"]["telegram_quiet_hours_end"])

        delete_response = await self.client.delete(
            f"/api/v1/admin/broadcasts/audiences/{preset_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(delete_response.status_code, 204)

        async with self._session_factory() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(BroadcastAudiencePreset)), 0)
            self.assertEqual(await session.scalar(select(func.count()).select_from(AdminActionLog)), 3)

    async def test_estimate_broadcast_audience_manual_list_deduplicates_and_excludes_blocked(self) -> None:
        token = await self._create_admin_token()

        selected_by_all_identifiers = Account(
            email="target@example.com",
            status=AccountStatus.ACTIVE,
            telegram_id=111001,
        )
        selected_by_email = Account(
            email="email-match@example.com",
            status=AccountStatus.ACTIVE,
        )
        selected_by_telegram = Account(
            email=None,
            status=AccountStatus.ACTIVE,
            telegram_id=333003,
        )
        blocked_selected = Account(
            email="blocked@example.com",
            status=AccountStatus.BLOCKED,
            telegram_id=444004,
        )

        async with self._session_factory() as session:
            session.add_all(
                [
                    selected_by_all_identifiers,
                    selected_by_email,
                    selected_by_telegram,
                    blocked_selected,
                ]
            )
            await session.commit()

        response = await self.client.post(
            "/api/v1/admin/broadcasts/estimate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "channels": ["in_app", "telegram"],
                "audience": {
                    "segment": "manual_list",
                    "exclude_blocked": True,
                    "manual_account_ids": [str(selected_by_all_identifiers.id)],
                    "manual_emails": [
                        "target@example.com",
                        "email-match@example.com",
                        "blocked@example.com",
                    ],
                    "manual_telegram_ids": [111001, 333003, 444004],
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["estimated_total_accounts"], 3)
        self.assertEqual(body["estimated_in_app_recipients"], 3)
        self.assertEqual(body["estimated_telegram_recipients"], 2)
        self.assertEqual(body["audience"]["segment"], "manual_list")
        self.assertEqual(body["audience"]["manual_account_ids"], [str(selected_by_all_identifiers.id)])
        self.assertEqual(
            body["audience"]["manual_emails"],
            ["target@example.com", "email-match@example.com", "blocked@example.com"],
        )
        self.assertEqual(body["audience"]["manual_telegram_ids"], [111001, 333003, 444004])

    async def test_estimate_broadcast_audience_inactive_accounts_respects_last_seen_filters(self) -> None:
        token = await self._create_admin_token()
        now = datetime.now(UTC)

        old_seen = Account(
            email="old-seen@example.com",
            status=AccountStatus.ACTIVE,
            telegram_id=111001,
            last_seen_at=now - timedelta(days=30),
        )
        recent_seen = Account(
            email="recent-seen@example.com",
            status=AccountStatus.ACTIVE,
            telegram_id=222002,
            last_seen_at=now - timedelta(days=2),
        )
        never_seen = Account(
            email="never-seen@example.com",
            status=AccountStatus.ACTIVE,
            telegram_id=None,
            last_seen_at=None,
        )
        blocked_old = Account(
            email="blocked-old@example.com",
            status=AccountStatus.BLOCKED,
            telegram_id=333003,
            last_seen_at=now - timedelta(days=45),
        )

        async with self._session_factory() as session:
            session.add_all([old_seen, recent_seen, never_seen, blocked_old])
            await session.commit()

        response = await self.client.post(
            "/api/v1/admin/broadcasts/estimate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "channels": ["in_app", "telegram"],
                "audience": {
                    "segment": "inactive_accounts",
                    "exclude_blocked": True,
                    "last_seen_older_than_days": 14,
                    "include_never_seen": True,
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["estimated_total_accounts"], 2)
        self.assertEqual(body["estimated_in_app_recipients"], 2)
        self.assertEqual(body["estimated_telegram_recipients"], 1)
        self.assertEqual(body["audience"]["segment"], "inactive_accounts")
        self.assertEqual(body["audience"]["last_seen_older_than_days"], 14)
        self.assertTrue(body["audience"]["include_never_seen"])

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

    async def test_estimate_broadcast_audience_abandoned_checkout_uses_latest_direct_plan_payment(self) -> None:
        token = await self._create_admin_token()
        now = datetime.now(UTC)

        abandoned_account = Account(
            email="abandoned@example.com",
            status=AccountStatus.ACTIVE,
            telegram_id=111001,
        )
        too_recent_account = Account(
            email="recent@example.com",
            status=AccountStatus.ACTIVE,
            telegram_id=222002,
        )
        wrong_flow_account = Account(
            email="topup@example.com",
            status=AccountStatus.ACTIVE,
            telegram_id=333003,
        )
        converted_account = Account(
            email="converted@example.com",
            status=AccountStatus.ACTIVE,
            telegram_id=444004,
        )

        async with self._session_factory() as session:
            session.add_all(
                [
                    abandoned_account,
                    too_recent_account,
                    wrong_flow_account,
                    converted_account,
                ]
            )
            await session.flush()
            session.add_all(
                [
                    Payment(
                        account_id=abandoned_account.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                        status=PaymentStatus.PENDING,
                        amount=1000,
                        currency="RUB",
                        provider_payment_id="abandoned-pending",
                        plan_code="plan_1m",
                        created_at=now - timedelta(hours=2),
                    ),
                    Payment(
                        account_id=too_recent_account.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                        status=PaymentStatus.PENDING,
                        amount=1000,
                        currency="RUB",
                        provider_payment_id="recent-pending",
                        plan_code="plan_1m",
                        created_at=now - timedelta(minutes=10),
                    ),
                    Payment(
                        account_id=wrong_flow_account.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.WALLET_TOPUP,
                        status=PaymentStatus.PENDING,
                        amount=1000,
                        currency="RUB",
                        provider_payment_id="topup-pending",
                        created_at=now - timedelta(hours=3),
                    ),
                    Payment(
                        account_id=converted_account.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                        status=PaymentStatus.PENDING,
                        amount=1000,
                        currency="RUB",
                        provider_payment_id="converted-pending",
                        plan_code="plan_1m",
                        created_at=now - timedelta(hours=3),
                    ),
                    Payment(
                        account_id=converted_account.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                        status=PaymentStatus.SUCCEEDED,
                        amount=1000,
                        currency="RUB",
                        provider_payment_id="converted-success",
                        plan_code="plan_1m",
                        finalized_at=now - timedelta(hours=1),
                        created_at=now - timedelta(hours=1),
                    ),
                ]
            )
            await session.commit()

        response = await self.client.post(
            "/api/v1/admin/broadcasts/estimate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "channels": ["in_app", "telegram"],
                "audience": {
                    "segment": "abandoned_checkout",
                    "exclude_blocked": True,
                    "pending_payment_older_than_minutes": 30,
                    "pending_payment_within_last_days": 7,
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["estimated_total_accounts"], 1)
        self.assertEqual(body["estimated_in_app_recipients"], 1)
        self.assertEqual(body["estimated_telegram_recipients"], 1)
        self.assertEqual(body["audience"]["segment"], "abandoned_checkout")
        self.assertEqual(body["audience"]["pending_payment_older_than_minutes"], 30)
        self.assertEqual(body["audience"]["pending_payment_within_last_days"], 7)

    async def test_estimate_broadcast_audience_expired_window_filters_old_subscriptions(self) -> None:
        token = await self._create_admin_token()
        now = datetime.now(UTC)

        async with self._session_factory() as session:
            session.add_all(
                [
                    Account(
                        email="expired-recent@example.com",
                        status=AccountStatus.ACTIVE,
                        telegram_id=111001,
                        subscription_expires_at=now - timedelta(days=2),
                    ),
                    Account(
                        email="expired-40d@example.com",
                        status=AccountStatus.ACTIVE,
                        telegram_id=222002,
                        subscription_expires_at=now - timedelta(days=40),
                    ),
                    Account(
                        email="expired-120d@example.com",
                        status=AccountStatus.ACTIVE,
                        telegram_id=333003,
                        subscription_expires_at=now - timedelta(days=120),
                    ),
                ]
            )
            await session.commit()

        response = await self.client.post(
            "/api/v1/admin/broadcasts/estimate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "channels": ["in_app", "telegram"],
                "audience": {
                    "segment": "expired",
                    "exclude_blocked": True,
                    "subscription_expired_from_days": 30,
                    "subscription_expired_to_days": 90,
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["estimated_total_accounts"], 1)
        self.assertEqual(body["estimated_in_app_recipients"], 1)
        self.assertEqual(body["estimated_telegram_recipients"], 1)
        self.assertEqual(body["audience"]["subscription_expired_from_days"], 30)
        self.assertEqual(body["audience"]["subscription_expired_to_days"], 90)

    async def test_preview_broadcast_audience_returns_match_reasons_and_delivery_gaps(self) -> None:
        token = await self._create_admin_token()
        now = datetime.now(UTC)

        ready_account = Account(
            email="ready@example.com",
            display_name="Готов",
            status=AccountStatus.ACTIVE,
            telegram_id=111001,
        )
        missing_telegram_account = Account(
            email="missing-telegram@example.com",
            display_name="Без Telegram",
            status=AccountStatus.ACTIVE,
        )
        blocked_telegram_account = Account(
            email="blocked-telegram@example.com",
            display_name="Заблокировал бота",
            status=AccountStatus.ACTIVE,
            telegram_id=333003,
            telegram_bot_blocked_at=now - timedelta(days=1),
        )

        async with self._session_factory() as session:
            session.add_all([ready_account, missing_telegram_account, blocked_telegram_account])
            await session.flush()
            session.add_all(
                [
                    Payment(
                        account_id=ready_account.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                        status=PaymentStatus.PENDING,
                        amount=1000,
                        currency="RUB",
                        provider_payment_id="ready-pending",
                        plan_code="plan_1m",
                        created_at=now - timedelta(hours=2),
                    ),
                    Payment(
                        account_id=missing_telegram_account.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                        status=PaymentStatus.PENDING,
                        amount=1000,
                        currency="RUB",
                        provider_payment_id="missing-telegram-pending",
                        plan_code="plan_1m",
                        created_at=now - timedelta(hours=3),
                    ),
                    Payment(
                        account_id=blocked_telegram_account.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                        status=PaymentStatus.PENDING,
                        amount=1000,
                        currency="RUB",
                        provider_payment_id="blocked-telegram-pending",
                        plan_code="plan_1m",
                        created_at=now - timedelta(hours=4),
                    ),
                ]
            )
            await session.commit()

        response = await self.client.post(
            "/api/v1/admin/broadcasts/preview",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "channels": ["telegram"],
                "audience": {
                    "segment": "abandoned_checkout",
                    "exclude_blocked": True,
                    "pending_payment_older_than_minutes": 30,
                    "pending_payment_within_last_days": 7,
                },
                "limit": 10,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_accounts"], 3)
        self.assertEqual(body["preview_count"], 3)
        self.assertFalse(body["has_more"])

        items_by_email = {item["email"]: item for item in body["items"]}

        ready_item = items_by_email["ready@example.com"]
        self.assertEqual(ready_item["delivery_channels"], ["telegram"])
        self.assertEqual(ready_item["delivery_notes"], [])
        self.assertTrue(any("не завершена" in reason for reason in ready_item["match_reasons"]))

        missing_telegram_item = items_by_email["missing-telegram@example.com"]
        self.assertEqual(missing_telegram_item["delivery_channels"], [])
        self.assertTrue(any("не привязан" in note for note in missing_telegram_item["delivery_notes"]))
        self.assertTrue(any("не будет доставки" in note for note in missing_telegram_item["delivery_notes"]))

        blocked_telegram_item = items_by_email["blocked-telegram@example.com"]
        self.assertEqual(blocked_telegram_item["delivery_channels"], [])
        self.assertTrue(any("бот заблокирован" in note for note in blocked_telegram_item["delivery_notes"]))

    async def test_preview_manual_list_audience_returns_resolution_diagnostics(self) -> None:
        token = await self._create_admin_token()
        now = datetime.now(UTC)
        admin_id = uuid.uuid4()

        eligible_account = Account(
            email="eligible-manual@example.com",
            display_name="Можно отправлять",
            status=AccountStatus.ACTIVE,
            telegram_id=111001,
        )
        blocked_account = Account(
            email="blocked-manual-preview@example.com",
            display_name="Заблокирован",
            status=AccountStatus.BLOCKED,
            telegram_id=222002,
        )
        cooled_account = Account(
            email="cooled-manual@example.com",
            display_name="Недавно получил",
            status=AccountStatus.ACTIVE,
            telegram_id=333003,
        )

        async with self._session_factory() as session:
            session.add_all([eligible_account, blocked_account, cooled_account])
            await session.flush()

            prior_broadcast = Broadcast(
                name="prior-manual-cooldown",
                title="Предыдущая manual-кампания",
                body_html="Историческая manual-рассылка",
                content_type=BroadcastContentType.TEXT,
                channels=[BroadcastChannel.IN_APP.value],
                buttons=[],
                audience={
                    "segment": "manual_list",
                    "exclude_blocked": True,
                    "manual_emails": ["cooled-manual@example.com"],
                    "cooldown_days": 7,
                    "cooldown_key": "manual_recovery",
                },
                status=BroadcastStatus.COMPLETED,
                estimated_total_accounts=1,
                estimated_in_app_recipients=1,
                estimated_telegram_recipients=0,
                created_by_admin_id=admin_id,
                updated_by_admin_id=admin_id,
                launched_at=now - timedelta(days=1),
                completed_at=now - timedelta(days=1),
            )
            session.add(prior_broadcast)
            await session.flush()

            prior_run = BroadcastRun(
                broadcast_id=prior_broadcast.id,
                run_type=BroadcastRunType.SEND_NOW,
                triggered_by_admin_id=admin_id,
                snapshot_total_accounts=1,
                snapshot_in_app_targets=1,
                snapshot_telegram_targets=0,
                started_at=now - timedelta(days=1),
                completed_at=now - timedelta(days=1),
            )
            session.add(prior_run)
            await session.flush()

            session.add(
                BroadcastDelivery(
                    run_id=prior_run.id,
                    broadcast_id=prior_broadcast.id,
                    account_id=cooled_account.id,
                    channel=BroadcastChannel.IN_APP,
                    status=BroadcastDeliveryStatus.DELIVERED,
                    attempts_count=1,
                    last_attempt_at=now - timedelta(days=1),
                    delivered_at=now - timedelta(days=1),
                )
            )
            await session.commit()

        response = await self.client.post(
            "/api/v1/admin/broadcasts/preview",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "channels": ["in_app", "telegram"],
                "audience": {
                    "segment": "manual_list",
                    "exclude_blocked": True,
                    "manual_emails": [
                        "eligible-manual@example.com",
                        "blocked-manual-preview@example.com",
                        "cooled-manual@example.com",
                        "missing-manual@example.com",
                    ],
                    "manual_telegram_ids": [999999],
                    "cooldown_days": 7,
                    "cooldown_key": "manual_recovery",
                },
                "limit": 10,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_accounts"], 1)
        self.assertEqual(body["preview_count"], 1)
        self.assertFalse(body["has_more"])
        self.assertEqual(body["items"][0]["email"], "eligible-manual@example.com")

        diagnostics = body["manual_list_diagnostics"]
        self.assertIsNotNone(diagnostics)
        self.assertEqual(diagnostics["requested_emails"], 4)
        self.assertEqual(diagnostics["requested_telegram_ids"], 1)
        self.assertEqual(diagnostics["matched_accounts"], 3)
        self.assertEqual(diagnostics["final_accounts"], 1)
        self.assertEqual(diagnostics["unresolved_emails_count"], 1)
        self.assertEqual(diagnostics["unresolved_emails_sample"], ["missing-manual@example.com"])
        self.assertEqual(diagnostics["unresolved_telegram_ids_count"], 1)
        self.assertEqual(diagnostics["unresolved_telegram_ids_sample"], [999999])
        self.assertEqual(diagnostics["excluded_accounts_count"], 2)
        self.assertEqual(diagnostics["excluded_blocked_count"], 1)
        self.assertEqual(diagnostics["excluded_cooldown_count"], 1)
        excluded_by_email = {
            item["email"]: item for item in diagnostics["excluded_accounts_sample"]
        }
        self.assertIn("blocked-manual-preview@example.com", excluded_by_email)
        self.assertIn("cooled-manual@example.com", excluded_by_email)
        self.assertIn("blocked", excluded_by_email["blocked-manual-preview@example.com"]["reasons"])
        self.assertIn("cooldown", excluded_by_email["cooled-manual@example.com"]["reasons"])

    async def test_estimate_broadcast_audience_respects_cooldown_family(self) -> None:
        token = await self._create_admin_token()
        now = datetime.now(UTC)
        admin_id = uuid.uuid4()

        recent_account = Account(
            email="recent-contact@example.com",
            status=AccountStatus.ACTIVE,
            telegram_id=111001,
        )
        old_account = Account(
            email="old-contact@example.com",
            status=AccountStatus.ACTIVE,
            telegram_id=222002,
        )

        async with self._session_factory() as session:
            session.add_all([recent_account, old_account])
            await session.flush()

            for index, (account, delivered_at) in enumerate(
                [
                    (recent_account, now - timedelta(days=2)),
                    (old_account, now - timedelta(days=12)),
                ],
                start=1,
            ):
                prior_broadcast = Broadcast(
                    name=f"prior-{index}",
                    title=f"Prior {index}",
                    body_html="Историческая рассылка",
                    content_type=BroadcastContentType.TEXT,
                    channels=[BroadcastChannel.IN_APP.value],
                    buttons=[],
                    audience={
                        "segment": "all",
                        "exclude_blocked": True,
                        "cooldown_days": 7,
                        "cooldown_key": "payment_recovery",
                    },
                    status=BroadcastStatus.COMPLETED,
                    estimated_total_accounts=1,
                    estimated_in_app_recipients=1,
                    estimated_telegram_recipients=0,
                    created_by_admin_id=admin_id,
                    updated_by_admin_id=admin_id,
                    launched_at=delivered_at,
                    completed_at=delivered_at,
                )
                session.add(prior_broadcast)
                await session.flush()

                prior_run = BroadcastRun(
                    broadcast_id=prior_broadcast.id,
                    run_type=BroadcastRunType.SEND_NOW,
                    triggered_by_admin_id=admin_id,
                    snapshot_total_accounts=1,
                    snapshot_in_app_targets=1,
                    snapshot_telegram_targets=0,
                    started_at=delivered_at,
                    completed_at=delivered_at,
                )
                session.add(prior_run)
                await session.flush()

                session.add(
                    BroadcastDelivery(
                        run_id=prior_run.id,
                        broadcast_id=prior_broadcast.id,
                        account_id=account.id,
                        channel=BroadcastChannel.IN_APP,
                        status=BroadcastDeliveryStatus.DELIVERED,
                        attempts_count=1,
                        last_attempt_at=delivered_at,
                        delivered_at=delivered_at,
                    )
                )

            await session.commit()

        response = await self.client.post(
            "/api/v1/admin/broadcasts/estimate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "channels": ["in_app", "telegram"],
                "audience": {
                    "segment": "all",
                    "exclude_blocked": True,
                    "cooldown_days": 7,
                    "cooldown_key": "payment_recovery",
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["estimated_total_accounts"], 1)
        self.assertEqual(body["estimated_in_app_recipients"], 1)
        self.assertEqual(body["estimated_telegram_recipients"], 1)
        self.assertEqual(body["audience"]["cooldown_days"], 7)
        self.assertEqual(body["audience"]["cooldown_key"], "payment_recovery")

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
                        telegram_id=222002,
                        telegram_bot_blocked_at=datetime.now(UTC),
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
        self.assertEqual(body["latest_run"]["snapshot_telegram_targets"], 1)
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

    async def test_send_now_broadcast_paid_before_not_active_now_targets_only_lapsed_payers(self) -> None:
        token = await self._create_admin_token()
        now = datetime.now(UTC)

        lapsed_paid = Account(
            email="lapsed-paid@example.com",
            display_name="Вернется",
            status=AccountStatus.ACTIVE,
            telegram_id=111001,
            subscription_expires_at=now - timedelta(days=5),
        )
        active_paid = Account(
            email="active-paid@example.com",
            display_name="Активный",
            status=AccountStatus.ACTIVE,
            telegram_id=222002,
            subscription_expires_at=now + timedelta(days=5),
        )
        never_paid = Account(
            email="never-paid@example.com",
            display_name="Без оплаты",
            status=AccountStatus.ACTIVE,
            telegram_id=333003,
            subscription_expires_at=now - timedelta(days=10),
        )

        async with self._session_factory() as session:
            session.add_all([lapsed_paid, active_paid, never_paid])
            await session.flush()
            session.add_all(
                [
                    Payment(
                        account_id=lapsed_paid.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                        status=PaymentStatus.SUCCEEDED,
                        amount=1000,
                        currency="RUB",
                        provider_payment_id="lapsed-success",
                        plan_code="plan_1m",
                        finalized_at=now - timedelta(days=40),
                        created_at=now - timedelta(days=40),
                    ),
                    Payment(
                        account_id=active_paid.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                        status=PaymentStatus.SUCCEEDED,
                        amount=1000,
                        currency="RUB",
                        provider_payment_id="active-success",
                        plan_code="plan_1m",
                        finalized_at=now - timedelta(days=10),
                        created_at=now - timedelta(days=10),
                    ),
                ]
            )
            await session.commit()

        create_response = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Lapsed payers only",
                "title": "Вернитесь",
                "body_html": "Только для тех, кто раньше уже платил",
                "content_type": "text",
                "channels": ["in_app", "telegram"],
                "buttons": [],
                "audience": {"segment": "paid_before_not_active_now", "exclude_blocked": True},
            },
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["estimated_total_accounts"], 1)
        broadcast_id = create_response.json()["id"]

        launch_response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/send-now",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "comment": "Только по ушедшим плательщикам",
                "idempotency_key": "broadcast-send-now-lapsed-paid",
            },
        )
        self.assertEqual(launch_response.status_code, 200)
        body = launch_response.json()
        self.assertEqual(body["latest_run"]["snapshot_total_accounts"], 1)
        self.assertEqual(body["latest_run"]["snapshot_in_app_targets"], 1)
        self.assertEqual(body["latest_run"]["snapshot_telegram_targets"], 1)
        self.assertEqual(body["latest_run"]["total_deliveries"], 2)

        async with self._session_factory() as session:
            result = await self._broadcasts_service.process_pending_broadcast_deliveries(
                session,
                limit=20,
            )
            await session.commit()

        self.assertEqual(result.processed, 2)
        self.assertEqual(result.delivered, 2)
        self.assertEqual(len(self._fake_telegram_client.sent_messages), 1)
        self.assertEqual(self._fake_telegram_client.sent_messages[0]["telegram_id"], 111001)

        async with self._session_factory() as session:
            notifications = list(
                (
                    await session.execute(
                        select(Notification).where(Notification.type == NotificationType.BROADCAST)
                    )
                ).scalars().all()
            )
            self.assertEqual(len(notifications), 1)

    async def test_send_now_broadcast_manual_list_targets_only_selected_accounts(self) -> None:
        token = await self._create_admin_token()

        selected_by_email = Account(
            email="manual-email@example.com",
            display_name="По email",
            status=AccountStatus.ACTIVE,
        )
        selected_by_telegram = Account(
            email=None,
            display_name="По Telegram",
            status=AccountStatus.ACTIVE,
            telegram_id=222002,
        )
        blocked_selected = Account(
            email="blocked-manual@example.com",
            display_name="Блок",
            status=AccountStatus.BLOCKED,
            telegram_id=333003,
        )
        non_selected = Account(
            email="other@example.com",
            display_name="Не выбран",
            status=AccountStatus.ACTIVE,
            telegram_id=444004,
        )

        async with self._session_factory() as session:
            session.add_all([selected_by_email, selected_by_telegram, blocked_selected, non_selected])
            await session.commit()

        create_response = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Manual list runtime",
                "title": "Точечная рассылка",
                "body_html": "Только для выбранного списка",
                "content_type": "text",
                "channels": ["in_app", "telegram"],
                "buttons": [],
                "audience": {
                    "segment": "manual_list",
                    "exclude_blocked": True,
                    "manual_emails": ["manual-email@example.com", "blocked-manual@example.com"],
                    "manual_telegram_ids": [222002],
                },
            },
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["estimated_total_accounts"], 2)
        self.assertEqual(create_response.json()["estimated_in_app_recipients"], 2)
        self.assertEqual(create_response.json()["estimated_telegram_recipients"], 1)
        broadcast_id = create_response.json()["id"]

        launch_response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/send-now",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "comment": "Точечная кампания по списку",
                "idempotency_key": "broadcast-send-now-manual-list",
            },
        )
        self.assertEqual(launch_response.status_code, 200)
        body = launch_response.json()
        self.assertEqual(body["latest_run"]["snapshot_total_accounts"], 2)
        self.assertEqual(body["latest_run"]["snapshot_in_app_targets"], 2)
        self.assertEqual(body["latest_run"]["snapshot_telegram_targets"], 1)
        self.assertEqual(body["latest_run"]["total_deliveries"], 3)

        async with self._session_factory() as session:
            result = await self._broadcasts_service.process_pending_broadcast_deliveries(
                session,
                limit=20,
            )
            await session.commit()

        self.assertEqual(result.processed, 3)
        self.assertEqual(result.delivered, 3)
        self.assertEqual(len(self._fake_telegram_client.sent_messages), 1)
        self.assertEqual(self._fake_telegram_client.sent_messages[0]["telegram_id"], 222002)

        async with self._session_factory() as session:
            notifications = list(
                (
                    await session.execute(
                        select(Notification).where(Notification.type == NotificationType.BROADCAST)
                    )
                ).scalars().all()
            )
            self.assertEqual(len(notifications), 2)

    async def test_send_now_broadcast_inactive_paid_users_targets_only_dormant_payers(self) -> None:
        token = await self._create_admin_token()
        now = datetime.now(UTC)

        dormant_paid = Account(
            email="dormant-paid@example.com",
            display_name="Спящий плательщик",
            status=AccountStatus.ACTIVE,
            telegram_id=111001,
            last_seen_at=now - timedelta(days=30),
        )
        never_seen_paid = Account(
            email="never-seen-paid@example.com",
            display_name="Ни разу не зашел",
            status=AccountStatus.ACTIVE,
            telegram_id=None,
            last_seen_at=None,
        )
        recent_paid = Account(
            email="recent-paid@example.com",
            display_name="Недавно был",
            status=AccountStatus.ACTIVE,
            telegram_id=222002,
            last_seen_at=now - timedelta(days=2),
        )
        dormant_never_paid = Account(
            email="dormant-free@example.com",
            display_name="Не платил",
            status=AccountStatus.ACTIVE,
            telegram_id=333003,
            last_seen_at=now - timedelta(days=45),
        )

        async with self._session_factory() as session:
            session.add_all([dormant_paid, never_seen_paid, recent_paid, dormant_never_paid])
            await session.flush()
            session.add_all(
                [
                    Payment(
                        account_id=dormant_paid.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                        status=PaymentStatus.SUCCEEDED,
                        amount=1000,
                        currency="RUB",
                        provider_payment_id="dormant-paid-success",
                        plan_code="plan_1m",
                        finalized_at=now - timedelta(days=60),
                        created_at=now - timedelta(days=60),
                    ),
                    Payment(
                        account_id=never_seen_paid.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                        status=PaymentStatus.SUCCEEDED,
                        amount=1000,
                        currency="RUB",
                        provider_payment_id="never-seen-paid-success",
                        plan_code="plan_1m",
                        finalized_at=now - timedelta(days=20),
                        created_at=now - timedelta(days=20),
                    ),
                    Payment(
                        account_id=recent_paid.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                        status=PaymentStatus.SUCCEEDED,
                        amount=1000,
                        currency="RUB",
                        provider_payment_id="recent-paid-success",
                        plan_code="plan_1m",
                        finalized_at=now - timedelta(days=10),
                        created_at=now - timedelta(days=10),
                    ),
                ]
            )
            await session.commit()

        create_response = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Inactive paid users",
                "title": "Вернитесь в продукт",
                "body_html": "Только для неактивных плательщиков",
                "content_type": "text",
                "channels": ["in_app", "telegram"],
                "buttons": [],
                "audience": {
                    "segment": "inactive_paid_users",
                    "exclude_blocked": True,
                    "last_seen_older_than_days": 14,
                    "include_never_seen": True,
                },
            },
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["estimated_total_accounts"], 2)
        self.assertEqual(create_response.json()["estimated_in_app_recipients"], 2)
        self.assertEqual(create_response.json()["estimated_telegram_recipients"], 1)
        broadcast_id = create_response.json()["id"]

        launch_response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/send-now",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "comment": "Retention по dormant payers",
                "idempotency_key": "broadcast-send-now-inactive-paid-users",
            },
        )
        self.assertEqual(launch_response.status_code, 200)
        body = launch_response.json()
        self.assertEqual(body["latest_run"]["snapshot_total_accounts"], 2)
        self.assertEqual(body["latest_run"]["snapshot_in_app_targets"], 2)
        self.assertEqual(body["latest_run"]["snapshot_telegram_targets"], 1)
        self.assertEqual(body["latest_run"]["total_deliveries"], 3)

        async with self._session_factory() as session:
            result = await self._broadcasts_service.process_pending_broadcast_deliveries(
                session,
                limit=20,
            )
            await session.commit()

        self.assertEqual(result.processed, 3)
        self.assertEqual(result.delivered, 3)
        self.assertEqual(len(self._fake_telegram_client.sent_messages), 1)
        self.assertEqual(self._fake_telegram_client.sent_messages[0]["telegram_id"], 111001)

        async with self._session_factory() as session:
            notifications = list(
                (
                    await session.execute(
                        select(Notification).where(Notification.type == NotificationType.BROADCAST)
                    )
                ).scalars().all()
            )
            self.assertEqual(len(notifications), 2)

    async def test_send_now_broadcast_respects_cooldown_family(self) -> None:
        token = await self._create_admin_token()
        now = datetime.now(UTC)
        admin_id = uuid.uuid4()

        cooled_account = Account(
            email="cooled@example.com",
            display_name="Недавно получал",
            status=AccountStatus.ACTIVE,
            telegram_id=111001,
        )
        eligible_account = Account(
            email="eligible@example.com",
            display_name="Можно отправлять",
            status=AccountStatus.ACTIVE,
            telegram_id=222002,
        )

        async with self._session_factory() as session:
            session.add_all([cooled_account, eligible_account])
            await session.flush()

            prior_broadcast = Broadcast(
                name="prior-payment-recovery",
                title="Предыдущий recovery",
                body_html="Историческая recovery-рассылка",
                content_type=BroadcastContentType.TEXT,
                channels=[BroadcastChannel.IN_APP.value],
                buttons=[],
                audience={
                    "segment": "all",
                    "exclude_blocked": True,
                    "cooldown_days": 7,
                    "cooldown_key": "payment_recovery",
                },
                status=BroadcastStatus.COMPLETED,
                estimated_total_accounts=1,
                estimated_in_app_recipients=1,
                estimated_telegram_recipients=0,
                created_by_admin_id=admin_id,
                updated_by_admin_id=admin_id,
                launched_at=now - timedelta(days=1),
                completed_at=now - timedelta(days=1),
            )
            session.add(prior_broadcast)
            await session.flush()

            prior_run = BroadcastRun(
                broadcast_id=prior_broadcast.id,
                run_type=BroadcastRunType.SEND_NOW,
                triggered_by_admin_id=admin_id,
                snapshot_total_accounts=1,
                snapshot_in_app_targets=1,
                snapshot_telegram_targets=0,
                started_at=now - timedelta(days=1),
                completed_at=now - timedelta(days=1),
            )
            session.add(prior_run)
            await session.flush()

            session.add(
                BroadcastDelivery(
                    run_id=prior_run.id,
                    broadcast_id=prior_broadcast.id,
                    account_id=cooled_account.id,
                    channel=BroadcastChannel.IN_APP,
                    status=BroadcastDeliveryStatus.DELIVERED,
                    attempts_count=1,
                    last_attempt_at=now - timedelta(days=1),
                    delivered_at=now - timedelta(days=1),
                )
            )
            await session.commit()

        create_response = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Cooldown family test",
                "title": "Recovery",
                "body_html": "Повторная recovery-рассылка",
                "content_type": "text",
                "channels": ["in_app", "telegram"],
                "buttons": [],
                "audience": {
                    "segment": "all",
                    "exclude_blocked": True,
                    "cooldown_days": 7,
                    "cooldown_key": "payment_recovery",
                },
            },
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["estimated_total_accounts"], 1)
        broadcast_id = create_response.json()["id"]

        launch_response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/send-now",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "comment": "Запуск с cooldown family",
                "idempotency_key": "broadcast-send-now-cooldown-family",
            },
        )
        self.assertEqual(launch_response.status_code, 200)
        body = launch_response.json()
        self.assertEqual(body["latest_run"]["snapshot_total_accounts"], 1)
        self.assertEqual(body["latest_run"]["snapshot_in_app_targets"], 1)
        self.assertEqual(body["latest_run"]["snapshot_telegram_targets"], 1)
        self.assertEqual(body["latest_run"]["total_deliveries"], 2)

        async with self._session_factory() as session:
            result = await self._broadcasts_service.process_pending_broadcast_deliveries(
                session,
                limit=20,
            )
            await session.commit()

        self.assertEqual(result.processed, 2)
        self.assertEqual(result.delivered, 2)
        self.assertEqual(len(self._fake_telegram_client.sent_messages), 1)
        self.assertEqual(self._fake_telegram_client.sent_messages[0]["telegram_id"], 222002)

        async with self._session_factory() as session:
            notifications = list(
                (
                    await session.execute(
                        select(Notification).where(Notification.type == NotificationType.BROADCAST)
                    )
                ).scalars().all()
            )
            self.assertEqual(len(notifications), 1)

    async def test_send_now_broadcast_defers_telegram_in_quiet_hours(self) -> None:
        token = await self._create_admin_token()
        quiet_now = datetime(2026, 3, 19, 2, 30, tzinfo=self._broadcasts_service.BROADCAST_TZ)
        active_now = datetime(2026, 3, 19, 9, 5, tzinfo=self._broadcasts_service.BROADCAST_TZ)

        async with self._session_factory() as session:
            session.add(
                Account(
                    email="quiet-hours@example.com",
                    display_name="Тихий час",
                    status=AccountStatus.ACTIVE,
                    telegram_id=111001,
                )
            )
            await session.commit()

        create_response = await self.client.post(
            "/api/v1/admin/broadcasts",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Quiet hours test",
                "title": "Ночная рассылка",
                "body_html": "Проверка quiet hours",
                "content_type": "text",
                "channels": ["in_app", "telegram"],
                "buttons": [],
                "audience": {
                    "segment": "all",
                    "exclude_blocked": True,
                    "telegram_quiet_hours_start": "23:00",
                    "telegram_quiet_hours_end": "08:00",
                },
            },
        )
        self.assertEqual(create_response.status_code, 201)
        broadcast_id = create_response.json()["id"]

        launch_response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/send-now",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "comment": "Запуск с quiet hours",
                "idempotency_key": "broadcast-send-now-quiet-hours",
            },
        )
        self.assertEqual(launch_response.status_code, 200)

        original_now_moscow = self._broadcasts_service._now_moscow
        try:
            self._broadcasts_service._now_moscow = lambda: quiet_now

            async with self._session_factory() as session:
                first_result = await self._broadcasts_service.process_pending_broadcast_deliveries(
                    session,
                    limit=20,
                )
                await session.commit()

            self.assertEqual(first_result.processed, 2)
            self.assertEqual(first_result.delivered, 1)
            self.assertEqual(first_result.scheduled_retry, 1)
            self.assertEqual(len(self._fake_telegram_client.sent_messages), 0)

            async with self._session_factory() as session:
                deliveries = list(
                    (
                        await session.execute(
                            select(BroadcastDelivery).where(BroadcastDelivery.broadcast_id == broadcast_id)
                        )
                    ).scalars().all()
                )
                telegram_delivery = next(item for item in deliveries if item.channel == BroadcastChannel.TELEGRAM)
                in_app_delivery = next(item for item in deliveries if item.channel == BroadcastChannel.IN_APP)

                self.assertEqual(in_app_delivery.status, BroadcastDeliveryStatus.DELIVERED)
                self.assertEqual(telegram_delivery.status, BroadcastDeliveryStatus.PENDING)
                self.assertEqual(telegram_delivery.error_code, "quiet_hours")
                self.assertIsNotNone(telegram_delivery.next_retry_at)

                telegram_delivery.next_retry_at = datetime.now(UTC) - timedelta(minutes=1)
                await session.commit()

            self._broadcasts_service._now_moscow = lambda: active_now

            async with self._session_factory() as session:
                second_result = await self._broadcasts_service.process_pending_broadcast_deliveries(
                    session,
                    limit=20,
                )
                await session.commit()

            self.assertEqual(second_result.processed, 1)
            self.assertEqual(second_result.delivered, 1)
            self.assertEqual(len(self._fake_telegram_client.sent_messages), 1)
            self.assertEqual(self._fake_telegram_client.sent_messages[0]["telegram_id"], 111001)
        finally:
            self._broadcasts_service._now_moscow = original_now_moscow

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

        scheduled_at = datetime.now(UTC) + timedelta(days=1)

        schedule_response = await self.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/schedule",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "scheduled_at": scheduled_at.isoformat(),
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
