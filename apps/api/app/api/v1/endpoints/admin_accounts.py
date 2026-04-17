from __future__ import annotations

import csv
import enum
from datetime import date, datetime
from io import StringIO
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import api_error, api_error_from_exception
from app.api.dependencies import get_current_admin
from app.core.audit import build_request_audit_context, log_audit_event
from app.db.models import Account, Admin
from app.db.session import get_session
from app.db.models.ledger import LedgerEntryType
from app.schemas.admin import (
    AdminAccountStatusChangeRequest,
    AdminAccountStatusChangeResponse,
    AdminBalanceAdjustmentRequest,
    AdminBalanceAdjustmentResponse,
    AdminAccountDetailResponse,
    AdminAccountEventLogHistoryResponse,
    AdminAccountEventLogResponse,
    AdminGlobalAccountEventLogHistoryResponse,
    AdminGlobalAccountEventLogResponse,
    AdminAccountLedgerHistoryResponse,
    AdminAccountLedgerEntryResponse,
    AdminAccountListItemResponse,
    AdminAccountListResponse,
    AdminAccountSearchItemResponse,
    AdminAccountSearchResponse,
    AdminSubscriptionGrantRequest,
    AdminSubscriptionGrantResponse,
)
from app.schemas.payment import SubscriptionPlanResponse
from app.services.admin_accounts import (
    export_admin_accounts,
    get_admin_account_detail,
    get_admin_account_event_logs,
    list_admin_accounts,
    search_admin_account_event_logs,
    search_admin_accounts,
)
from app.services.admin_account_status import (
    AdminAccountStatusCommentRequiredError,
    AdminAccountStatusConflictError,
    change_account_status,
)
from app.services.admin_subscriptions import (
    AdminSubscriptionCommentRequiredError,
    grant_subscription_manually,
)
from app.services.ledger import (
    InsufficientFundsError,
    LedgerCommentRequiredError,
    admin_adjust_balance,
    get_account_ledger_history,
)
from app.services.plans import SubscriptionPlanError, get_subscription_plans
from app.services.purchases import PurchaseConflictError, RemnawaveSyncError
from app.services.i18n import translate


router = APIRouter()

ACCOUNT_EXPORT_COLUMNS = (
    "id",
    "email",
    "display_name",
    "telegram_id",
    "username",
    "first_name",
    "last_name",
    "is_premium",
    "locale",
    "telegram_bot_blocked_at",
    "remnawave_user_uuid",
    "subscription_url",
    "subscription_status",
    "subscription_expires_at",
    "subscription_last_synced_at",
    "subscription_is_trial",
    "trial_used_at",
    "trial_ends_at",
    "balance",
    "referral_code",
    "referral_earnings",
    "referrals_count",
    "referral_reward_rate",
    "referred_by_account_id",
    "status",
    "last_login_source",
    "last_seen_at",
    "created_at",
    "updated_at",
    "auth_email_primary",
    "auth_emails",
    "auth_providers",
)


def _build_account_list_item(account: Account) -> AdminAccountListItemResponse:
    resolved_email = account.email or next(
        (identity.email for identity in account.auth_accounts if identity.email),
        None,
    )
    return AdminAccountListItemResponse(
        id=account.id,
        email=resolved_email,
        display_name=account.display_name,
        telegram_id=account.telegram_id,
        username=account.username,
        status=account.status,
        balance=account.balance,
        subscription_status=account.subscription_status,
        subscription_expires_at=account.subscription_expires_at,
        referrals_count=account.referrals_count,
        last_seen_at=account.last_seen_at,
        created_at=account.created_at,
    )


