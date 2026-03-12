from datetime import UTC, datetime
import tempfile
import unittest
import uuid
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_account
from app.db.base import Base
from app.db.models import (
    Account,
    Notification,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationPriority,
    NotificationType,
)
from app.db.session import get_session
from app.main import create_app
from app.services.notifications import (
    TelegramNotificationDeliveryError,
    create_notification,
    process_pending_telegram_deliveries,
)


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


class FakeTelegramNotificationClient:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str]] = []
        self._error: TelegramNotificationDeliveryError | None = None

    def fail_with(self, error: TelegramNotificationDeliveryError) -> None:
        self._error = error

    async def send_message(self, *, telegram_id: int, text: str) -> str:
        self.sent_messages.append((telegram_id, text))
        if self._error is not None:
            raise self._error
        return "message-1"


class NotificationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "notifications.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._current_account_id: uuid.UUID | None = None

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module
        import app.services.notifications as notifications_service

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()
        self._notifications_service = notifications_service
        self._original_bot_token = notifications_service.settings.telegram_bot_token
        self._original_notification_max_attempts = (
            notifications_service.settings.notification_telegram_max_attempts
        )
        self._original_notification_retry_base_seconds = (
            notifications_service.settings.notification_telegram_retry_base_seconds
        )
        self._original_notification_retry_max_seconds = (
            notifications_service.settings.notification_telegram_retry_max_seconds
        )
        notifications_service.settings.telegram_bot_token = "telegram-token"
        notifications_service.settings.notification_telegram_max_attempts = 3
        notifications_service.settings.notification_telegram_retry_base_seconds = 30
        notifications_service.settings.notification_telegram_retry_max_seconds = 900

        self.app = create_app()

        async def override_get_session():
            async with self._session_factory() as session:
                yield session

        async def override_get_current_account():
            if self._current_account_id is None:
                raise AssertionError("current account is not configured for test request")

            async with self._session_factory() as session:
                account = await session.get(Account, self._current_account_id)
                if account is None:
                    raise AssertionError(f"account not found: {self._current_account_id}")
                return account

        self.app.dependency_overrides[get_session] = override_get_session
        self.app.dependency_overrides[get_current_account] = override_get_current_account
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        self._cache_module._cache = self._original_cache
        self._notifications_service.settings.telegram_bot_token = self._original_bot_token
        self._notifications_service.settings.notification_telegram_max_attempts = (
            self._original_notification_max_attempts
        )
        self._notifications_service.settings.notification_telegram_retry_base_seconds = (
            self._original_notification_retry_base_seconds
        )
        self._notifications_service.settings.notification_telegram_retry_max_seconds = (
            self._original_notification_retry_max_seconds
        )
        await self._engine.dispose()
        self._tmpdir.cleanup()

    async def _create_account(self, **values) -> Account:
        async with self._session_factory() as session:
            account = Account(**values)
            session.add(account)
            await session.commit()
            await session.refresh(account)
            return account

    async def _create_notification(
        self,
        *,
        account_id: uuid.UUID,
        type: NotificationType,
        title: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.INFO,
        dedupe_key: str | None = None,
    ) -> Notification:
        async with self._session_factory() as session:
            notification = await create_notification(
                session,
                account_id=account_id,
                type=type,
                title=title,
                body=body,
                priority=priority,
                dedupe_key=dedupe_key,
            )
            await session.commit()
            await session.refresh(notification)
            return notification

    async def _get_deliveries(self, notification_id: int) -> list[NotificationDelivery]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(NotificationDelivery)
                .where(NotificationDelivery.notification_id == notification_id)
                .order_by(NotificationDelivery.id.asc())
            )
            return list(result.scalars().all())

    async def _get_notification(self, notification_id: int) -> Notification | None:
        async with self._session_factory() as session:
            return await session.get(Notification, notification_id)

    async def test_create_notification_creates_in_app_delivery_and_dedupes(self) -> None:
        account = await self._create_account(email="notify@example.com")

        first = await self._create_notification(
            account_id=account.id,
            type=NotificationType.PAYMENT_SUCCEEDED,
            title="Оплата прошла",
            body="Платеж успешно завершен.",
            priority=NotificationPriority.SUCCESS,
            dedupe_key="payment_succeeded:1",
        )
        second = await self._create_notification(
            account_id=account.id,
            type=NotificationType.PAYMENT_SUCCEEDED,
            title="Оплата прошла",
            body="Платеж успешно завершен.",
            priority=NotificationPriority.SUCCESS,
            dedupe_key="payment_succeeded:1",
        )

        self.assertEqual(first.id, second.id)
        deliveries = await self._get_deliveries(first.id)
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].channel, NotificationChannel.IN_APP)
        self.assertEqual(deliveries[0].status, NotificationDeliveryStatus.DELIVERED)
        self.assertEqual(deliveries[0].attempts_count, 1)
        self.assertIsNotNone(deliveries[0].delivered_at)

    async def test_create_notification_adds_pending_telegram_delivery_for_linked_account(self) -> None:
        account = await self._create_account(
            email="notify-telegram@example.com",
            telegram_id=758107031,
        )

        notification = await self._create_notification(
            account_id=account.id,
            type=NotificationType.PAYMENT_SUCCEEDED,
            title="Оплата прошла",
            body="Платеж успешно завершен.",
            priority=NotificationPriority.SUCCESS,
        )

        deliveries = await self._get_deliveries(notification.id)
        self.assertEqual(len(deliveries), 2)
        self.assertEqual(deliveries[0].channel, NotificationChannel.IN_APP)
        self.assertEqual(deliveries[0].status, NotificationDeliveryStatus.DELIVERED)
        self.assertEqual(deliveries[1].channel, NotificationChannel.TELEGRAM)
        self.assertEqual(deliveries[1].status, NotificationDeliveryStatus.PENDING)
        self.assertEqual(deliveries[1].attempts_count, 0)
        self.assertIsNone(deliveries[1].next_retry_at)

    async def test_process_pending_telegram_deliveries_marks_delivery_delivered(self) -> None:
        account = await self._create_account(
            email="telegram-deliver@example.com",
            telegram_id=758107031,
        )
        notification = await self._create_notification(
            account_id=account.id,
            type=NotificationType.PAYMENT_SUCCEEDED,
            title="Оплата прошла",
            body="Платеж успешно завершен.",
            priority=NotificationPriority.SUCCESS,
        )

        client = FakeTelegramNotificationClient()
        async with self._session_factory() as session:
            result = await process_pending_telegram_deliveries(
                session,
                limit=10,
                client=client,
            )
            await session.commit()

        self.assertEqual(result.processed, 1)
        self.assertEqual(result.delivered, 1)
        self.assertEqual(result.scheduled_retry, 0)
        self.assertEqual(result.terminal_failed, 0)
        self.assertEqual(client.sent_messages, [(758107031, "Оплата прошла\n\nПлатеж успешно завершен.")])

        deliveries = await self._get_deliveries(notification.id)
        telegram_delivery = next(
            delivery for delivery in deliveries if delivery.channel == NotificationChannel.TELEGRAM
        )
        self.assertEqual(telegram_delivery.status, NotificationDeliveryStatus.DELIVERED)
        self.assertEqual(telegram_delivery.attempts_count, 1)
        self.assertEqual(telegram_delivery.provider_message_id, "message-1")
        self.assertIsNotNone(telegram_delivery.delivered_at)
        self.assertIsNone(telegram_delivery.next_retry_at)

    async def test_process_pending_telegram_deliveries_schedules_retry_for_retryable_error(self) -> None:
        account = await self._create_account(
            email="telegram-retry@example.com",
            telegram_id=758107031,
        )
        notification = await self._create_notification(
            account_id=account.id,
            type=NotificationType.PAYMENT_FAILED,
            title="Оплата не завершена",
            body="Попробуйте еще раз.",
            priority=NotificationPriority.ERROR,
        )

        client = FakeTelegramNotificationClient()
        client.fail_with(
            TelegramNotificationDeliveryError(
                "temporary network issue",
                code="http_error",
                retryable=True,
            )
        )

        async with self._session_factory() as session:
            result = await process_pending_telegram_deliveries(
                session,
                limit=10,
                client=client,
            )
            await session.commit()

        self.assertEqual(result.processed, 1)
        self.assertEqual(result.delivered, 0)
        self.assertEqual(result.scheduled_retry, 1)
        self.assertEqual(result.terminal_failed, 0)

        deliveries = await self._get_deliveries(notification.id)
        telegram_delivery = next(
            delivery for delivery in deliveries if delivery.channel == NotificationChannel.TELEGRAM
        )
        self.assertEqual(telegram_delivery.status, NotificationDeliveryStatus.FAILED)
        self.assertEqual(telegram_delivery.attempts_count, 1)
        self.assertEqual(telegram_delivery.error_code, "http_error")
        self.assertEqual(telegram_delivery.error_message, "temporary network issue")
        self.assertIsNotNone(telegram_delivery.next_retry_at)

    async def test_list_notifications_returns_unread_count_and_filter(self) -> None:
        account = await self._create_account(email="list@example.com")
        self._current_account_id = account.id

        oldest = await self._create_notification(
            account_id=account.id,
            type=NotificationType.PAYMENT_SUCCEEDED,
            title="Первое",
            body="Первое уведомление",
        )
        middle = await self._create_notification(
            account_id=account.id,
            type=NotificationType.WITHDRAWAL_CREATED,
            title="Второе",
            body="Второе уведомление",
        )
        newest = await self._create_notification(
            account_id=account.id,
            type=NotificationType.REFERRAL_REWARD_RECEIVED,
            title="Третье",
            body="Третье уведомление",
        )

        async with self._session_factory() as session:
            stored_middle = await session.get(Notification, middle.id)
            assert stored_middle is not None
            stored_middle.read_at = datetime.now(UTC)
            await session.commit()

        response = await self.client.get("/api/v1/notifications?limit=10&offset=0")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["unread_count"], 2)
        self.assertEqual(body["items"][0]["id"], newest.id)
        self.assertEqual(body["items"][1]["id"], middle.id)
        self.assertEqual(body["items"][1]["is_read"], True)
        self.assertEqual(body["items"][2]["id"], oldest.id)

        unread_only_response = await self.client.get("/api/v1/notifications?unread_only=true")
        self.assertEqual(unread_only_response.status_code, 200)
        unread_body = unread_only_response.json()
        self.assertEqual(unread_body["total"], 2)
        self.assertEqual(unread_body["unread_count"], 2)
        self.assertTrue(all(not item["is_read"] for item in unread_body["items"]))

    async def test_mark_notification_read_marks_single_item(self) -> None:
        account = await self._create_account(email="read@example.com")
        self._current_account_id = account.id
        notification = await self._create_notification(
            account_id=account.id,
            type=NotificationType.PAYMENT_FAILED,
            title="Ошибка оплаты",
            body="Платеж не завершился.",
            priority=NotificationPriority.ERROR,
        )

        response = await self.client.post(f"/api/v1/notifications/{notification.id}/read")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], notification.id)
        self.assertEqual(body["is_read"], True)
        self.assertIsNotNone(body["read_at"])

        unread_count_response = await self.client.get("/api/v1/notifications/unread-count")
        self.assertEqual(unread_count_response.status_code, 200)
        self.assertEqual(unread_count_response.json()["unread_count"], 0)

        stored_notification = await self._get_notification(notification.id)
        self.assertIsNotNone(stored_notification)
        assert stored_notification is not None
        self.assertIsNotNone(stored_notification.read_at)

    async def test_mark_all_notifications_read_marks_only_unread(self) -> None:
        account = await self._create_account(email="all-read@example.com")
        self._current_account_id = account.id
        first = await self._create_notification(
            account_id=account.id,
            type=NotificationType.WITHDRAWAL_CREATED,
            title="Заявка создана",
            body="Мы приняли заявку на вывод.",
        )
        second = await self._create_notification(
            account_id=account.id,
            type=NotificationType.WITHDRAWAL_PAID,
            title="Заявка выплачена",
            body="Средства отправлены.",
        )
        third = await self._create_notification(
            account_id=account.id,
            type=NotificationType.WITHDRAWAL_REJECTED,
            title="Заявка отклонена",
            body="Нужны уточнения.",
        )

        async with self._session_factory() as session:
            stored_third = await session.get(Notification, third.id)
            assert stored_third is not None
            stored_third.read_at = datetime.now(UTC)
            await session.commit()

        response = await self.client.post("/api/v1/notifications/read-all")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated_count"], 2)

        unread_count_response = await self.client.get("/api/v1/notifications/unread-count")
        self.assertEqual(unread_count_response.status_code, 200)
        self.assertEqual(unread_count_response.json()["unread_count"], 0)

        stored_first = await self._get_notification(first.id)
        stored_second = await self._get_notification(second.id)
        stored_third_after = await self._get_notification(third.id)
        self.assertIsNotNone(stored_first)
        self.assertIsNotNone(stored_second)
        self.assertIsNotNone(stored_third_after)
        assert stored_first is not None and stored_second is not None and stored_third_after is not None
        self.assertIsNotNone(stored_first.read_at)
        self.assertIsNotNone(stored_second.read_at)
        self.assertIsNotNone(stored_third_after.read_at)


if __name__ == "__main__":
    unittest.main()
