from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_account
from app.db.models import Account
from app.db.session import get_session
from app.schemas.payment import (
    CreateTelegramStarsPlanPurchaseRequest,
    CreateYooKassaPlanPurchaseRequest,
    CreateYooKassaTopupRequest,
    PaymentIntentResponse,
    PaymentStatusResponse,
    SubscriptionPlanResponse,
)
from app.domain.payments import PaymentProvider
from app.services.plans import SubscriptionPlanError, get_subscription_plans
from app.services.payments import (
    PaymentConflictError,
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
    PaymentNotFoundError,
    create_telegram_stars_plan_purchase_payment,
    create_yookassa_plan_purchase_payment,
    create_yookassa_topup_payment,
    get_payment_for_account,
)

router = APIRouter()


@router.get("/plans", response_model=list[SubscriptionPlanResponse])
async def list_subscription_plans() -> list[SubscriptionPlanResponse]:
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


@router.get("/status", response_model=PaymentStatusResponse)
async def get_payment_status(
    provider: PaymentProvider,
    provider_payment_id: str,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> PaymentStatusResponse:
    try:
        payment = await get_payment_for_account(
            session,
            account=current_account,
            provider=provider,
            provider_payment_id=provider_payment_id,
        )
    except PaymentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return PaymentStatusResponse(
        provider=payment.provider,
        flow_type=payment.flow_type,
        status=payment.status,
        amount=payment.amount,
        currency=payment.currency,
        provider_payment_id=payment.provider_payment_id,
        confirmation_url=payment.confirmation_url,
        expires_at=payment.expires_at,
        finalized_at=payment.finalized_at,
    )


@router.post("/yookassa/topup", response_model=PaymentIntentResponse)
async def create_yookassa_topup(
    payload: CreateYooKassaTopupRequest,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> PaymentIntentResponse:
    try:
        snapshot = await create_yookassa_topup_payment(
            session,
            account=current_account,
            amount_rub=payload.amount_rub,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
            description=payload.description,
            idempotency_key=payload.idempotency_key,
        )
    except PaymentGatewayConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except PaymentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PaymentGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return PaymentIntentResponse.model_validate(snapshot, from_attributes=True)


@router.post("/yookassa/plans/{plan_code}", response_model=PaymentIntentResponse)
async def create_yookassa_plan_purchase(
    plan_code: str,
    payload: CreateYooKassaPlanPurchaseRequest,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> PaymentIntentResponse:
    try:
        snapshot = await create_yookassa_plan_purchase_payment(
            session,
            account=current_account,
            plan_code=plan_code,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
            description=payload.description,
            idempotency_key=payload.idempotency_key,
        )
    except SubscriptionPlanError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PaymentGatewayConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except PaymentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PaymentGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return PaymentIntentResponse.model_validate(snapshot, from_attributes=True)


@router.post("/telegram-stars/plans/{plan_code}", response_model=PaymentIntentResponse)
async def create_telegram_stars_plan_purchase(
    plan_code: str,
    payload: CreateTelegramStarsPlanPurchaseRequest,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> PaymentIntentResponse:
    try:
        snapshot = await create_telegram_stars_plan_purchase_payment(
            session,
            account=current_account,
            plan_code=plan_code,
            description=payload.description,
            idempotency_key=payload.idempotency_key,
        )
    except SubscriptionPlanError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PaymentGatewayConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except PaymentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PaymentGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return PaymentIntentResponse.model_validate(snapshot, from_attributes=True)
