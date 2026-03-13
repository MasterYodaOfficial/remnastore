from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, AuthAccount, LedgerEntry, Payment, Withdrawal
from app.domain.payments import PaymentStatus
from app.db.models.withdrawal import WithdrawalStatus


def _normalize_query(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        raise ValueError("query is required")
    return normalized


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
