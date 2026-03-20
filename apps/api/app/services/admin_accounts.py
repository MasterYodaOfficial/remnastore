from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import (
    Account,
    AccountEventLog,
    Admin,
    AuthAccount,
    LedgerEntry,
    Payment,
    ReferralAttribution,
    ReferralReward,
    Withdrawal,
)
from app.domain.payments import PaymentStatus
from app.db.models.withdrawal import WithdrawalStatus
from app.services.referrals import get_effective_referral_reward_rate


def _normalize_query(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        raise ValueError("query is required")
    return normalized


def _normalize_filter_values(
    values: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    if not values:
        return None
    normalized_values = tuple(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        )
    )
    return normalized_values or None


def _build_referral_account_snapshot(
    account: Account | None,
    *,
    account_id: uuid.UUID,
) -> dict[str, object | None]:
    return {
        "account_id": account_id,
        "email": None if account is None else account.email,
        "display_name": None if account is None else account.display_name,
        "telegram_id": None if account is None else account.telegram_id,
        "username": None if account is None else account.username,
        "referral_code": None if account is None else account.referral_code,
        "status": None if account is None else account.status,
    }


def _build_account_identity_snapshot(
    account: Account | None,
    *,
    account_id: uuid.UUID | None,
) -> dict[str, object | None] | None:
    if account is None and account_id is None:
        return None
    return {
        "id": account_id if account is None else account.id,
        "email": None if account is None else account.email,
        "display_name": None if account is None else account.display_name,
        "telegram_id": None if account is None else account.telegram_id,
        "username": None if account is None else account.username,
        "status": None if account is None else account.status,
    }


def _build_admin_identity_snapshot(
    admin: Admin | None, *, admin_id: uuid.UUID | None
) -> dict[str, object | None] | None:
    if admin is None and admin_id is None:
        return None
    return {
        "id": admin_id if admin is None else admin.id,
        "username": None if admin is None else admin.username,
        "email": None if admin is None else admin.email,
        "full_name": None if admin is None else admin.full_name,
    }


async def _get_admin_referral_chain(
    session: AsyncSession,
    *,
    account: Account,
) -> dict[str, object]:
    referrer_account = aliased(Account)
    referrer_result = await session.execute(
        select(ReferralAttribution, referrer_account)
        .outerjoin(
            referrer_account,
            referrer_account.id == ReferralAttribution.referrer_account_id,
        )
        .where(ReferralAttribution.referred_account_id == account.id)
        .order_by(ReferralAttribution.created_at.desc(), ReferralAttribution.id.desc())
        .limit(1)
    )
    referrer_row = referrer_result.first()

    referrer_payload: dict[str, object | None] | None = None
    if referrer_row is not None:
        attribution, referrer = referrer_row
        referrer_payload = {
            **_build_referral_account_snapshot(
                referrer,
                account_id=attribution.referrer_account_id,
            ),
            "attributed_at": attribution.created_at,
        }

    referred_account = aliased(Account)
    referrals_result = await session.execute(
        select(ReferralAttribution, referred_account, ReferralReward)
        .outerjoin(
            referred_account,
            referred_account.id == ReferralAttribution.referred_account_id,
        )
        .outerjoin(
            ReferralReward, ReferralReward.attribution_id == ReferralAttribution.id
        )
        .where(ReferralAttribution.referrer_account_id == account.id)
        .order_by(ReferralAttribution.created_at.desc(), ReferralAttribution.id.desc())
    )

    direct_referrals: list[dict[str, object | None]] = []
    rewarded_direct_referrals_count = 0
    pending_direct_referrals_count = 0
    for attribution, referred, reward in referrals_result.all():
        reward_status = "pending" if reward is None else "rewarded"
        if reward is None:
            pending_direct_referrals_count += 1
        else:
            rewarded_direct_referrals_count += 1

        direct_referrals.append(
            {
                "attribution_id": attribution.id,
                **_build_referral_account_snapshot(
                    referred,
                    account_id=attribution.referred_account_id,
                ),
                "subscription_status": None
                if referred is None
                else referred.subscription_status,
                "subscription_expires_at": None
                if referred is None
                else referred.subscription_expires_at,
                "attributed_at": attribution.created_at,
                "reward_status": reward_status,
                "reward_amount": 0 if reward is None else int(reward.reward_amount),
                "reward_rate": None if reward is None else float(reward.reward_rate),
                "purchase_amount": None
                if reward is None
                else int(reward.purchase_amount_rub),
                "reward_created_at": None if reward is None else reward.created_at,
            }
        )

    return {
        "effective_reward_rate": float(get_effective_referral_reward_rate(account)),
        "referrer": referrer_payload,
        "direct_referrals": direct_referrals,
        "direct_referrals_count": len(direct_referrals),
        "rewarded_direct_referrals_count": rewarded_direct_referrals_count,
        "pending_direct_referrals_count": pending_direct_referrals_count,
    }


async def search_admin_accounts(
    session: AsyncSession,
    *,
    query: str,
    limit: int = 20,
) -> list[Account]:
    normalized_query = _normalize_query(query)
    lowered_query = normalized_query.lower()
    lowered_like = f"%{lowered_query}%"

    auth_email_account_ids = select(AuthAccount.account_id).where(
        func.lower(func.coalesce(AuthAccount.email, "")).like(lowered_like)
    )

    conditions = [
        func.lower(func.coalesce(Account.email, "")).like(lowered_like),
        func.lower(func.coalesce(Account.username, "")).like(lowered_like),
        func.lower(func.coalesce(Account.display_name, "")).like(lowered_like),
        Account.id.in_(auth_email_account_ids),
    ]

    if normalized_query.isdigit():
        conditions.append(Account.telegram_id == int(normalized_query))

    result = await session.execute(
        select(Account)
        .where(or_(*conditions))
        .order_by(Account.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_admin_account_event_logs(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    limit: int,
    offset: int,
    event_types: list[str] | tuple[str, ...] | None = None,
    outcomes: list[str] | tuple[str, ...] | None = None,
    sources: list[str] | tuple[str, ...] | None = None,
    request_id: str | None = None,
) -> tuple[list[AccountEventLog], int]:
    filters = [AccountEventLog.account_id == account_id]
    normalized_event_types = _normalize_filter_values(event_types)
    normalized_outcomes = _normalize_filter_values(outcomes)
    normalized_sources = _normalize_filter_values(sources)
    normalized_request_id = None if request_id is None else request_id.strip() or None

    if normalized_event_types:
        filters.append(AccountEventLog.event_type.in_(normalized_event_types))
    if normalized_outcomes:
        filters.append(AccountEventLog.outcome.in_(normalized_outcomes))
    if normalized_sources:
        filters.append(AccountEventLog.source.in_(normalized_sources))
    if normalized_request_id is not None:
        filters.append(AccountEventLog.request_id == normalized_request_id)

    total = int(
        await session.scalar(
            select(func.count()).select_from(AccountEventLog).where(*filters)
        )
        or 0
    )
    result = await session.execute(
        select(AccountEventLog)
        .where(*filters)
        .order_by(AccountEventLog.created_at.desc(), AccountEventLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


async def search_admin_account_event_logs(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    account_id: uuid.UUID | None = None,
    actor_account_id: uuid.UUID | None = None,
    actor_admin_id: uuid.UUID | None = None,
    telegram_id: int | None = None,
    event_types: list[str] | tuple[str, ...] | None = None,
    outcomes: list[str] | tuple[str, ...] | None = None,
    sources: list[str] | tuple[str, ...] | None = None,
    request_id: str | None = None,
) -> tuple[list[dict[str, object | None]], int]:
    target_account = aliased(Account)
    actor_account = aliased(Account)
    actor_admin = aliased(Admin)

    filters = []
    normalized_event_types = _normalize_filter_values(event_types)
    normalized_outcomes = _normalize_filter_values(outcomes)
    normalized_sources = _normalize_filter_values(sources)
    normalized_request_id = None if request_id is None else request_id.strip() or None

    if account_id is not None:
        filters.append(AccountEventLog.account_id == account_id)
    if actor_account_id is not None:
        filters.append(AccountEventLog.actor_account_id == actor_account_id)
    if actor_admin_id is not None:
        filters.append(AccountEventLog.actor_admin_id == actor_admin_id)
    if telegram_id is not None:
        filters.append(target_account.telegram_id == telegram_id)
    if normalized_event_types:
        filters.append(AccountEventLog.event_type.in_(normalized_event_types))
    if normalized_outcomes:
        filters.append(AccountEventLog.outcome.in_(normalized_outcomes))
    if normalized_sources:
        filters.append(AccountEventLog.source.in_(normalized_sources))
    if normalized_request_id is not None:
        filters.append(AccountEventLog.request_id == normalized_request_id)

    count_stmt = (
        select(func.count())
        .select_from(AccountEventLog)
        .outerjoin(target_account, target_account.id == AccountEventLog.account_id)
        .outerjoin(actor_account, actor_account.id == AccountEventLog.actor_account_id)
        .outerjoin(actor_admin, actor_admin.id == AccountEventLog.actor_admin_id)
        .where(*filters)
    )
    total = int(await session.scalar(count_stmt) or 0)

    result = await session.execute(
        select(AccountEventLog, target_account, actor_account, actor_admin)
        .outerjoin(target_account, target_account.id == AccountEventLog.account_id)
        .outerjoin(actor_account, actor_account.id == AccountEventLog.actor_account_id)
        .outerjoin(actor_admin, actor_admin.id == AccountEventLog.actor_admin_id)
        .where(*filters)
        .order_by(AccountEventLog.created_at.desc(), AccountEventLog.id.desc())
        .limit(limit)
        .offset(offset)
    )

    items: list[dict[str, object | None]] = []
    for event, account, actor, admin in result.all():
        items.append(
            {
                "id": event.id,
                "account_id": event.account_id,
                "actor_account_id": event.actor_account_id,
                "actor_admin_id": event.actor_admin_id,
                "event_type": event.event_type,
                "outcome": event.outcome,
                "source": event.source,
                "request_id": event.request_id,
                "payload": event.payload,
                "created_at": event.created_at,
                "account": _build_account_identity_snapshot(
                    account, account_id=event.account_id
                ),
                "actor_account": _build_account_identity_snapshot(
                    actor, account_id=event.actor_account_id
                ),
                "actor_admin": _build_admin_identity_snapshot(
                    admin, admin_id=event.actor_admin_id
                ),
            }
        )

    return items, total


async def get_admin_account_detail(
    session: AsyncSession,
    *,
    account_id: uuid.UUID | str,
) -> dict | None:
    if isinstance(account_id, str):
        try:
            account_id = uuid.UUID(account_id)
        except ValueError:
            return None

    account = await session.get(Account, account_id)
    if account is None:
        return None

    referral_chain = await _get_admin_referral_chain(session, account=account)

    auth_accounts_result = await session.execute(
        select(AuthAccount)
        .where(AuthAccount.account_id == account.id)
        .order_by(AuthAccount.linked_at.asc(), AuthAccount.id.asc())
    )
    ledger_entries_result = await session.execute(
        select(LedgerEntry)
        .where(LedgerEntry.account_id == account.id)
        .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .limit(10)
    )
    payments_result = await session.execute(
        select(Payment)
        .where(Payment.account_id == account.id)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .limit(10)
    )
    withdrawals_result = await session.execute(
        select(Withdrawal)
        .where(Withdrawal.account_id == account.id)
        .order_by(Withdrawal.created_at.desc(), Withdrawal.id.desc())
        .limit(10)
    )

    ledger_entries_count = int(
        await session.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(LedgerEntry.account_id == account.id)
        )
        or 0
    )
    payments_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Payment)
            .where(Payment.account_id == account.id)
        )
        or 0
    )
    pending_payments_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Payment)
            .where(
                Payment.account_id == account.id,
                Payment.status.in_(
                    (
                        PaymentStatus.CREATED,
                        PaymentStatus.PENDING,
                        PaymentStatus.REQUIRES_ACTION,
                    )
                ),
                Payment.finalized_at.is_(None),
            )
        )
        or 0
    )
    withdrawals_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Withdrawal)
            .where(Withdrawal.account_id == account.id)
        )
        or 0
    )
    pending_withdrawals_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Withdrawal)
            .where(
                Withdrawal.account_id == account.id,
                Withdrawal.status.in_(
                    (WithdrawalStatus.NEW, WithdrawalStatus.IN_PROGRESS)
                ),
            )
        )
        or 0
    )

    return {
        **account.__dict__,
        "referral_chain": referral_chain,
        "auth_accounts": list(auth_accounts_result.scalars().all()),
        "recent_ledger_entries": list(ledger_entries_result.scalars().all()),
        "recent_payments": list(payments_result.scalars().all()),
        "recent_withdrawals": list(withdrawals_result.scalars().all()),
        "ledger_entries_count": ledger_entries_count,
        "payments_count": payments_count,
        "pending_payments_count": pending_payments_count,
        "withdrawals_count": withdrawals_count,
        "pending_withdrawals_count": pending_withdrawals_count,
    }
