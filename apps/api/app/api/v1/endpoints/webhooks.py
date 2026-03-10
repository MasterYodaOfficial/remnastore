import hashlib
import hmac
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.schemas.payment import (
    PaymentWebhookProcessResponse,
    TelegramStarsPreCheckoutRequest,
    TelegramStarsPreCheckoutResponse,
)
from app.services.payments import (
    PaymentConflictError,
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
    PaymentWebhookProcessResult,
    process_telegram_stars_webhook,
    process_yookassa_webhook,
    validate_telegram_stars_pre_checkout,
)
from app.services.subscriptions import RemnawaveSyncError, sync_subscription_by_remnawave_user_uuid

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


def _extract_remnawave_user_uuid(payload: dict) -> UUID:
    event_data = payload.get("data")
    if isinstance(event_data, str):
        try:
            return UUID(event_data)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid Remnawave user uuid",
            ) from exc

    if isinstance(event_data, dict):
        raw_uuid = event_data.get("uuid")
        if isinstance(raw_uuid, str):
            try:
                return UUID(raw_uuid)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="invalid Remnawave user uuid",
                ) from exc

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="invalid Remnawave webhook payload",
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


@router.post("/remnawave")
async def remnawave_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_remnawave_signature: str | None = Header(default=None),
) -> dict:
    raw_body = await request.body()
    _verify_remnawave_signature(raw_body, x_remnawave_signature)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid JSON payload",
        ) from exc

    event = payload.get("event")
    if not isinstance(event, str) or not event.startswith("user."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="unsupported Remnawave webhook event",
        )

    remnawave_user_uuid = _extract_remnawave_user_uuid(payload)

    try:
        account = await sync_subscription_by_remnawave_user_uuid(
            session,
            remnawave_user_uuid=remnawave_user_uuid,
        )
    except RemnawaveSyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return {
        "ok": True,
        "processed": account is not None,
        "account_id": str(account.id) if account is not None else None,
    }
