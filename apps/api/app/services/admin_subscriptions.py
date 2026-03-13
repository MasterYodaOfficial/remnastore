from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, AdminActionLog, AdminActionType, SubscriptionGrant
from app.integrations.remnawave import get_remnawave_gateway
from app.services.ledger import clear_account_cache
from app.services.plans import SubscriptionPlan, get_subscription_plan
from app.services.purchases import (
    GatewayFactory,
    PurchaseConflictError,
    PurchaseSource,
    RemnawaveSyncError,
    apply_paid_purchase,
    compute_paid_plan_window,
    get_subscription_grant_by_reference,
    load_purchase_account_for_update,
    utcnow,
)


ADMIN_MANUAL_GRANT_REFERENCE_TYPE = "admin_manual_grant"


class AdminSubscriptionServiceError(Exception):
    pass


class AdminSubscriptionCommentRequiredError(AdminSubscriptionServiceError):
    pass


@dataclass(slots=True)
class AdminSubscriptionGrantResult:
    account: Account
    grant: SubscriptionGrant
    audit_log: AdminActionLog


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise PurchaseConflictError(f"{field_name} is required")
    return normalized


def _normalize_required_comment(comment: str) -> str:
    normalized = comment.strip()
    if not normalized:
        raise AdminSubscriptionCommentRequiredError("admin comment is required")
    return normalized


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


def _validate_existing_manual_grant(
    grant: SubscriptionGrant,
    *,
    account_id: UUID,
    plan: SubscriptionPlan,
) -> None:
    if grant.account_id != account_id:
        raise PurchaseConflictError("idempotency key already belongs to another account")
    if grant.plan_code != plan.code:
        raise PurchaseConflictError("idempotency key already used for another plan")
    if grant.amount != 0 or grant.currency != "RUB":
        raise PurchaseConflictError("idempotency key already used for another grant amount")
    if grant.duration_days != plan.duration_days:
        raise PurchaseConflictError("idempotency key already used for another duration")


def _validate_existing_audit_log(
    audit_log: AdminActionLog,
    *,
    admin_id: UUID,
    account_id: UUID,
    plan_code: str,
    comment: str,
) -> None:
    if audit_log.admin_id != admin_id:
        raise PurchaseConflictError("idempotency key already belongs to another admin")
    if audit_log.target_account_id != account_id:
        raise PurchaseConflictError("idempotency key already belongs to another account")
    if (audit_log.comment or "") != comment:
        raise PurchaseConflictError("idempotency key already used with another comment")

    payload = audit_log.payload or {}
    if payload.get("plan_code") != plan_code:
        raise PurchaseConflictError("idempotency key already used for another plan")


def _build_audit_payload(
    *,
    plan: SubscriptionPlan,
    grant: SubscriptionGrant,
) -> dict[str, object]:
    return {
        "plan_code": plan.code,
        "duration_days": plan.duration_days,
        "purchase_source": PurchaseSource.ADMIN.value,
        "reference_type": ADMIN_MANUAL_GRANT_REFERENCE_TYPE,
        "reference_id": grant.reference_id,
        "subscription_grant_id": grant.id,
        "base_expires_at": grant.base_expires_at.isoformat(),
        "target_expires_at": grant.target_expires_at.isoformat(),
    }


async def _load_existing_result(
    session: AsyncSession,
    *,
    account_id: UUID,
    admin_id: UUID,
    plan: SubscriptionPlan,
    comment: str,
    idempotency_key: str,
) -> AdminSubscriptionGrantResult | None:
    existing_grant = await get_subscription_grant_by_reference(
        session,
        purchase_source=PurchaseSource.ADMIN,
        reference_type=ADMIN_MANUAL_GRANT_REFERENCE_TYPE,
        reference_id=idempotency_key,
        for_update=True,
    )
    if existing_grant is None:
        return None
    _validate_existing_manual_grant(existing_grant, account_id=account_id, plan=plan)

    audit_log = await _get_admin_action_log_by_idempotency_key(
        session,
        action_type=AdminActionType.SUBSCRIPTION_GRANT,
        idempotency_key=idempotency_key,
        for_update=True,
    )
    if audit_log is None:
        raise PurchaseConflictError("admin audit log is missing for existing subscription grant")
    _validate_existing_audit_log(
        audit_log,
        admin_id=admin_id,
        account_id=account_id,
        plan_code=plan.code,
        comment=comment,
    )

    account = await load_purchase_account_for_update(session, account_id=account_id)
    return AdminSubscriptionGrantResult(
        account=account,
        grant=existing_grant,
        audit_log=audit_log,
    )


