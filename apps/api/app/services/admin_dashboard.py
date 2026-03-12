from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, Payment, Withdrawal
from app.domain.payments import PaymentStatus
from app.db.models.withdrawal import WithdrawalStatus


async def get_admin_dashboard_summary(session: AsyncSession) -> dict[str, int]:
    total_accounts = int(await session.scalar(select(func.count()).select_from(Account)) or 0)
    active_subscriptions = int(
        await session.scalar(
            select(func.count()).select_from(Account).where(Account.subscription_status == "active")
        )
        or 0
    )
    pending_withdrawals = int(
        await session.scalar(
            select(func.count())
            .select_from(Withdrawal)
            .where(Withdrawal.status.in_((WithdrawalStatus.NEW, WithdrawalStatus.IN_PROGRESS)))
        )
        or 0
    )
    pending_payments = int(
        await session.scalar(
            select(func.count())
            .select_from(Payment)
            .where(
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

    return {
        "total_accounts": total_accounts,
        "active_subscriptions": active_subscriptions,
        "pending_withdrawals": pending_withdrawals,
        "pending_payments": pending_payments,
    }
