from fastapi import APIRouter, Depends
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_account
from app.db.session import get_session
from app.schemas.account import AccountResponse, TelegramUpsertRequest
from app.services.accounts import upsert_telegram_account
from app.db.models import Account

router = APIRouter()


@router.post("/accounts/telegram", response_model=AccountResponse)
async def upsert_account_from_telegram(
    payload: TelegramUpsertRequest,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> AccountResponse:
    # Ensure the caller updates only their own account
    if current_account.telegram_id != payload.telegram_id:
        raise HTTPException(status_code=403, detail="cannot modify another account")

    account = await upsert_telegram_account(
        session,
        telegram_id=payload.telegram_id,
        username=payload.username,
        first_name=payload.first_name,
        last_name=payload.last_name,
        is_premium=payload.is_premium,
        locale=payload.locale,
        email=payload.email,
        display_name=payload.display_name,
        last_login_source=payload.last_login_source,
    )
    return account


@router.get("/accounts/me", response_model=AccountResponse)
async def get_account_me(
    current_account: Account = Depends(get_current_account),
) -> AccountResponse:
    return current_account
