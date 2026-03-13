from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, Payment, Withdrawal
from app.db.models.account import AccountStatus
from app.domain.payments import PaymentFlowType, PaymentStatus
from app.db.models.withdrawal import WithdrawalStatus


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _read_int_stat(session: AsyncSession, statement) -> int:
    return int(await session.scalar(statement) or 0)


async def get_admin_dashboard_summary(session: AsyncSession) -> dict[str, int]:
    now = _utcnow()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)
    pending_withdrawal_statuses = (WithdrawalStatus.NEW, WithdrawalStatus.IN_PROGRESS)
    pending_payment_statuses = (
        PaymentStatus.CREATED,
        PaymentStatus.PENDING,
        PaymentStatus.REQUIRES_ACTION,
    )
    successful_payment_timestamp = func.coalesce(Payment.finalized_at, Payment.created_at)
    paid_withdrawal_timestamp = func.coalesce(Withdrawal.processed_at, Withdrawal.created_at)

    total_accounts = await _read_int_stat(
        session,
        select(func.count()).select_from(Account),
    )
    active_subscriptions = await _read_int_stat(
        session,
        select(func.count()).select_from(Account).where(Account.subscription_status == "active"),
    )
    pending_withdrawals = await _read_int_stat(
        session,
        select(func.count())
        .select_from(Withdrawal)
        .where(Withdrawal.status.in_(pending_withdrawal_statuses)),
    )
    pending_payments = await _read_int_stat(
        session,
        select(func.count())
        .select_from(Payment)
        .where(
            Payment.status.in_(pending_payment_statuses),
            Payment.finalized_at.is_(None),
        ),
    )
    blocked_accounts = await _read_int_stat(
        session,
        select(func.count()).select_from(Account).where(Account.status == AccountStatus.BLOCKED),
    )
    new_accounts_last_7d = await _read_int_stat(
        session,
        select(func.count()).select_from(Account).where(Account.created_at >= seven_days_ago),
    )
    total_wallet_balance = await _read_int_stat(
        session,
        select(func.sum(Account.balance)).select_from(Account),
    )
    total_referral_earnings = await _read_int_stat(
        session,
        select(func.sum(Account.referral_earnings)).select_from(Account),
    )
    pending_withdrawals_amount = await _read_int_stat(
        session,
        select(func.sum(Withdrawal.amount))
        .select_from(Withdrawal)
        .where(Withdrawal.status.in_(pending_withdrawal_statuses)),
    )
    paid_withdrawals_amount_last_30d = await _read_int_stat(
        session,
        select(func.sum(Withdrawal.amount))
        .select_from(Withdrawal)
        .where(
            Withdrawal.status == WithdrawalStatus.PAID,
            paid_withdrawal_timestamp >= thirty_days_ago,
        ),
    )
    successful_payments_last_30d = await _read_int_stat(
        session,
        select(func.count())
        .select_from(Payment)
        .where(
            Payment.status == PaymentStatus.SUCCEEDED,
            successful_payment_timestamp >= thirty_days_ago,
        ),
    )
    successful_payments_amount_last_30d = await _read_int_stat(
        session,
        select(func.sum(Payment.amount))
        .select_from(Payment)
        .where(
            Payment.status == PaymentStatus.SUCCEEDED,
            successful_payment_timestamp >= thirty_days_ago,
        ),
    )
    wallet_topups_amount_last_30d = await _read_int_stat(
        session,
        select(func.sum(Payment.amount))
        .select_from(Payment)
        .where(
            Payment.status == PaymentStatus.SUCCEEDED,
            Payment.flow_type == PaymentFlowType.WALLET_TOPUP,
            successful_payment_timestamp >= thirty_days_ago,
        ),
    )
    direct_plan_revenue_last_30d = await _read_int_stat(
        session,
        select(func.sum(Payment.amount))
        .select_from(Payment)
        .where(
            Payment.status == PaymentStatus.SUCCEEDED,
            Payment.flow_type == PaymentFlowType.DIRECT_PLAN_PURCHASE,
            successful_payment_timestamp >= thirty_days_ago,
        ),
    )

    return {
        "total_accounts": total_accounts,
        "active_subscriptions": active_subscriptions,
        "pending_withdrawals": pending_withdrawals,
        "pending_payments": pending_payments,
        "blocked_accounts": blocked_accounts,
        "new_accounts_last_7d": new_accounts_last_7d,
        "total_wallet_balance": total_wallet_balance,
        "total_referral_earnings": total_referral_earnings,
        "pending_withdrawals_amount": pending_withdrawals_amount,
        "paid_withdrawals_amount_last_30d": paid_withdrawals_amount_last_30d,
        "successful_payments_last_30d": successful_payments_last_30d,
        "successful_payments_amount_last_30d": successful_payments_amount_last_30d,
        "wallet_topups_amount_last_30d": wallet_topups_amount_last_30d,
        "direct_plan_revenue_last_30d": direct_plan_revenue_last_30d,
    }
