from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_account
from app.db.models import Account
from app.db.session import get_session
from app.schemas.bootstrap import BootstrapResponse
from app.services.subscriptions import get_current_subscription


router = APIRouter()


@router.get("/bootstrap/me", response_model=BootstrapResponse)
async def get_bootstrap_me(
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> BootstrapResponse:
    response = BootstrapResponse.from_account(current_account)
    response.subscription = await get_current_subscription(
        session, account=current_account
    )
    return response
