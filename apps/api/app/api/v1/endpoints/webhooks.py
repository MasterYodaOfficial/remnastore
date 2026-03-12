import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.schemas.payment import (
    PaymentWebhookProcessResponse,
    TelegramStarsPreCheckoutRequest,
    TelegramStarsPreCheckoutResponse,
)
from app.schemas.referral import TelegramReferralIntentRequest, TelegramReferralIntentResponse
from app.services.payments import (
    PaymentConflictError,
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
    PaymentWebhookProcessResult,
    process_telegram_stars_webhook,
    process_yookassa_webhook,
    validate_telegram_stars_pre_checkout,
)
from app.services.referrals import ReferralCodeNotFoundError, record_telegram_referral_intent
from app.services.remnawave_webhooks import (
    RemnawaveWebhookPayloadError,
    process_remnawave_webhook,
)

router = APIRouter()


def _verify_remnawave_signature(raw_body: bytes, signature: str | None) -> None:
    if not settings.remnawave_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="REMNAWAVE_WEBHOOK_SECRET is not configured",
        )

    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing Remnawave signature",
        )

    expected_signature = hmac.new(
        settings.remnawave_webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid Remnawave signature",
        )


def _verify_internal_api_token(authorization: str | None) -> None:
    if not settings.api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_TOKEN is not configured",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing internal api token",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token or token != settings.api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal api token",
        )

def _payment_webhook_response(result: PaymentWebhookProcessResult) -> PaymentWebhookProcessResponse:
    return PaymentWebhookProcessResponse(
        payment_id=result.payment_id,
        provider_payment_id=result.provider_payment_id,
        status=result.status,
        duplicate=result.duplicate,
        ledger_applied=result.ledger_applied,
        subscription_applied=result.subscription_applied,
    )


@router.post("/payments/yookassa", response_model=PaymentWebhookProcessResponse)
async def yookassa_payments_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> PaymentWebhookProcessResponse:
    raw_body = await request.body()
    headers = {key: value for key, value in request.headers.items()}

    try:
        result = await process_yookassa_webhook(
            session,
            raw_body=raw_body,
            headers=headers,
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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return _payment_webhook_response(result)


@router.post("/payments/telegram-stars/pre-checkout", response_model=TelegramStarsPreCheckoutResponse)
async def telegram_stars_pre_checkout(
    payload: TelegramStarsPreCheckoutRequest,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> TelegramStarsPreCheckoutResponse:
    _verify_internal_api_token(authorization)
    ok, error_message = await validate_telegram_stars_pre_checkout(
        session,
        telegram_id=payload.telegram_id,
        invoice_payload=payload.invoice_payload,
        total_amount=payload.total_amount,
        currency=payload.currency,
    )
    return TelegramStarsPreCheckoutResponse(ok=ok, error_message=error_message)


@router.post("/payments/telegram-stars", response_model=PaymentWebhookProcessResponse)
async def telegram_stars_payments_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> PaymentWebhookProcessResponse:
    _verify_internal_api_token(authorization)
    raw_body = await request.body()
    headers = {key: value for key, value in request.headers.items()}

    try:
        result = await process_telegram_stars_webhook(
            session,
            raw_body=raw_body,
            headers=headers,
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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return _payment_webhook_response(result)


@router.post("/referrals/telegram-start", response_model=TelegramReferralIntentResponse)
async def telegram_referral_start_webhook(
    payload: TelegramReferralIntentRequest,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> TelegramReferralIntentResponse:
    _verify_internal_api_token(authorization)
    try:
        await record_telegram_referral_intent(
            session,
            telegram_id=payload.telegram_id,
            referral_code=payload.referral_code,
        )
    except ReferralCodeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return TelegramReferralIntentResponse()


@router.post("/remnawave")
async def remnawave_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_remnawave_signature: str | None = Header(default=None),
) -> dict:
    raw_body = await request.body()
    _verify_remnawave_signature(raw_body, x_remnawave_signature)

    try:
        result = await process_remnawave_webhook(
            session,
            raw_body=raw_body,
        )
    except RemnawaveWebhookPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {
        "ok": True,
        "event": result.event,
        "scope": result.scope,
        "handled": result.handled,
        "processed": result.processed,
        "account_id": str(result.account_id) if result.account_id is not None else None,
        "notification_types": [notification_type.value for notification_type in result.notification_types],
    }
