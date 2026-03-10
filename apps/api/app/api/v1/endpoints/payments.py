from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_account
from app.db.models import Account
from app.db.session import get_session
from app.schemas.payment import CreateYooKassaTopupRequest, PaymentIntentResponse
from app.services.payments import (
    PaymentConflictError,
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
    create_yookassa_topup_payment,
)

router = APIRouter()


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
