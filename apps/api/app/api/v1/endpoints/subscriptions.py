from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_account
from app.db.models import Account
from app.db.session import get_session
from app.schemas.subscription import SubscriptionStateResponse, TrialEligibilityResponse
from app.services.subscriptions import (
    RemnawaveSyncError,
    TrialEligibilityError,
    activate_trial,
    get_current_subscription,
    get_trial_eligibility,
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
