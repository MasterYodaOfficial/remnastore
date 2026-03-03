from fastapi import APIRouter, Depends
from fastapi import HTTPException, Query

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.account import AccountResponse, TelegramUpsertRequest
from app.services.accounts import upsert_telegram_account, get_account_by_telegram_id

router = APIRouter()


@router.post("/accounts/telegram", response_model=AccountResponse)
async def upsert_account_from_telegram(
    payload: TelegramUpsertRequest, session: AsyncSession = Depends(get_session)
) -> AccountResponse:
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
    telegram_id: int = Query(..., description="Telegram user id"),
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    account = await get_account_by_telegram_id(session, telegram_id=telegram_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return account
