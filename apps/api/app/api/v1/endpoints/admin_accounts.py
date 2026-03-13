from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin
from app.db.models import Account, Admin
from app.db.session import get_session
from app.db.models.ledger import LedgerEntryType
from app.schemas.admin import (
    AdminAccountStatusChangeRequest,
    AdminAccountStatusChangeResponse,
    AdminBalanceAdjustmentRequest,
    AdminBalanceAdjustmentResponse,
    AdminAccountDetailResponse,
    AdminAccountLedgerHistoryResponse,
    AdminAccountLedgerEntryResponse,
    AdminAccountSearchItemResponse,
    AdminAccountSearchResponse,
    AdminSubscriptionGrantRequest,
    AdminSubscriptionGrantResponse,
)
from app.schemas.payment import SubscriptionPlanResponse
from app.services.admin_accounts import get_admin_account_detail, search_admin_accounts
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


router = APIRouter()


@router.get("/subscription-plans", response_model=list[SubscriptionPlanResponse])
async def list_admin_subscription_plans(
    _: Admin = Depends(get_current_admin),
) -> list[SubscriptionPlanResponse]:
    try:
        plans = get_subscription_plans()
    except SubscriptionPlanError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
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


@router.get("/{account_id}", response_model=AdminAccountDetailResponse)
async def read_account_detail(
    account_id: str,
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminAccountDetailResponse:
    detail = await get_admin_account_detail(session, account_id=account_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
    return AdminAccountDetailResponse.model_validate(detail, from_attributes=True)


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")

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
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> AdminBalanceAdjustmentResponse:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")

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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except InsufficientFundsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return AdminBalanceAdjustmentResponse(
        account_id=account.id,
        balance=account.balance,
        ledger_entry=AdminAccountLedgerEntryResponse.model_validate(entry, from_attributes=True),
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")

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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except AdminAccountStatusConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")

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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except SubscriptionPlanError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PurchaseConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RemnawaveSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return AdminSubscriptionGrantResponse(
        account_id=result.account.id,
        plan_code=result.grant.plan_code,
        subscription_grant_id=result.grant.id,
        audit_log_id=result.audit_log.id,
        subscription_status=result.account.subscription_status,
        subscription_expires_at=result.account.subscription_expires_at,
        subscription_url=result.account.subscription_url,
    )
