#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID


REPO_ROOT = Path(__file__).resolve().parent.parent
API_APP_ROOT = REPO_ROOT / "apps" / "api"

if str(API_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(API_APP_ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repair stuck trial flags for accounts converted from trial to paid subscription.",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Target application database URL. Defaults to app settings.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write fixes to Remnawave and local DB. Default is dry-run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for number of accounts to inspect.",
    )
    return parser.parse_args()


@dataclass(slots=True)
class TrialRepairCandidate:
    account_id: UUID
    telegram_id: int | None
    email: str | None
    remnawave_user_uuid: UUID
    subscription_status: str | None
    subscription_expires_at: datetime
    trial_ends_at: datetime
    remote_tag: str | None


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


async def _open_target_session_factory(database_url: str):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _collect_candidates(
    *,
    database_url: str,
    limit: int | None,
) -> list[TrialRepairCandidate]:
    from sqlalchemy import select

    from app.db.models import Account
    from app.integrations.remnawave import get_remnawave_gateway

    engine, session_factory = await _open_target_session_factory(database_url)
    gateway = get_remnawave_gateway()

    try:
        async with session_factory() as session:
            statement = (
                select(Account)
                .where(
                    Account.subscription_is_trial.is_(True),
                    Account.subscription_expires_at.is_not(None),
                    Account.trial_ends_at.is_not(None),
                )
                .order_by(Account.updated_at.desc())
            )
            if limit is not None:
                statement = statement.limit(limit)

            accounts = (await session.execute(statement)).scalars().all()

        candidates: list[TrialRepairCandidate] = []
        for account in accounts:
            if account.subscription_expires_at is None or account.trial_ends_at is None:
                continue
            if account.subscription_expires_at <= account.trial_ends_at:
                continue

            remote_uuid = account.remnawave_user_uuid or account.id
            remote_user = await gateway.get_user_by_uuid(remote_uuid)
            candidates.append(
                TrialRepairCandidate(
                    account_id=account.id,
                    telegram_id=account.telegram_id,
                    email=account.email,
                    remnawave_user_uuid=remote_uuid,
                    subscription_status=account.subscription_status,
                    subscription_expires_at=account.subscription_expires_at,
                    trial_ends_at=account.trial_ends_at,
                    remote_tag=None if remote_user is None else remote_user.tag,
                )
            )
        return candidates
    finally:
        await engine.dispose()


async def _apply_repairs(
    *,
    database_url: str,
    candidates: list[TrialRepairCandidate],
) -> dict[str, int]:
    from sqlalchemy import select

    from app.db.models import Account
    from app.integrations.remnawave import get_remnawave_gateway
    from app.services.ledger import clear_account_cache
    from app.services.purchases import apply_remote_subscription_snapshot

    engine, session_factory = await _open_target_session_factory(database_url)
    gateway = get_remnawave_gateway()
    summary = {
        "accounts_fixed_local": 0,
        "accounts_fixed_remote": 0,
        "accounts_remote_missing": 0,
    }

    try:
        async with session_factory() as session:
            for candidate in candidates:
                account = await session.scalar(
                    select(Account)
                    .where(Account.id == candidate.account_id)
                    .with_for_update()
                )
                if account is None:
                    continue

                remote_user = await gateway.get_user_by_uuid(
                    candidate.remnawave_user_uuid
                )
                if remote_user is None:
                    account.subscription_is_trial = False
                    account.subscription_last_synced_at = datetime.now(UTC)
                    summary["accounts_fixed_local"] += 1
                    summary["accounts_remote_missing"] += 1
                    continue

                if remote_user.tag == "TRIAL":
                    remote_user = await gateway.upsert_user(
                        user_uuid=candidate.remnawave_user_uuid,
                        expire_at=account.subscription_expires_at
                        or candidate.subscription_expires_at,
                        email=account.email,
                        telegram_id=account.telegram_id,
                        status=account.subscription_status,
                        is_trial=False,
                    )
                    summary["accounts_fixed_remote"] += 1

                apply_remote_subscription_snapshot(account, remote_user)
                account.subscription_is_trial = False
                summary["accounts_fixed_local"] += 1

            await session.commit()

            for candidate in candidates:
                await clear_account_cache(candidate.account_id)
    finally:
        await engine.dispose()

    return summary


async def _async_main(args: argparse.Namespace) -> int:
    database_url = args.database_url
    if not database_url:
        from app.core.config import settings

        database_url = settings.database_url
    if not database_url:
        raise SystemExit("Target database URL is required")

    candidates = await _collect_candidates(database_url=database_url, limit=args.limit)

    print("Trial flag repair report")
    print(f"- candidates: {len(candidates)}")
    for candidate in candidates[:20]:
        print(
            f"- account_id={candidate.account_id} telegram_id={candidate.telegram_id or '-'} "
            f"expires_at={_serialize_datetime(candidate.subscription_expires_at)} "
            f"trial_ends_at={_serialize_datetime(candidate.trial_ends_at)} "
            f"remote_tag={candidate.remote_tag or '-'}"
        )

    if not args.apply:
        return 0

    summary = await _apply_repairs(database_url=database_url, candidates=candidates)
    print()
    print("Trial flag repair apply summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
