from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_account
from app.db.models import Account
from app.schemas.bootstrap import BootstrapResponse


router = APIRouter()


@router.get("/bootstrap/me", response_model=BootstrapResponse)
async def get_bootstrap_me(
    current_account: Account = Depends(get_current_account),
) -> BootstrapResponse:
    return BootstrapResponse.from_account(current_account)