def _format_account_export_value(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return str(value.value)
    return str(value)


def _build_account_export_row(account: Account) -> list[str]:
    auth_emails = [
        identity.email for identity in account.auth_accounts if identity.email
    ]
    auth_providers = [identity.provider.value for identity in account.auth_accounts]
    auth_email_primary = auth_emails[0] if auth_emails else None

    row = [
        account.id,
        account.email,
        account.display_name,
        account.telegram_id,
        account.username,
        account.first_name,
        account.last_name,
        account.is_premium,
        account.locale,
        account.telegram_bot_blocked_at,
        account.remnawave_user_uuid,
        account.subscription_url,
        account.subscription_status,
        account.subscription_expires_at,
        account.subscription_last_synced_at,
        account.subscription_is_trial,
        account.trial_used_at,
        account.trial_ends_at,
        account.balance,
        account.referral_code,
        account.referral_earnings,
        account.referrals_count,
        account.referral_reward_rate,
        account.referred_by_account_id,
        account.status,
        account.last_login_source,
        account.last_seen_at,
        account.created_at,
        account.updated_at,
        auth_email_primary,
        ", ".join(auth_emails),
        ", ".join(auth_providers),
    ]
    return [_format_account_export_value(value) for value in row]


@router.get("", response_model=AdminAccountListResponse)
async def list_accounts(
    query: str | None = Query(default=None, min_length=1, max_length=255),
    user_query: str | None = Query(default=None, min_length=1, max_length=255),
    telegram_query: str | None = Query(default=None, min_length=1, max_length=255),
    email_query: str | None = Query(default=None, min_length=1, max_length=255),
    status: Literal["active", "blocked"] | None = Query(default=None),
    subscription_state: Literal["active", "inactive", "none"] | None = Query(
        default=None
    ),
    telegram_state: Literal["connected", "not_connected"] | None = Query(default=None),
    sort_by: Literal[
        "user",
        "telegram_id",
        "email",
        "created_at",
        "last_seen_at",
        "balance",
        "subscription_expires_at",
        "referrals_count",
    ] = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminAccountListResponse:
    accounts, total = await list_admin_accounts(
        session,
        query=query,
        user_query=user_query,
        telegram_query=telegram_query,
        email_query=email_query,
        status=status,
        subscription_state=subscription_state,
        telegram_state=telegram_state,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    return AdminAccountListResponse(
        items=[_build_account_list_item(account) for account in accounts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/export")
async def export_accounts(
    query: str | None = Query(default=None, min_length=1, max_length=255),
    user_query: str | None = Query(default=None, min_length=1, max_length=255),
    telegram_query: str | None = Query(default=None, min_length=1, max_length=255),
    email_query: str | None = Query(default=None, min_length=1, max_length=255),
    status: Literal["active", "blocked"] | None = Query(default=None),
    subscription_state: Literal["active", "inactive", "none"] | None = Query(
        default=None
    ),
    telegram_state: Literal["connected", "not_connected"] | None = Query(default=None),
    sort_by: Literal[
        "user",
        "telegram_id",
        "email",
        "created_at",
        "last_seen_at",
        "balance",
        "subscription_expires_at",
        "referrals_count",
    ] = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> Response:
    accounts = await export_admin_accounts(
        session,
        query=query,
        user_query=user_query,
        telegram_query=telegram_query,
        email_query=email_query,
        status=status,
        subscription_state=subscription_state,
        telegram_state=telegram_state,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(ACCOUNT_EXPORT_COLUMNS)
    for account in accounts:
        writer.writerow(_build_account_export_row(account))

    export_date = date.today().isoformat()
    filename = f"accounts-export-{export_date}.csv"
    return Response(
        content=f"\ufeff{buffer.getvalue()}",
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/subscription-plans", response_model=list[SubscriptionPlanResponse])
async def list_admin_subscription_plans(
    _: Admin = Depends(get_current_admin),
) -> list[SubscriptionPlanResponse]:
    try:
        plans = get_subscription_plans()
    except SubscriptionPlanError as exc:
        raise api_error_from_exception(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            exc,
        ) from exc

    return [
        SubscriptionPlanResponse(
            code=plan.code,
            name=plan.name,
            price_rub=plan.price_rub,
            price_stars=plan.price_stars,
            duration_days=plan.duration_days,
            features=list(plan.features),
            popular=plan.popular,
        )
        for plan in plans
    ]


@router.get("/search", response_model=AdminAccountSearchResponse)
async def search_accounts(
    query: str = Query(..., min_length=1, max_length=255),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminAccountSearchResponse:
    accounts = await search_admin_accounts(session, query=query, limit=limit)
    return AdminAccountSearchResponse(
        items=[
            AdminAccountSearchItemResponse.model_validate(account, from_attributes=True)
            for account in accounts
        ]
    )


@router.get(
    "/event-logs/search",
    response_model=AdminGlobalAccountEventLogHistoryResponse,
)
async def search_account_event_logs(
    account_id: UUID | None = Query(default=None),
    actor_account_id: UUID | None = Query(default=None),
    actor_admin_id: UUID | None = Query(default=None),
    telegram_id: int | None = Query(default=None),
    event_type: list[str] | None = Query(default=None),
    outcome: list[str] | None = Query(default=None),
    source: list[str] | None = Query(default=None),
    request_id: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminGlobalAccountEventLogHistoryResponse:
    items, total = await search_admin_account_event_logs(
        session,
        account_id=account_id,
        actor_account_id=actor_account_id,
        actor_admin_id=actor_admin_id,
        telegram_id=telegram_id,
        event_types=event_type,
        outcomes=outcome,
        sources=source,
        request_id=request_id,
        limit=limit,
        offset=offset,
    )
    return AdminGlobalAccountEventLogHistoryResponse(
        items=[
            AdminGlobalAccountEventLogResponse.model_validate(item) for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{account_id}", response_model=AdminAccountDetailResponse)
async def read_account_detail(
    account_id: str,
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminAccountDetailResponse:
    detail = await get_admin_account_detail(session, account_id=account_id)
    if detail is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            translate("api.admin.errors.account_not_found"),
            error_code="admin_account_not_found",
        )
    return AdminAccountDetailResponse.model_validate(detail, from_attributes=True)


@router.get(
    "/{account_id}/event-logs",
    response_model=AdminAccountEventLogHistoryResponse,
)
async def read_account_event_logs(
    account_id: UUID,
    event_type: list[str] | None = Query(default=None),
    outcome: list[str] | None = Query(default=None),
    source: list[str] | None = Query(default=None),
    request_id: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminAccountEventLogHistoryResponse:
    account = await session.get(Account, account_id)
    if account is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            translate("api.admin.errors.account_not_found"),
            error_code="admin_account_not_found",
        )

    items, total = await get_admin_account_event_logs(
        session,
        account_id=account.id,
        limit=limit,
        offset=offset,
        event_types=event_type,
        outcomes=outcome,
        sources=source,
        request_id=request_id,
    )
    return AdminAccountEventLogHistoryResponse(
        items=[
            AdminAccountEventLogResponse.model_validate(item, from_attributes=True)
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{account_id}/ledger-entries",
    response_model=AdminAccountLedgerHistoryResponse,
)
async def read_account_ledger_entries(
    account_id: UUID,
    entry_type: LedgerEntryType | None = Query(default=None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminAccountLedgerHistoryResponse:
    account = await session.get(Account, account_id)
    if account is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            translate("api.admin.errors.account_not_found"),
            error_code="admin_account_not_found",
        )

    items, total = await get_account_ledger_history(
        session,
        account_id=account.id,
        limit=limit,
        offset=offset,
        entry_types=(entry_type,) if entry_type is not None else None,
    )
    return AdminAccountLedgerHistoryResponse(
        items=[
            AdminAccountLedgerEntryResponse.model_validate(entry, from_attributes=True)
            for entry in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{account_id}/balance-adjustments",
    response_model=AdminBalanceAdjustmentResponse,
)
async def adjust_account_balance(
    account_id: UUID,
    payload: AdminBalanceAdjustmentRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> AdminBalanceAdjustmentResponse:
    request_context = build_request_audit_context(request)
    account = await session.get(Account, account_id)
    if account is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            translate("api.admin.errors.account_not_found"),
            error_code="admin_account_not_found",
        )

    try:
        entry = await admin_adjust_balance(
            session,
            account_id=account.id,
            amount=payload.amount,
            admin_id=current_admin.id,
            comment=payload.comment,
            idempotency_key=payload.idempotency_key,
        )
    except LedgerCommentRequiredError as exc:
        log_audit_event(
            "admin.balance_adjustment",
            outcome="failure",
            category="business",
            reason="comment_required",
            admin_id=current_admin.id,
            account_id=account.id,
            amount=payload.amount,
            **request_context,
        )
        exc.args = (translate("api.admin.errors.comment_required"),)
        raise api_error_from_exception(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            exc,
            error_code="admin_comment_required",
        ) from exc
    except InsufficientFundsError as exc:
        log_audit_event(
            "admin.balance_adjustment",
            outcome="failure",
            category="business",
            reason="insufficient_funds",
            admin_id=current_admin.id,
            account_id=account.id,
            amount=payload.amount,
            **request_context,
        )
        raise api_error_from_exception(status.HTTP_409_CONFLICT, exc) from exc

    return AdminBalanceAdjustmentResponse(
        account_id=account.id,
        balance=account.balance,
        ledger_entry=AdminAccountLedgerEntryResponse.model_validate(
            entry, from_attributes=True
        ),
    )


@router.post(
    "/{account_id}/status",
    response_model=AdminAccountStatusChangeResponse,
)
async def change_status(
    account_id: UUID,
    payload: AdminAccountStatusChangeRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> AdminAccountStatusChangeResponse:
    account = await session.get(Account, account_id)
    if account is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            translate("api.admin.errors.account_not_found"),
            error_code="admin_account_not_found",
        )

    try:
        result = await change_account_status(
            session,
            account_id=account.id,
            admin_id=current_admin.id,
            target_status=payload.status,
            comment=payload.comment,
            idempotency_key=payload.idempotency_key,
        )
    except AdminAccountStatusCommentRequiredError as exc:
        exc.args = (translate("api.admin.errors.comment_required"),)
        raise api_error_from_exception(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            exc,
        ) from exc
    except AdminAccountStatusConflictError as exc:
        exc.args = (translate("api.admin.errors.account_status_conflict"),)
        raise api_error_from_exception(status.HTTP_409_CONFLICT, exc) from exc

    return AdminAccountStatusChangeResponse(
        account_id=result.account.id,
        previous_status=result.previous_status,
        status=result.account.status,
        audit_log_id=result.audit_log.id,
    )


@router.post(
    "/{account_id}/subscription-grants",
    response_model=AdminSubscriptionGrantResponse,
)
async def grant_account_subscription(
    account_id: UUID,
    payload: AdminSubscriptionGrantRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> AdminSubscriptionGrantResponse:
    account = await session.get(Account, account_id)
    if account is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            translate("api.admin.errors.account_not_found"),
            error_code="admin_account_not_found",
        )

    try:
        result = await grant_subscription_manually(
            session,
            account_id=account.id,
            admin_id=current_admin.id,
            plan_code=payload.plan_code,
            comment=payload.comment,
            idempotency_key=payload.idempotency_key,
        )
    except AdminSubscriptionCommentRequiredError as exc:
        exc.args = (translate("api.admin.errors.comment_required"),)
        raise api_error_from_exception(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            exc,
            error_code="admin_comment_required",
        ) from exc
    except SubscriptionPlanError as exc:
        raise api_error_from_exception(status.HTTP_404_NOT_FOUND, exc) from exc
    except PurchaseConflictError as exc:
        raise api_error_from_exception(status.HTTP_409_CONFLICT, exc) from exc
    except RemnawaveSyncError as exc:
        raise api_error_from_exception(status.HTTP_502_BAD_GATEWAY, exc) from exc

    return AdminSubscriptionGrantResponse(
        account_id=result.account.id,
        plan_code=result.grant.plan_code,
        subscription_grant_id=result.grant.id,
        audit_log_id=result.audit_log.id,
        subscription_status=result.account.subscription_status,
        subscription_expires_at=result.account.subscription_expires_at,
        subscription_url=result.account.subscription_url,
    )
