from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Account,
    AdminActionLog,
    AdminActionType,
    LedgerEntry,
    LedgerEntryType,
    Withdrawal,
    WithdrawalStatus,
)
from app.services.ledger import apply_credit_in_transaction, clear_account_cache
from app.services.notifications import notify_withdrawal_paid, notify_withdrawal_rejected


class AdminWithdrawalServiceError(Exception):
    pass


class AdminWithdrawalCommentRequiredError(AdminWithdrawalServiceError):
    pass


class AdminWithdrawalConflictError(AdminWithdrawalServiceError):
    pass


class AdminWithdrawalInvalidStatusError(AdminWithdrawalServiceError):
    pass


PENDING_WITHDRAWAL_STATUSES = (
    WithdrawalStatus.NEW,
    WithdrawalStatus.IN_PROGRESS,
)
ADMIN_WITHDRAWAL_TARGET_STATUSES = (
    WithdrawalStatus.IN_PROGRESS,
    WithdrawalStatus.PAID,
    WithdrawalStatus.REJECTED,
)


@dataclass(slots=True)
class AdminWithdrawalQueueItem:
    id: int
    account_id: UUID
    account_email: str | None
    account_display_name: str | None
    account_telegram_id: int | None
    account_username: str | None
    account_status: str
    amount: int
    destination_type: str
    destination_value: str
    user_comment: str | None
    admin_comment: str | None
    status: str
    created_at: datetime
    processed_at: datetime | None


@dataclass(slots=True)
class AdminWithdrawalStatusChangeResult:
    withdrawal: Withdrawal
    previous_status: WithdrawalStatus
    audit_log: AdminActionLog
    release_entry: LedgerEntry | None


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise AdminWithdrawalConflictError(f"{field_name} is required")
    return normalized


def _normalize_required_comment(comment: str) -> str:
    normalized = comment.strip()
    if not normalized:
        raise AdminWithdrawalCommentRequiredError("admin comment is required")
    return normalized


def _normalize_statuses(
    statuses: tuple[WithdrawalStatus, ...] | None,
) -> tuple[WithdrawalStatus, ...]:
    if not statuses:
        return PENDING_WITHDRAWAL_STATUSES
    return tuple(dict.fromkeys(statuses))


async def list_admin_withdrawals(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    statuses: tuple[WithdrawalStatus, ...] | None = None,
) -> tuple[list[AdminWithdrawalQueueItem], int]:
    resolved_statuses = _normalize_statuses(statuses)

    total = int(
        await session.scalar(
            select(func.count())
            .select_from(Withdrawal)
            .where(Withdrawal.status.in_(resolved_statuses))
        )
        or 0
    )

    result = await session.execute(
        select(Withdrawal, Account)
        .join(Account, Account.id == Withdrawal.account_id)
        .where(Withdrawal.status.in_(resolved_statuses))
        .order_by(Withdrawal.created_at.asc(), Withdrawal.id.asc())
        .limit(limit)
        .offset(offset)
    )

    items: list[AdminWithdrawalQueueItem] = []
    for withdrawal, account in result.all():
        items.append(
            AdminWithdrawalQueueItem(
                id=withdrawal.id,
                account_id=account.id,
                account_email=account.email,
                account_display_name=account.display_name,
                account_telegram_id=account.telegram_id,
                account_username=account.username,
                account_status=account.status.value,
                amount=withdrawal.amount,
                destination_type=withdrawal.destination_type.value,
                destination_value=withdrawal.destination_value,
                user_comment=withdrawal.user_comment,
                admin_comment=withdrawal.admin_comment,
                status=withdrawal.status.value,
                created_at=withdrawal.created_at,
                processed_at=withdrawal.processed_at,
            )
        )

    return items, total


async def _load_withdrawal_for_update(session: AsyncSession, withdrawal_id: int) -> Withdrawal:
    result = await session.execute(
        select(Withdrawal).where(Withdrawal.id == withdrawal_id).with_for_update()
    )
    withdrawal = result.scalar_one_or_none()
    if withdrawal is None:
        raise AdminWithdrawalServiceError(f"withdrawal not found: {withdrawal_id}")
    return withdrawal


