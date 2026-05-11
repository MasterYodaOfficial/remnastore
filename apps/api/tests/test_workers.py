import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.core.config import settings
from app.services.payments import PaymentMaintenanceResult
from app.tasks import broadcast_worker, notifications_worker, payments_worker


class _DummyCache:
    def __init__(self, lock_token: str | None = "lock-token") -> None:
        self.lock_token = lock_token
        self.closed = False
        self.try_calls: list[tuple[str, int]] = []
        self.release_calls: list[tuple[str, str]] = []

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        self.closed = True

    async def try_acquire_lock(self, key: str, ttl_seconds: int) -> str | None:
        self.try_calls.append((key, ttl_seconds))
        return self.lock_token

    async def release_lock(self, key: str, token: str) -> None:
        self.release_calls.append((key, token))


class _SessionContext:
    def __init__(self, session) -> None:
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._original_payment_lock_ttl = settings.payment_job_lock_ttl_seconds
        self._original_payment_batch = settings.payment_jobs_batch_size
        self._original_payment_expire_interval = (
            settings.payment_expire_stale_interval_seconds
        )
        self._original_payment_reconcile_interval = (
            settings.payment_reconcile_yookassa_interval_seconds
        )
        self._original_payment_wallet_interval = (
            settings.payment_reconcile_wallet_grants_interval_seconds
        )
        self._original_payment_min_age = (
            settings.payment_reconcile_yookassa_min_age_seconds
        )
        self._original_notification_lock_ttl = (
            settings.notification_job_lock_ttl_seconds
        )
        self._original_notification_batch = settings.notification_jobs_batch_size
        self._original_notification_interval = (
            settings.notification_telegram_delivery_interval_seconds
        )
        self._original_broadcast_lock_ttl = settings.broadcast_job_lock_ttl_seconds
        self._original_broadcast_batch = settings.broadcast_jobs_batch_size
        self._original_broadcast_sched_interval = (
            settings.broadcast_scheduler_interval_seconds
        )
        self._original_broadcast_delivery_interval = (
            settings.broadcast_delivery_interval_seconds
        )
        self._original_broadcast_timezone = settings.broadcast_timezone

        settings.payment_job_lock_ttl_seconds = 15
        settings.payment_jobs_batch_size = 10
        settings.payment_expire_stale_interval_seconds = 5
        settings.payment_reconcile_yookassa_interval_seconds = 6
        settings.payment_reconcile_wallet_grants_interval_seconds = 7
        settings.payment_reconcile_yookassa_min_age_seconds = 8
        settings.notification_job_lock_ttl_seconds = 15
        settings.notification_jobs_batch_size = 10
        settings.notification_telegram_delivery_interval_seconds = 5
        settings.broadcast_job_lock_ttl_seconds = 15
        settings.broadcast_jobs_batch_size = 10
        settings.broadcast_scheduler_interval_seconds = 5
        settings.broadcast_delivery_interval_seconds = 3
        settings.broadcast_timezone = "UTC"

    def tearDown(self) -> None:
        settings.payment_job_lock_ttl_seconds = self._original_payment_lock_ttl
        settings.payment_jobs_batch_size = self._original_payment_batch
        settings.payment_expire_stale_interval_seconds = (
            self._original_payment_expire_interval
        )
        settings.payment_reconcile_yookassa_interval_seconds = (
            self._original_payment_reconcile_interval
        )
        settings.payment_reconcile_wallet_grants_interval_seconds = (
            self._original_payment_wallet_interval
        )
        settings.payment_reconcile_yookassa_min_age_seconds = (
            self._original_payment_min_age
        )
        settings.notification_job_lock_ttl_seconds = (
            self._original_notification_lock_ttl
        )
        settings.notification_jobs_batch_size = self._original_notification_batch
        settings.notification_telegram_delivery_interval_seconds = (
            self._original_notification_interval
        )
        settings.broadcast_job_lock_ttl_seconds = self._original_broadcast_lock_ttl
        settings.broadcast_jobs_batch_size = self._original_broadcast_batch
        settings.broadcast_scheduler_interval_seconds = (
            self._original_broadcast_sched_interval
        )
        settings.broadcast_delivery_interval_seconds = (
            self._original_broadcast_delivery_interval
        )
        settings.broadcast_timezone = self._original_broadcast_timezone

    async def test_payments_worker_single_runs_use_locks_and_release_them(self) -> None:
        cache = _DummyCache()
        session = SimpleNamespace()

        with (
            patch("app.tasks.payments_worker.get_cache", return_value=cache),
            patch(
                "app.tasks.payments_worker.SessionLocal",
                return_value=_SessionContext(session),
            ),
            patch(
                "app.tasks.payments_worker.expire_stale_payments",
                new=AsyncMock(return_value=PaymentMaintenanceResult(expired=2)),
            ) as expire_mock,
            patch(
                "app.tasks.payments_worker.reconcile_pending_yookassa_payments",
                new=AsyncMock(return_value=PaymentMaintenanceResult(processed=1)),
            ) as reconcile_mock,
            patch(
                "app.tasks.payments_worker.reconcile_pending_wallet_plan_purchases",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        processed=1, applied=1, still_pending=0
                    )
                ),
            ) as wallet_mock,
        ):
            await payments_worker._run_expire_stale_once()
            await payments_worker._run_reconcile_yookassa_once()
            await payments_worker._run_reconcile_wallet_grants_once()

        expire_mock.assert_awaited_once()
        reconcile_mock.assert_awaited_once()
        wallet_mock.assert_awaited_once()
        self.assertEqual(len(cache.release_calls), 3)

    async def test_payments_worker_skips_when_lock_not_acquired(self) -> None:
        cache = _DummyCache(lock_token=None)
        with (
            patch("app.tasks.payments_worker.get_cache", return_value=cache),
            patch(
                "app.tasks.payments_worker.expire_stale_payments", new=AsyncMock()
            ) as expire_mock,
        ):
            await payments_worker._run_expire_stale_once()

        expire_mock.assert_not_awaited()
        self.assertEqual(cache.release_calls, [])

    async def test_payments_worker_run_closes_cache_and_disposes_engine(self) -> None:
        cache = _DummyCache()
        dispose_mock = AsyncMock()

        with (
            patch("app.tasks.payments_worker.configure_logging"),
            patch("app.tasks.payments_worker.get_cache", return_value=cache),
            patch(
                "app.tasks.payments_worker.engine",
                SimpleNamespace(dispose=dispose_mock),
            ),
            patch(
                "app.tasks.payments_worker._run_expire_stale_once",
                new=AsyncMock(side_effect=Exception("boom")),
            ),
            patch(
                "app.tasks.payments_worker._run_reconcile_yookassa_once",
                new=AsyncMock(side_effect=Exception("boom")),
            ),
            patch(
                "app.tasks.payments_worker._run_reconcile_wallet_grants_once",
                new=AsyncMock(side_effect=Exception("boom")),
            ),
            patch("app.tasks.payments_worker.logger.exception"),
            patch(
                "app.tasks.payments_worker.asyncio.sleep",
                new=AsyncMock(side_effect=RuntimeError("stop")),
            ),
            self.assertRaisesRegex(RuntimeError, "stop"),
        ):
            await payments_worker.run()

        self.assertTrue(cache.closed)
        dispose_mock.assert_awaited_once()

    async def test_notifications_worker_paths(self) -> None:
        cache = _DummyCache()
        session = SimpleNamespace(commit=AsyncMock())

        with (
            patch(
                "app.tasks.notifications_worker.is_telegram_notification_delivery_enabled",
                return_value=True,
            ),
            patch("app.tasks.notifications_worker.get_cache", return_value=cache),
            patch(
                "app.tasks.notifications_worker.SessionLocal",
                return_value=_SessionContext(session),
            ),
            patch(
                "app.tasks.notifications_worker.process_pending_telegram_deliveries",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        processed=1,
                        delivered=1,
                        scheduled_retry=0,
                        terminal_failed=0,
                    )
                ),
            ) as delivery_mock,
            patch(
                "app.tasks.notifications_worker.process_subscription_no_connection_reminders",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        processed=1, notified=1, marked_connected=0
                    )
                ),
            ) as reminder_mock,
        ):
            await notifications_worker._run_telegram_delivery_once()
            await notifications_worker._run_subscription_no_connection_once()

        delivery_mock.assert_awaited_once()
        reminder_mock.assert_awaited_once()
        self.assertEqual(session.commit.await_count, 2)

    async def test_notifications_worker_run_handles_configuration_and_shutdown(
        self,
    ) -> None:
        cache = _DummyCache()
        dispose_mock = AsyncMock()

        with (
            patch("app.tasks.notifications_worker.configure_logging"),
            patch("app.tasks.notifications_worker.get_cache", return_value=cache),
            patch(
                "app.tasks.notifications_worker.engine",
                SimpleNamespace(dispose=dispose_mock),
            ),
            patch(
                "app.tasks.notifications_worker._run_telegram_delivery_once",
                new=AsyncMock(
                    side_effect=notifications_worker.TelegramNotificationConfigurationError(
                        "bad config"
                    )
                ),
            ),
            patch(
                "app.tasks.notifications_worker._run_subscription_no_connection_once",
                new=AsyncMock(side_effect=Exception("boom")),
            ),
            patch("app.tasks.notifications_worker.logger.warning"),
            patch("app.tasks.notifications_worker.logger.exception"),
            patch(
                "app.tasks.notifications_worker.asyncio.sleep",
                new=AsyncMock(side_effect=RuntimeError("stop")),
            ),
            self.assertRaisesRegex(RuntimeError, "stop"),
        ):
            await notifications_worker.run()

        self.assertTrue(cache.closed)
        dispose_mock.assert_awaited_once()

    async def test_broadcast_worker_paths(self) -> None:
        cache = _DummyCache()
        session = SimpleNamespace(commit=AsyncMock())

        with (
            patch("app.tasks.broadcast_worker.get_cache", return_value=cache),
            patch(
                "app.tasks.broadcast_worker.SessionLocal",
                return_value=_SessionContext(session),
            ),
            patch(
                "app.tasks.broadcast_worker.start_due_scheduled_broadcasts",
                new=AsyncMock(return_value=SimpleNamespace(started_runs=1)),
            ) as scheduler_mock,
            patch(
                "app.tasks.broadcast_worker.process_pending_broadcast_deliveries",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        processed=1,
                        delivered=1,
                        scheduled_retry=0,
                        terminal_failed=0,
                        skipped=0,
                    )
                ),
            ) as delivery_mock,
        ):
            await broadcast_worker._run_scheduler_once()
            await broadcast_worker._run_delivery_once()

        scheduler_mock.assert_awaited_once()
        delivery_mock.assert_awaited_once()
        self.assertEqual(session.commit.await_count, 2)

    async def test_broadcast_worker_run_closes_cache_and_disposes_engine(self) -> None:
        cache = _DummyCache()
        dispose_mock = AsyncMock()

        with (
            patch("app.tasks.broadcast_worker.configure_logging"),
            patch("app.tasks.broadcast_worker.get_cache", return_value=cache),
            patch(
                "app.tasks.broadcast_worker.engine",
                SimpleNamespace(dispose=dispose_mock),
            ),
            patch(
                "app.tasks.broadcast_worker._run_scheduler_once",
                new=AsyncMock(side_effect=Exception("boom")),
            ),
            patch(
                "app.tasks.broadcast_worker._run_delivery_once",
                new=AsyncMock(side_effect=Exception("boom")),
            ),
            patch("app.tasks.broadcast_worker.logger.exception"),
            patch(
                "app.tasks.broadcast_worker.asyncio.sleep",
                new=AsyncMock(side_effect=RuntimeError("stop")),
            ),
            self.assertRaisesRegex(RuntimeError, "stop"),
        ):
            await broadcast_worker.run()

        self.assertTrue(cache.closed)
        dispose_mock.assert_awaited_once()

    def test_worker_main_functions_delegate_to_asyncio_run(self) -> None:
        def _consume_coroutine(coro):
            coro.close()

        payments_run = Mock(side_effect=_consume_coroutine)
        notifications_run = Mock(side_effect=_consume_coroutine)
        broadcasts_run = Mock(side_effect=_consume_coroutine)

        with (
            patch(
                "app.tasks.payments_worker.asyncio",
                SimpleNamespace(run=payments_run),
            ),
            patch(
                "app.tasks.notifications_worker.asyncio",
                SimpleNamespace(run=notifications_run),
            ),
            patch(
                "app.tasks.broadcast_worker.asyncio",
                SimpleNamespace(run=broadcasts_run),
            ),
        ):
            payments_worker.main()
            notifications_worker.main()
            broadcast_worker.main()

        payments_run.assert_called_once()
        notifications_run.assert_called_once()
        broadcasts_run.assert_called_once()