async def _recover_existing_result(
    session: AsyncSession,
    *,
    account_id: UUID,
    admin_id: UUID,
    plan: SubscriptionPlan,
    comment: str,
    idempotency_key: str,
    error_message: str,
) -> AdminSubscriptionGrantResult:
    existing_result = await _load_existing_result(
        session,
        account_id=account_id,
        admin_id=admin_id,
        plan=plan,
        comment=comment,
        idempotency_key=idempotency_key,
    )
    if existing_result is not None:
        return existing_result
    raise PurchaseConflictError(error_message)


async def grant_subscription_manually(
    session: AsyncSession,
    *,
    account_id: UUID,
    admin_id: UUID,
    plan_code: str,
    comment: str,
    idempotency_key: str,
    gateway_factory: GatewayFactory | None = None,
) -> AdminSubscriptionGrantResult:
    plan = get_subscription_plan(plan_code)
    normalized_comment = _normalize_required_comment(comment)
    normalized_idempotency_key = _normalize_required_text(
        idempotency_key,
        field_name="idempotency_key",
    )

    existing_result = await _load_existing_result(
        session,
        account_id=account_id,
        admin_id=admin_id,
        plan=plan,
        comment=normalized_comment,
        idempotency_key=normalized_idempotency_key,
    )
    if existing_result is not None:
        return existing_result

    account = await load_purchase_account_for_update(session, account_id=account_id)
    base_expires_at, target_expires_at = compute_paid_plan_window(
        account,
        duration_days=plan.duration_days,
    )

    grant = SubscriptionGrant(
        account_id=account.id,
        payment_id=None,
        purchase_source=PurchaseSource.ADMIN.value,
        reference_type=ADMIN_MANUAL_GRANT_REFERENCE_TYPE,
        reference_id=normalized_idempotency_key,
        plan_code=plan.code,
        amount=0,
        currency="RUB",
        duration_days=plan.duration_days,
        base_expires_at=base_expires_at,
        target_expires_at=target_expires_at,
        applied_at=None,
    )
    session.add(grant)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return await _recover_existing_result(
            session,
            account_id=account_id,
            admin_id=admin_id,
            plan=plan,
            comment=normalized_comment,
            idempotency_key=normalized_idempotency_key,
            error_message="manual subscription grant staging failed",
        )

    audit_log = AdminActionLog(
        admin_id=admin_id,
        action_type=AdminActionType.SUBSCRIPTION_GRANT,
        target_account_id=account.id,
        idempotency_key=normalized_idempotency_key,
        comment=normalized_comment,
        payload=_build_audit_payload(plan=plan, grant=grant),
    )
    session.add(audit_log)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return await _recover_existing_result(
            session,
            account_id=account_id,
            admin_id=admin_id,
            plan=plan,
            comment=normalized_comment,
            idempotency_key=normalized_idempotency_key,
            error_message="manual subscription audit log staging failed",
        )

    try:
        await apply_paid_purchase(
            account,
            source=PurchaseSource.ADMIN,
            target_expires_at=target_expires_at,
            gateway_factory=gateway_factory or get_remnawave_gateway,
        )
    except RemnawaveSyncError:
        await session.rollback()
        raise

    grant.applied_at = utcnow()

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return await _recover_existing_result(
            session,
            account_id=account_id,
            admin_id=admin_id,
            plan=plan,
            comment=normalized_comment,
            idempotency_key=normalized_idempotency_key,
            error_message="manual subscription grant commit failed",
        )

    await session.refresh(account)
    await session.refresh(grant)
    await session.refresh(audit_log)
    await clear_account_cache(account.id)
    return AdminSubscriptionGrantResult(
        account=account,
        grant=grant,
        audit_log=audit_log,
    )
