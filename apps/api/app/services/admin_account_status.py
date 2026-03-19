from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, AccountStatus, AdminActionLog, AdminActionType
from app.services.account_events import append_account_event
from app.services.ledger import clear_account_cache


class AdminAccountStatusServiceError(Exception):
    pass


class AdminAccountStatusCommentRequiredError(AdminAccountStatusServiceError):
    pass


class AdminAccountStatusConflictError(AdminAccountStatusServiceError):
    pass


@dataclass(slots=True)
class AdminAccountStatusChangeResult:
    account: Account
    previous_status: AccountStatus
    audit_log: AdminActionLog


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise AdminAccountStatusConflictError(f"{field_name} is required")
    return normalized


def _normalize_required_comment(comment: str) -> str:
    normalized = comment.strip()
    if not normalized:
        raise AdminAccountStatusCommentRequiredError("admin comment is required")
    return normalized


async def _load_account_for_update(session: AsyncSession, account_id: UUID) -> Account:
    result = await session.execute(select(Account).where(Account.id == account_id).with_for_update())
    account = result.scalar_one_or_none()
    if account is None:
        raise AdminAccountStatusServiceError(f"account not found: {account_id}")
    return account


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


def _build_audit_payload(
    *,
    previous_status: AccountStatus,
    next_status: AccountStatus,
) -> dict[str, str]:
    return {
        "previous_status": previous_status.value,
        "next_status": next_status.value,
    }


def _validate_existing_audit_log(
    audit_log: AdminActionLog,
    *,
    admin_id: UUID,
    account_id: UUID,
    target_status: AccountStatus,
    comment: str,
) -> AccountStatus:
    if audit_log.admin_id != admin_id:
        raise AdminAccountStatusConflictError("idempotency key already belongs to another admin")
    if audit_log.target_account_id != account_id:
        raise AdminAccountStatusConflictError("idempotency key already belongs to another account")
    if (audit_log.comment or "") != comment:
        raise AdminAccountStatusConflictError("idempotency key already used with another comment")

    payload = audit_log.payload or {}
    payload_next_status = payload.get("next_status")
    if payload_next_status != target_status.value:
        raise AdminAccountStatusConflictError("idempotency key already used for another target status")

    payload_previous_status = payload.get("previous_status")
    if not isinstance(payload_previous_status, str):
        raise AdminAccountStatusConflictError("existing admin audit log is missing previous_status")

    try:
        return AccountStatus(payload_previous_status)
    except ValueError as exc:
        raise AdminAccountStatusConflictError("existing admin audit log contains invalid previous_status") from exc


async def _load_existing_result(
    session: AsyncSession,
    *,
    account_id: UUID,
    admin_id: UUID,
    target_status: AccountStatus,
    comment: str,
    idempotency_key: str,
) -> AdminAccountStatusChangeResult | None:
    audit_log = await _get_admin_action_log_by_idempotency_key(
        session,
        action_type=AdminActionType.ACCOUNT_STATUS_CHANGE,
        idempotency_key=idempotency_key,
        for_update=True,
    )
    if audit_log is None:
        return None

    previous_status = _validate_existing_audit_log(
        audit_log,
        admin_id=admin_id,
        account_id=account_id,
        target_status=target_status,
        comment=comment,
    )
    account = await _load_account_for_update(session, account_id)
    if account.status != target_status:
        raise AdminAccountStatusConflictError("account status changed after this idempotent request")

    return AdminAccountStatusChangeResult(
        account=account,
        previous_status=previous_status,
        audit_log=audit_log,
    )


async def _recover_existing_result(
    session: AsyncSession,
    *,
    account_id: UUID,
    admin_id: UUID,
    target_status: AccountStatus,
    comment: str,
    idempotency_key: str,
    error_message: str,
) -> AdminAccountStatusChangeResult:
    existing_result = await _load_existing_result(
        session,
        account_id=account_id,
        admin_id=admin_id,
        target_status=target_status,
        comment=comment,
        idempotency_key=idempotency_key,
    )
    if existing_result is not None:
        return existing_result
    raise AdminAccountStatusConflictError(error_message)


async def change_account_status(
    session: AsyncSession,
    *,
    account_id: UUID,
    admin_id: UUID,
    target_status: AccountStatus,
    comment: str,
    idempotency_key: str,
) -> AdminAccountStatusChangeResult:
    normalized_comment = _normalize_required_comment(comment)
    normalized_idempotency_key = _normalize_required_text(
        idempotency_key,
        field_name="idempotency_key",
    )

    existing_result = await _load_existing_result(
        session,
        account_id=account_id,
        admin_id=admin_id,
        target_status=target_status,
        comment=normalized_comment,
        idempotency_key=normalized_idempotency_key,
    )
    if existing_result is not None:
        return existing_result

    account = await _load_account_for_update(session, account_id)
    previous_status = account.status
    if previous_status == target_status:
        raise AdminAccountStatusConflictError(f"account already {target_status.value}")

    account.status = target_status
    audit_log = AdminActionLog(
        admin_id=admin_id,
        action_type=AdminActionType.ACCOUNT_STATUS_CHANGE,
        target_account_id=account.id,
        idempotency_key=normalized_idempotency_key,
        comment=normalized_comment,
        payload=_build_audit_payload(
            previous_status=previous_status,
            next_status=target_status,
        ),
    )
    session.add(audit_log)
    await session.flush()
    await append_account_event(
        session,
        account_id=account.id,
        actor_admin_id=admin_id,
        event_type="admin.account_status_change",
        source="admin",
        payload={
            "previous_status": previous_status.value,
            "next_status": target_status.value,
            "comment": normalized_comment,
            "admin_action_log_id": audit_log.id,
            "idempotency_key": normalized_idempotency_key,
        },
    )

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return await _recover_existing_result(
            session,
            account_id=account_id,
            admin_id=admin_id,
            target_status=target_status,
            comment=normalized_comment,
            idempotency_key=normalized_idempotency_key,
            error_message="account status change commit failed",
        )

    await session.refresh(account)
    await session.refresh(audit_log)
    await clear_account_cache(account.id)
    return AdminAccountStatusChangeResult(
        account=account,
        previous_status=previous_status,
        audit_log=audit_log,
    )