async def _get_admin_action_log_by_idempotency_key(
    session: AsyncSession,
    *,
    action_type: AdminActionType,
    idempotency_key: str,
    for_update: bool = False,
) -> AdminActionLog | None:
    statement: Select[tuple[AdminActionLog]] = select(AdminActionLog).where(
        AdminActionLog.action_type == action_type,
        AdminActionLog.idempotency_key == idempotency_key,
    )
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    return result.scalar_one_or_none()


def _validate_target_status(target_status: WithdrawalStatus) -> None:
    if target_status not in ADMIN_WITHDRAWAL_TARGET_STATUSES:
        raise AdminWithdrawalInvalidStatusError(
            "admin withdrawal status must be one of in_progress, paid or rejected"
        )


def _build_audit_payload(
    *,
    withdrawal_id: int,
    previous_status: WithdrawalStatus,
    next_status: WithdrawalStatus,
    released_ledger_entry_id: int | None = None,
) -> dict[str, str | int | None]:
    return {
        "withdrawal_id": withdrawal_id,
        "previous_status": previous_status.value,
        "next_status": next_status.value,
        "released_ledger_entry_id": released_ledger_entry_id,
    }


def _validate_existing_audit_log(
    audit_log: AdminActionLog,
    *,
    admin_id: UUID,
    withdrawal: Withdrawal,
    target_status: WithdrawalStatus,
    comment: str,
) -> WithdrawalStatus:
    if audit_log.admin_id != admin_id:
        raise AdminWithdrawalConflictError("idempotency key already belongs to another admin")
    if audit_log.target_account_id != withdrawal.account_id:
        raise AdminWithdrawalConflictError("idempotency key already belongs to another account")
    if (audit_log.comment or "") != comment:
        raise AdminWithdrawalConflictError("idempotency key already used with another comment")

    payload = audit_log.payload or {}
    if payload.get("withdrawal_id") != withdrawal.id:
        raise AdminWithdrawalConflictError("idempotency key already used for another withdrawal")
    if payload.get("next_status") != target_status.value:
        raise AdminWithdrawalConflictError("idempotency key already used for another target status")

    previous_status = payload.get("previous_status")
    if not isinstance(previous_status, str):
        raise AdminWithdrawalConflictError("existing admin audit log is missing previous_status")

    try:
        return WithdrawalStatus(previous_status)
    except ValueError as exc:
        raise AdminWithdrawalConflictError(
            "existing admin audit log contains invalid previous_status"
        ) from exc


async def _load_existing_result(
    session: AsyncSession,
    *,
    withdrawal_id: int,
    admin_id: UUID,
    target_status: WithdrawalStatus,
    comment: str,
    idempotency_key: str,
) -> AdminWithdrawalStatusChangeResult | None:
    audit_log = await _get_admin_action_log_by_idempotency_key(
        session,
        action_type=AdminActionType.WITHDRAWAL_STATUS_CHANGE,
        idempotency_key=idempotency_key,
        for_update=True,
    )
    if audit_log is None:
        return None

    withdrawal = await _load_withdrawal_for_update(session, withdrawal_id)
    previous_status = _validate_existing_audit_log(
        audit_log,
        admin_id=admin_id,
        withdrawal=withdrawal,
        target_status=target_status,
        comment=comment,
    )
    if withdrawal.status != target_status:
        raise AdminWithdrawalConflictError("withdrawal status changed after this idempotent request")

    release_entry = None
    if withdrawal.released_ledger_entry_id is not None:
        release_entry = await session.get(LedgerEntry, withdrawal.released_ledger_entry_id)

    return AdminWithdrawalStatusChangeResult(
        withdrawal=withdrawal,
        previous_status=previous_status,
        audit_log=audit_log,
        release_entry=release_entry,
    )


