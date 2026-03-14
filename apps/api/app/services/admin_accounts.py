from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import (
    Account,
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


async def _get_admin_referral_chain(
    session: AsyncSession,
    *,
    account: Account,
) -> dict[str, object]:
    referrer_account = aliased(Account)
    referrer_result = await session.execute(
        select(ReferralAttribution, referrer_account)
        .outerjoin(referrer_account, referrer_account.id == ReferralAttribution.referrer_account_id)
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
        .outerjoin(referred_account, referred_account.id == ReferralAttribution.referred_account_id)
        .outerjoin(ReferralReward, ReferralReward.attribution_id == ReferralAttribution.id)
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
                "subscription_status": None if referred is None else referred.subscription_status,
                "subscription_expires_at": None
                if referred is None
                else referred.subscription_expires_at,
                "attributed_at": attribution.created_at,
                "reward_status": reward_status,
                "reward_amount": 0 if reward is None else int(reward.reward_amount),
                "reward_rate": None if reward is None else float(reward.reward_rate),
                "purchase_amount": None if reward is None else int(reward.purchase_amount_rub),
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

    auth_email_account_ids = (
        select(AuthAccount.account_id).where(func.lower(func.coalesce(AuthAccount.email, "")).like(lowered_like))
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
            select(func.count()).select_from(LedgerEntry).where(LedgerEntry.account_id == account.id)
        )
        or 0
    )
    payments_count = int(
        await session.scalar(select(func.count()).select_from(Payment).where(Payment.account_id == account.id))
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
            select(func.count()).select_from(Withdrawal).where(Withdrawal.account_id == account.id)
        )
        or 0
    )
    pending_withdrawals_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Withdrawal)
            .where(
                Withdrawal.account_id == account.id,
                Withdrawal.status.in_((WithdrawalStatus.NEW, WithdrawalStatus.IN_PROGRESS)),
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
