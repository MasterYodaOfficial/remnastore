from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_account
from app.db.models import Account
from app.db.session import get_session
from app.schemas.subscription import (
    SubscriptionStateResponse,
    TrialEligibilityResponse,
    WalletPlanPurchaseRequest,
)
from app.services.ledger import InsufficientFundsError
from app.services.plans import SubscriptionPlanError
from app.services.purchases import PurchaseConflictError
from app.services.promos import (
    PromoBlockedError,
    PromoCodeNotFoundError,
    PromoConflictError,
    PromoValidationError,
)
from app.services.subscriptions import (
    RemnawaveSyncError,
    TrialEligibilityError,
    SubscriptionPurchaseBlockedError,
    activate_trial,
    get_current_subscription,
    get_trial_eligibility,
    purchase_subscription_with_wallet,
    sync_current_subscription,
)

router = APIRouter()


@router.get("/", response_model=SubscriptionStateResponse)
async def read_current_subscription(
    current_account: Account = Depends(get_current_account),
) -> SubscriptionStateResponse:
    return await get_current_subscription(current_account)


@router.get("/trial-eligibility", response_model=TrialEligibilityResponse)
async def read_trial_eligibility(
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> TrialEligibilityResponse:
    return await get_trial_eligibility(session, account=current_account)


@router.post("/trial", response_model=SubscriptionStateResponse)
async def create_trial_subscription(
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> SubscriptionStateResponse:
    try:
        return await activate_trial(session, account=current_account)
    except TrialEligibilityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    except RemnawaveSyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post("/sync", response_model=SubscriptionStateResponse)
async def sync_subscription(
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> SubscriptionStateResponse:
    try:
        return await sync_current_subscription(session, account=current_account)
    except RemnawaveSyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post("/wallet/plans/{plan_code}", response_model=SubscriptionStateResponse)
async def purchase_with_wallet(
    plan_code: str,
    payload: WalletPlanPurchaseRequest,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> SubscriptionStateResponse:
    try:
        return await purchase_subscription_with_wallet(
            session,
            account=current_account,
            plan_code=plan_code,
            idempotency_key=payload.idempotency_key,
            promo_code=payload.promo_code,
        )
    except SubscriptionPlanError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PromoCodeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InsufficientFundsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PurchaseConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PromoConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except SubscriptionPurchaseBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except PromoBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except PromoValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RemnawaveSyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
