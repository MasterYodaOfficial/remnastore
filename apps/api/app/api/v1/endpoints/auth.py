from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, verify_telegram_init_data
from app.db.models import LoginSource
from app.db.session import get_session
from app.schemas.account import AccountResponse
from app.schemas.auth import AuthResponse, TelegramAuthRequest, TelegramReferralResultResponse
from app.services.accounts import AccountBlockedError, upsert_telegram_account
from app.services.referrals import (
    ReferralCodeNotFoundError,
    apply_telegram_referral_intent,
    record_telegram_referral_intent,
)

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

    try:
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
    except AccountBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    start_param = data.get("start_param")
    referral_result = None
    if isinstance(start_param, str) and start_param.startswith("ref_"):
        try:
            await record_telegram_referral_intent(
                session,
                telegram_id=int(user.get("id")),
                referral_code=start_param.removeprefix("ref_"),
            )
        except ReferralCodeNotFoundError:
            referral_result = TelegramReferralResultResponse(
                applied=False,
                created=False,
                reason="referral_code_not_found",
            )

    if referral_result is None:
        applied_referral_result = await apply_telegram_referral_intent(
            session,
            telegram_id=int(user.get("id")),
            account_id=account.id,
        )
        referral_result = (
            None
            if applied_referral_result is None
            else TelegramReferralResultResponse(
                applied=applied_referral_result.applied,
                created=applied_referral_result.created,
                reason=applied_referral_result.reason,
            )
        )

    token = create_access_token(
        {"sub": str(account.id), "telegram_id": account.telegram_id},
        secret=settings.jwt_secret,
        expires_in_seconds=settings.jwt_access_token_expires_seconds,
    )
    await session.refresh(account)

    return AuthResponse(
        access_token=token,
        account=AccountResponse.model_validate(account),
        referral_result=referral_result,
    )
