from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from time import monotonic

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal, engine
from app.services.cache import get_cache
from app.services.notifications import (
    TelegramNotificationConfigurationError,
    is_telegram_notification_delivery_enabled,
    process_pending_telegram_deliveries,
)


logger = logging.getLogger(__name__)

TELEGRAM_DELIVERY_LOCK_KEY = "lock:notifications:telegram-delivery"


async def _run_telegram_delivery_once() -> None:
    if not is_telegram_notification_delivery_enabled():
        return

    cache = get_cache()
    lock_token = await cache.try_acquire_lock(
        TELEGRAM_DELIVERY_LOCK_KEY,
        ttl_seconds=max(10, int(settings.notification_job_lock_ttl_seconds)),
    )
    if not lock_token:
        return

    try:
        async with SessionLocal() as session:
            result = await process_pending_telegram_deliveries(
                session,
                limit=max(1, int(settings.notification_jobs_batch_size)),
            )
            await session.commit()
        if result.processed > 0:
            logger.info(
                "processed telegram notification deliveries: processed=%s delivered=%s scheduled_retry=%s terminal_failed=%s",
                result.processed,
                result.delivered,
                result.scheduled_retry,
                result.terminal_failed,
            )
    finally:
        await cache.release_lock(TELEGRAM_DELIVERY_LOCK_KEY, lock_token)


async def run() -> None:
    configure_logging(component_name="notifications-worker")
    cache = get_cache()
    await cache.ping()

    interval = max(5, int(settings.notification_telegram_delivery_interval_seconds))
    next_run_at = 0.0

    logger.info(
        "starting notifications worker: telegram_interval=%ss batch_size=%s enabled=%s",
        interval,
        settings.notification_jobs_batch_size,
        is_telegram_notification_delivery_enabled(),
    )

    try:
        while True:
            now = monotonic()
            if now >= next_run_at:
                try:
                    await _run_telegram_delivery_once()
                except TelegramNotificationConfigurationError:
                    logger.warning("telegram notification delivery is disabled: bot token is not configured")
                except Exception:
                    logger.exception("telegram notification delivery iteration failed")
                next_run_at = now + interval

            await asyncio.sleep(1.0)
    finally:
        await cache.close()
        await engine.dispose()


def main() -> None:
    with suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
