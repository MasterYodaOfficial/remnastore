from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_account
from app.db.models import Account
from app.db.session import get_session
from app.schemas.promo import (
    PromoPlanQuoteRequest,
    PromoPlanQuoteResponse,
    PromoRedeemRequest,
    PromoRedeemResponse,
)
from app.schemas.subscription import SubscriptionStateResponse
from app.services.plans import SubscriptionPlanError
from app.services.promos import (
    PromoBlockedError,
    PromoCodeNotFoundError,
    PromoConflictError,
    PromoValidationError,
    quote_plan_promo,
    redeem_promo_code,
    resolve_plan_checkout_amount,
)
from app.services.purchases import RemnawaveSyncError


router = APIRouter()


@router.post("/plans/{plan_code}/quote", response_model=PromoPlanQuoteResponse)
async def quote_plan_promo_effect(
    plan_code: str,
    payload: PromoPlanQuoteRequest,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> PromoPlanQuoteResponse:
    try:
        base_amount = resolve_plan_checkout_amount(plan_code=plan_code, currency=payload.currency.upper())
        quote = await quote_plan_promo(
            session,
            account=current_account,
            plan_code=plan_code,
            base_amount=base_amount,
            currency=payload.currency.upper(),
            code=payload.promo_code,
        )
    except SubscriptionPlanError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PromoCodeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PromoBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except PromoConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PromoValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return PromoPlanQuoteResponse(
        plan_code=quote.plan.code,
        promo_code=quote.promo_code.code,
        effect_type=quote.campaign.effect_type,
        original_amount=quote.original_amount,
        final_amount=quote.final_amount,
        discount_amount=quote.discount_amount,
        currency=quote.currency,
        original_duration_days=quote.original_duration_days,
        final_duration_days=quote.final_duration_days,
    )


@router.post("/redeem", response_model=PromoRedeemResponse)
async def redeem_promo(
    payload: PromoRedeemRequest,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> PromoRedeemResponse:
    try:
        result = await redeem_promo_code(
            session,
            account=current_account,
            code=payload.code,
            idempotency_key=payload.idempotency_key,
        )
    except PromoCodeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PromoBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except PromoConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PromoValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RemnawaveSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    promo_code = payload.code.strip().upper()
    return PromoRedeemResponse(
        promo_code=promo_code,
        effect_type=result.redemption.effect_type,
        status=result.redemption.status,
        balance=result.account.balance,
        balance_credit_amount=result.redemption.balance_credit_amount,
        granted_duration_days=result.redemption.granted_duration_days,
        subscription=SubscriptionStateResponse.from_account(result.account),
    )
