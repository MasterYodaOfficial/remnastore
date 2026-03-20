from __future__ import annotations

from dataclasses import dataclass
import uuid
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Account, AccountStatus, LedgerEntryType, Withdrawal, WithdrawalStatus
from app.db.models.withdrawal import WithdrawalDestinationType
from app.services.account_events import append_account_event
from app.services.i18n import translate
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


class WithdrawalInvalidCardError(WithdrawalServiceError):
    pass


class WithdrawalInsufficientAvailableError(WithdrawalServiceError):
    pass


class WithdrawalAccountBlockedError(WithdrawalServiceError):
    pass


def _withdrawal_error(key: str, **kwargs: object) -> str:
    return translate(f"api.withdrawals.errors.{key}", **kwargs)


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


def _only_digits(value: str) -> str:
    return re.sub(r"\D+", "", value)


def _is_luhn_valid(card_number: str) -> bool:
    checksum = 0
    reversed_digits = list(reversed(card_number))
    for index, digit_text in enumerate(reversed_digits):
        digit = int(digit_text)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def normalize_withdrawal_destination_value(
    *,
    destination_type: WithdrawalDestinationType,
    destination_value: str,
) -> str:
    normalized = _normalize_required_text(
        destination_value,
        error_type=WithdrawalDestinationRequiredError,
        message=_withdrawal_error("destination_required"),
    )

    if destination_type == WithdrawalDestinationType.CARD:
        digits = _only_digits(normalized)
        if len(digits) < 16 or len(digits) > 19 or not _is_luhn_valid(digits):
            raise WithdrawalInvalidCardError(_withdrawal_error("invalid_card"))
        return digits

    return normalized


def mask_withdrawal_destination_value(
    *,
    destination_type: WithdrawalDestinationType,
    destination_value: str,
) -> str:
    if destination_type == WithdrawalDestinationType.CARD:
        digits = _only_digits(destination_value)
        if len(digits) >= 4:
            return f"**** **** **** {digits[-4:]}"
        return "****"

    digits = _only_digits(destination_value)
    if digits and len(digits) >= 4:
        return f"{destination_value[:2]}••••{digits[-2:]}"
    return destination_value


def _get_minimum_withdrawal_amount_rub() -> int:
    return max(1, int(settings.min_withdrawal_amount_rub))


async def _load_account_for_update(session: AsyncSession, account_id: uuid.UUID) -> Account:
    result = await session.execute(
        select(Account).where(Account.id == account_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise WithdrawalServiceError(_withdrawal_error("account_not_found"))
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
        raise ValueError(_withdrawal_error("amount_positive"))

    minimum_amount_rub = _get_minimum_withdrawal_amount_rub()
    if amount < minimum_amount_rub:
        raise WithdrawalAmountTooLowError(_withdrawal_error("minimum_amount", amount=minimum_amount_rub))

    normalized_destination_value = normalize_withdrawal_destination_value(
        destination_type=destination_type,
        destination_value=destination_value,
    )
    normalized_user_comment = _normalize_optional_text(user_comment)

    account = await _load_account_for_update(session, account_id)
    if account.status == AccountStatus.BLOCKED:
        raise WithdrawalAccountBlockedError(_withdrawal_error("account_blocked"))

    availability = await get_withdrawal_availability(session, account=account)
    if amount > availability.available_for_withdraw:
        raise WithdrawalInsufficientAvailableError(_withdrawal_error("insufficient_available"))

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
    await append_account_event(
        session,
        account_id=account.id,
        actor_account_id=account.id,
        event_type="withdrawal.created",
        source="api",
        payload={
            "withdrawal_id": withdrawal.id,
            "amount": withdrawal.amount,
            "status": withdrawal.status.value,
            "destination_type": withdrawal.destination_type.value,
            "destination_value": mask_withdrawal_destination_value(
                destination_type=withdrawal.destination_type,
                destination_value=withdrawal.destination_value,
            ),
            "reserved_ledger_entry_id": reserve_entry.id,
        },
    )
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
