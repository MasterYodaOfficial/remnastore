from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from time import monotonic

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal, engine
from app.services.broadcasts import (
    process_pending_broadcast_deliveries,
    start_due_scheduled_broadcasts,
)
from app.services.cache import get_cache


logger = logging.getLogger(__name__)

SCHEDULER_LOCK_KEY = "lock:broadcasts:scheduler"
DELIVERY_LOCK_KEY = "lock:broadcasts:delivery"


async def _run_scheduler_once() -> None:
    cache = get_cache()
    lock_token = await cache.try_acquire_lock(
        SCHEDULER_LOCK_KEY,
        ttl_seconds=max(10, int(settings.broadcast_job_lock_ttl_seconds)),
    )
    if not lock_token:
        return

    try:
        async with SessionLocal() as session:
            result = await start_due_scheduled_broadcasts(
                session,
                limit=max(1, int(settings.broadcast_jobs_batch_size)),
            )
            await session.commit()
        if result.started_runs > 0:
            logger.info("started scheduled broadcasts: started_runs=%s", result.started_runs)
    finally:
        await cache.release_lock(SCHEDULER_LOCK_KEY, lock_token)


async def _run_delivery_once() -> None:
    cache = get_cache()
    lock_token = await cache.try_acquire_lock(
        DELIVERY_LOCK_KEY,
        ttl_seconds=max(10, int(settings.broadcast_job_lock_ttl_seconds)),
    )
    if not lock_token:
        return

    try:
        async with SessionLocal() as session:
            result = await process_pending_broadcast_deliveries(
                session,
                limit=max(1, int(settings.broadcast_jobs_batch_size)),
            )
            await session.commit()
        if result.processed > 0:
            logger.info(
                "processed broadcast deliveries: processed=%s delivered=%s scheduled_retry=%s terminal_failed=%s skipped=%s",
                result.processed,
                result.delivered,
                result.scheduled_retry,
                result.terminal_failed,
                result.skipped,
            )
    finally:
        await cache.release_lock(DELIVERY_LOCK_KEY, lock_token)


async def run() -> None:
    configure_logging()
    cache = get_cache()
    await cache.ping()

    scheduler_interval = max(5, int(settings.broadcast_scheduler_interval_seconds))
    delivery_interval = max(3, int(settings.broadcast_delivery_interval_seconds))
    next_scheduler_run_at = 0.0
    next_delivery_run_at = 0.0

    logger.info(
        "starting broadcast worker: scheduler_interval=%ss delivery_interval=%ss batch_size=%s timezone=%s",
        scheduler_interval,
        delivery_interval,
        settings.broadcast_jobs_batch_size,
        settings.broadcast_timezone,
    )

    try:
        while True:
            now = monotonic()
            if now >= next_scheduler_run_at:
                try:
                    await _run_scheduler_once()
                except Exception:
                    logger.exception("broadcast scheduler iteration failed")
                next_scheduler_run_at = now + scheduler_interval

            if now >= next_delivery_run_at:
                try:
                    await _run_delivery_once()
                except Exception:
                    logger.exception("broadcast delivery iteration failed")
                next_delivery_run_at = now + delivery_interval

            await asyncio.sleep(1.0)
    finally:
        await cache.close()
        await engine.dispose()


def main() -> None:
    with suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
