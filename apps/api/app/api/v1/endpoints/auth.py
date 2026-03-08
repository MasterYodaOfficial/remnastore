from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, verify_telegram_init_data
from app.db.models import LoginSource
from app.db.session import get_session
from app.schemas.account import AccountResponse
from app.schemas.auth import AuthResponse, TelegramAuthRequest
from app.services.accounts import upsert_telegram_account

router = APIRouter()


@router.post("/telegram/webapp", response_model=AuthResponse, status_code=status.HTTP_200_OK)
async def auth_telegram_webapp(
    payload: TelegramAuthRequest, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    data = verify_telegram_init_data(
        payload.init_data,
        bot_token=settings.telegram_bot_token,
        max_age_seconds=settings.telegram_init_data_ttl_seconds,
    )

    user = data.get("user")
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="init data missing user")

    account = await upsert_telegram_account(
        session,
        telegram_id=int(user.get("id")),
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        is_premium=bool(user.get("is_premium", False)),
        locale=user.get("language_code"),
        email=None,
        display_name=None,
        last_login_source=LoginSource.TELEGRAM_WEBAPP,
    )

    token = create_access_token(
        {"sub": str(account.id), "telegram_id": account.telegram_id},
        secret=settings.jwt_secret,
        expires_in_seconds=settings.jwt_access_token_expires_seconds,
    )

    return AuthResponse(access_token=token, account=AccountResponse.model_validate(account))
