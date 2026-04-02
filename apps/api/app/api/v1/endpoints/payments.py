from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import api_error, api_error_from_exception
from app.api.dependencies import get_current_account
from app.db.models import Account
from app.db.session import get_session
from app.schemas.payment import (
    CreateTelegramStarsPlanPurchaseRequest,
    CreateYooKassaPlanPurchaseRequest,
    CreateYooKassaTopupRequest,
    PaymentIntentResponse,
    PaymentListItemResponse,
    PaymentListResponse,
    PaymentStatusResponse,
    SubscriptionPlanResponse,
)
from app.domain.payments import PaymentProvider
from app.services.plans import SubscriptionPlanError, get_subscription_plans
from app.services.payments import (
    PaymentAccountBlockedError,
    PaymentConflictError,
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
    PaymentNotFoundError,
    create_telegram_stars_plan_purchase_payment,
    create_yookassa_plan_purchase_payment,
    create_yookassa_topup_payment,
    get_payment_for_account,
    list_account_payments,
)
from app.services.promos import (
    PromoBlockedError,
    PromoCodeNotFoundError,
    PromoConflictError,
    PromoValidationError,
)
from app.services.i18n import translate

router = APIRouter()


@router.get("/plans", response_model=list[SubscriptionPlanResponse])
async def list_subscription_plans() -> list[SubscriptionPlanResponse]:
    try:
        plans = get_subscription_plans()
    except SubscriptionPlanError as exc:
        raise api_error_from_exception(
            status.HTTP_503_SERVICE_UNAVAILABLE, exc
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


@router.get("", response_model=PaymentListResponse)
async def list_payments(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    active_only: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> PaymentListResponse:
    payments, total = await list_account_payments(
        session,
        account=current_account,
        limit=limit,
        offset=offset,
        active_only=active_only,
    )
    return PaymentListResponse(
        items=[
            PaymentListItemResponse.model_validate(item, from_attributes=True)
            for item in payments
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


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
        raise api_error_from_exception(status.HTTP_404_NOT_FOUND, exc) from exc

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
        raise api_error_from_exception(
            status.HTTP_503_SERVICE_UNAVAILABLE, exc
        ) from exc
    except PaymentConflictError as exc:
        raise api_error_from_exception(status.HTTP_409_CONFLICT, exc) from exc
    except PaymentAccountBlockedError as exc:
        raise api_error_from_exception(status.HTTP_403_FORBIDDEN, exc) from exc
    except PaymentGatewayError as exc:
        raise api_error(
            status.HTTP_502_BAD_GATEWAY,
            translate("api.payments.errors.gateway_failed"),
            error_code="gateway_failed",
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
            promo_code=payload.promo_code,
        )
    except SubscriptionPlanError as exc:
        raise api_error_from_exception(status.HTTP_404_NOT_FOUND, exc) from exc
    except PromoCodeNotFoundError as exc:
        raise api_error_from_exception(status.HTTP_404_NOT_FOUND, exc) from exc
    except PaymentGatewayConfigurationError as exc:
        raise api_error_from_exception(
            status.HTTP_503_SERVICE_UNAVAILABLE, exc
        ) from exc
    except PaymentConflictError as exc:
        raise api_error_from_exception(status.HTTP_409_CONFLICT, exc) from exc
    except PromoConflictError as exc:
        raise api_error_from_exception(status.HTTP_409_CONFLICT, exc) from exc
    except PaymentAccountBlockedError as exc:
        raise api_error_from_exception(status.HTTP_403_FORBIDDEN, exc) from exc
    except PromoBlockedError as exc:
        raise api_error_from_exception(status.HTTP_403_FORBIDDEN, exc) from exc
    except PromoValidationError as exc:
        raise api_error_from_exception(
            status.HTTP_422_UNPROCESSABLE_ENTITY, exc
        ) from exc
    except PaymentGatewayError as exc:
        raise api_error(
            status.HTTP_502_BAD_GATEWAY,
            translate("api.payments.errors.gateway_failed"),
            error_code="gateway_failed",
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
            promo_code=payload.promo_code,
        )
    except SubscriptionPlanError as exc:
        raise api_error_from_exception(status.HTTP_404_NOT_FOUND, exc) from exc
    except PromoCodeNotFoundError as exc:
        raise api_error_from_exception(status.HTTP_404_NOT_FOUND, exc) from exc
    except PaymentGatewayConfigurationError as exc:
        raise api_error_from_exception(
            status.HTTP_503_SERVICE_UNAVAILABLE, exc
        ) from exc
    except PaymentConflictError as exc:
        raise api_error_from_exception(status.HTTP_409_CONFLICT, exc) from exc
    except PromoConflictError as exc:
        raise api_error_from_exception(status.HTTP_409_CONFLICT, exc) from exc
    except PaymentAccountBlockedError as exc:
        raise api_error_from_exception(status.HTTP_403_FORBIDDEN, exc) from exc
    except PromoBlockedError as exc:
        raise api_error_from_exception(status.HTTP_403_FORBIDDEN, exc) from exc
    except PromoValidationError as exc:
        raise api_error_from_exception(
            status.HTTP_422_UNPROCESSABLE_ENTITY, exc
        ) from exc
    except PaymentGatewayError as exc:
        raise api_error(
            status.HTTP_502_BAD_GATEWAY,
            translate("api.payments.errors.gateway_failed"),
            error_code="gateway_failed",
        ) from exc

    return PaymentIntentResponse.model_validate(snapshot, from_attributes=True)