def _validate_transition(
    *,
    current_status: WithdrawalStatus,
    target_status: WithdrawalStatus,
) -> None:
    if current_status == target_status:
        raise AdminWithdrawalConflictError(f"withdrawal already {target_status.value}")
    if current_status in (WithdrawalStatus.PAID, WithdrawalStatus.REJECTED, WithdrawalStatus.CANCELLED):
        raise AdminWithdrawalConflictError(
            f"withdrawal in status {current_status.value} cannot be changed"
        )
    if current_status == WithdrawalStatus.NEW and target_status in ADMIN_WITHDRAWAL_TARGET_STATUSES:
        return
    if current_status == WithdrawalStatus.IN_PROGRESS and target_status in (
        WithdrawalStatus.PAID,
        WithdrawalStatus.REJECTED,
    ):
        return
    raise AdminWithdrawalConflictError(
        f"cannot move withdrawal from {current_status.value} to {target_status.value}"
    )


async def change_admin_withdrawal_status(
    session: AsyncSession,
    *,
    withdrawal_id: int,
    admin_id: UUID,
    target_status: WithdrawalStatus,
    comment: str,
    idempotency_key: str,
) -> AdminWithdrawalStatusChangeResult:
    _validate_target_status(target_status)
    normalized_comment = _normalize_required_comment(comment)
    normalized_idempotency_key = _normalize_required_text(
        idempotency_key,
        field_name="idempotency_key",
    )

    existing_result = await _load_existing_result(
        session,
        withdrawal_id=withdrawal_id,
        admin_id=admin_id,
        target_status=target_status,
        comment=normalized_comment,
        idempotency_key=normalized_idempotency_key,
    )
    if existing_result is not None:
        return existing_result

    withdrawal = await _load_withdrawal_for_update(session, withdrawal_id)
    previous_status = withdrawal.status
    _validate_transition(current_status=previous_status, target_status=target_status)

    release_entry = None
    if target_status == WithdrawalStatus.REJECTED:
        release_entry = await apply_credit_in_transaction(
            session,
            account_id=withdrawal.account_id,
            amount=int(withdrawal.amount),
            entry_type=LedgerEntryType.WITHDRAWAL_RELEASE,
            reference_type="withdrawal",
            reference_id=str(withdrawal.id),
            comment=f"Release reserve for withdrawal #{withdrawal.id}",
            idempotency_key=f"withdrawal:release:{withdrawal.id}",
            created_by_admin_id=admin_id,
        )
        withdrawal.released_ledger_entry_id = release_entry.id

    withdrawal.status = target_status
    withdrawal.admin_comment = normalized_comment
    withdrawal.processed_by_admin_id = admin_id
    withdrawal.processed_at = _utcnow()

    audit_log = AdminActionLog(
        admin_id=admin_id,
        action_type=AdminActionType.WITHDRAWAL_STATUS_CHANGE,
        target_account_id=withdrawal.account_id,
        idempotency_key=normalized_idempotency_key,
        comment=normalized_comment,
        payload=_build_audit_payload(
            withdrawal_id=withdrawal.id,
            previous_status=previous_status,
            next_status=target_status,
            released_ledger_entry_id=release_entry.id if release_entry is not None else None,
        ),
    )
    session.add(audit_log)

    try:
        await session.flush()
        if target_status == WithdrawalStatus.PAID:
            await notify_withdrawal_paid(session, withdrawal=withdrawal)
        elif target_status == WithdrawalStatus.REJECTED:
            await notify_withdrawal_rejected(session, withdrawal=withdrawal)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing_result = await _load_existing_result(
            session,
            withdrawal_id=withdrawal_id,
            admin_id=admin_id,
            target_status=target_status,
            comment=normalized_comment,
            idempotency_key=normalized_idempotency_key,
        )
        if existing_result is not None:
            return existing_result
        raise

    await session.refresh(withdrawal)
    await session.refresh(audit_log)
    await clear_account_cache(withdrawal.account_id)
    return AdminWithdrawalStatusChangeResult(
        withdrawal=withdrawal,
        previous_status=previous_status,
        audit_log=audit_log,
        release_entry=release_entry,
    )
