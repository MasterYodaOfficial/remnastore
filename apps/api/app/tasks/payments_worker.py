from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from time import monotonic

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal, engine
from app.services.cache import get_cache
from app.services.payments import (
    expire_stale_payments,
    reconcile_pending_yookassa_payments,
)


logger = logging.getLogger(__name__)

EXPIRE_STALE_LOCK_KEY = "lock:payments:expire-stale"
RECONCILE_YOOKASSA_LOCK_KEY = "lock:payments:reconcile-yookassa"


async def _run_expire_stale_once() -> None:
    cache = get_cache()
    lock_token = await cache.try_acquire_lock(
        EXPIRE_STALE_LOCK_KEY,
        ttl_seconds=max(10, int(settings.payment_job_lock_ttl_seconds)),
    )
    if not lock_token:
        return

    try:
        async with SessionLocal() as session:
            result = await expire_stale_payments(
                session,
                limit=max(1, int(settings.payment_jobs_batch_size)),
            )
        if result.expired > 0:
            logger.info("expired stale payments: expired=%s", result.expired)
    finally:
        await cache.release_lock(EXPIRE_STALE_LOCK_KEY, lock_token)


async def _run_reconcile_yookassa_once() -> None:
    cache = get_cache()
    lock_token = await cache.try_acquire_lock(
        RECONCILE_YOOKASSA_LOCK_KEY,
        ttl_seconds=max(10, int(settings.payment_job_lock_ttl_seconds)),
    )
    if not lock_token:
        return

    try:
        async with SessionLocal() as session:
            result = await reconcile_pending_yookassa_payments(
                session,
                limit=max(1, int(settings.payment_jobs_batch_size)),
                min_age_seconds=max(
                    1, int(settings.payment_reconcile_yookassa_min_age_seconds)
                ),
            )
        if result.processed > 0:
            logger.info(
                "reconciled pending yookassa payments: processed=%s succeeded=%s cancelled=%s failed=%s",
                result.processed,
                result.succeeded,
                result.cancelled,
                result.failed,
            )
    finally:
        await cache.release_lock(RECONCILE_YOOKASSA_LOCK_KEY, lock_token)


async def run() -> None:
    configure_logging(component_name="payments-worker")
    cache = get_cache()
    await cache.ping()

    expire_interval = max(5, int(settings.payment_expire_stale_interval_seconds))
    reconcile_interval = max(
        5, int(settings.payment_reconcile_yookassa_interval_seconds)
    )
    next_expire_run_at = 0.0
    next_reconcile_run_at = 0.0

    logger.info(
        "starting payments worker: expire_interval=%ss reconcile_yookassa_interval=%ss batch_size=%s",
        expire_interval,
        reconcile_interval,
        settings.payment_jobs_batch_size,
    )

    try:
        while True:
            now = monotonic()
            if now >= next_expire_run_at:
                try:
                    await _run_expire_stale_once()
                except Exception:
                    logger.exception("expire_stale_payments iteration failed")
                next_expire_run_at = now + expire_interval

            if now >= next_reconcile_run_at:
                try:
                    await _run_reconcile_yookassa_once()
                except Exception:
                    logger.exception(
                        "reconcile_pending_yookassa_payments iteration failed"
                    )
                next_reconcile_run_at = now + reconcile_interval

            await asyncio.sleep(1.0)
    finally:
        await cache.close()
        await engine.dispose()


def main() -> None:
    with suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
