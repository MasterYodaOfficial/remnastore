from __future__ import annotations

from dataclasses import dataclass
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Account, AccountStatus, LedgerEntryType, Withdrawal, WithdrawalStatus
from app.db.models.withdrawal import WithdrawalDestinationType
from app.services.ledger import apply_debit_in_transaction
from app.services.notifications import notify_withdrawal_created


class WithdrawalServiceError(Exception):
    pass


class WithdrawalCommentRequiredError(WithdrawalServiceError):
    pass


class WithdrawalDestinationRequiredError(WithdrawalServiceError):
    pass


class WithdrawalAmountTooLowError(WithdrawalServiceError):
    pass


class WithdrawalInsufficientAvailableError(WithdrawalServiceError):
    pass


class WithdrawalAccountBlockedError(WithdrawalServiceError):
    pass


@dataclass(slots=True)
class WithdrawalAvailability:
    available_for_withdraw: int
    active_requested_amount: int
    paid_amount: int


def _normalize_required_text(value: str, *, error_type: type[Exception], message: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise error_type(message)
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _get_minimum_withdrawal_amount_rub() -> int:
    return max(1, int(settings.min_withdrawal_amount_rub))


async def _load_account_for_update(session: AsyncSession, account_id: uuid.UUID) -> Account:
    result = await session.execute(
        select(Account).where(Account.id == account_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise WithdrawalServiceError(f"account not found: {account_id}")
    return account


async def _get_amount_sum_by_statuses(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    statuses: tuple[WithdrawalStatus, ...],
) -> int:
    if not statuses:
        return 0
    amount = await session.scalar(
        select(func.coalesce(func.sum(Withdrawal.amount), 0)).where(
            Withdrawal.account_id == account_id,
            Withdrawal.status.in_(statuses),
        )
    )
    return int(amount or 0)


async def get_withdrawal_availability(
    session: AsyncSession,
    *,
    account: Account,
) -> WithdrawalAvailability:
    active_requested_amount = await _get_amount_sum_by_statuses(
        session,
        account_id=account.id,
        statuses=(WithdrawalStatus.NEW, WithdrawalStatus.IN_PROGRESS),
    )
    paid_amount = await _get_amount_sum_by_statuses(
        session,
        account_id=account.id,
        statuses=(WithdrawalStatus.PAID,),
    )
    remaining_referral_earnings = max(
        0,
        int(account.referral_earnings) - active_requested_amount - paid_amount,
    )
    available_for_withdraw = max(0, min(int(account.balance), remaining_referral_earnings))
    return WithdrawalAvailability(
        available_for_withdraw=available_for_withdraw,
        active_requested_amount=active_requested_amount,
        paid_amount=paid_amount,
    )


async def create_withdrawal_request(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    amount: int,
    destination_type: WithdrawalDestinationType,
    destination_value: str,
    user_comment: str | None,
) -> Withdrawal:
    if amount <= 0:
        raise ValueError("amount must be positive")

    minimum_amount_rub = _get_minimum_withdrawal_amount_rub()
    if amount < minimum_amount_rub:
        raise WithdrawalAmountTooLowError(
            f"minimum withdrawal amount is {minimum_amount_rub} RUB"
        )

    normalized_destination_value = _normalize_required_text(
        destination_value,
        error_type=WithdrawalDestinationRequiredError,
        message="destination value is required",
    )
    normalized_user_comment = _normalize_optional_text(user_comment)

    account = await _load_account_for_update(session, account_id)
    if account.status == AccountStatus.BLOCKED:
        raise WithdrawalAccountBlockedError("blocked accounts cannot create withdrawals")

    availability = await get_withdrawal_availability(session, account=account)
    if amount > availability.available_for_withdraw:
        raise WithdrawalInsufficientAvailableError("insufficient referral funds for withdrawal")

    withdrawal = Withdrawal(
        account_id=account.id,
        amount=amount,
        destination_type=destination_type,
        destination_value=normalized_destination_value,
        user_comment=normalized_user_comment,
        status=WithdrawalStatus.NEW,
    )
    session.add(withdrawal)
    await session.flush()

    reserve_entry = await apply_debit_in_transaction(
        session,
        account_id=account.id,
        amount=amount,
        entry_type=LedgerEntryType.WITHDRAWAL_RESERVE,
        reference_type="withdrawal",
        reference_id=str(withdrawal.id),
        comment=f"Reserve funds for withdrawal #{withdrawal.id}",
        idempotency_key=f"withdrawal:reserve:{withdrawal.id}",
        created_by_account_id=account.id,
    )
    withdrawal.reserved_ledger_entry_id = reserve_entry.id
    await session.flush()
    await notify_withdrawal_created(session, withdrawal=withdrawal)
    return withdrawal


async def get_account_withdrawals(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    limit: int,
    offset: int,
) -> tuple[list[Withdrawal], int]:
    total = await session.scalar(
        select(func.count()).select_from(Withdrawal).where(Withdrawal.account_id == account_id)
    )
    result = await session.execute(
        select(Withdrawal)
        .where(Withdrawal.account_id == account_id)
        .order_by(Withdrawal.created_at.desc(), Withdrawal.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


def get_minimum_withdrawal_amount_rub() -> int:
    return _get_minimum_withdrawal_amount_rub()
