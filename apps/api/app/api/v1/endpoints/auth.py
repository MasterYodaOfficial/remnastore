from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import api_error, api_error_from_exception
from app.core.audit import build_request_audit_context, log_audit_event
from app.core.config import settings
from app.core.security import create_access_token, verify_telegram_init_data
from app.db.models import LoginSource
from app.db.session import get_session
from app.schemas.account import AccountResponse
from app.schemas.auth import (
    AuthResponse,
    TelegramAuthRequest,
    TelegramReferralResultResponse,
)
from app.services.account_events import append_account_event
from app.services.accounts import (
    AccountBlockedError,
    upsert_telegram_account,
)
from app.services.i18n import translate
from app.services.referrals import (
    ReferralCodeNotFoundError,
    apply_telegram_referral_intent,
    record_telegram_referral_intent,
)

router = APIRouter()


def _build_browser_auth_response(
    account,
    *,
    avatar_url: str | None = None,
    referral_result: TelegramReferralResultResponse | None = None,
) -> AuthResponse:
    token = create_access_token(
        {"sub": str(account.id), "telegram_id": account.telegram_id},
        secret=settings.jwt_secret,
        expires_in_seconds=settings.jwt_access_token_expires_seconds,
    )
    return AuthResponse(
        access_token=token,
        account=AccountResponse.model_validate(account),
        referral_result=referral_result,
        avatar_url=avatar_url,
    )


@router.post(
    "/telegram/webapp", response_model=AuthResponse, status_code=status.HTTP_200_OK
)
async def auth_telegram_webapp(
    payload: TelegramAuthRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    request_context = build_request_audit_context(request)
    try:
        data = verify_telegram_init_data(
            payload.init_data,
            bot_token=settings.telegram_bot_token,
            max_age_seconds=settings.telegram_init_data_ttl_seconds,
        )
    except HTTPException as exc:
        log_audit_event(
            "auth.telegram_webapp",
            outcome="failure",
            category="security",
            reason=str(exc.detail),
            **request_context,
        )
        raise

    user = data.get("user")
    if not user:
        log_audit_event(
            "auth.telegram_webapp",
            outcome="failure",
            category="security",
            reason="init_data_missing_user",
            **request_context,
        )
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            translate("api.auth.errors.init_data_missing_user"),
            error_code="init_data_missing_user",
        )

    telegram_id = int(user.get("id"))
    try:
        account = await upsert_telegram_account(
            session,
            telegram_id=telegram_id,
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
        log_audit_event(
            "auth.telegram_webapp",
            outcome="denied",
            category="security",
            reason="account_blocked",
            telegram_id=telegram_id,
            **request_context,
        )
        raise api_error_from_exception(status.HTTP_403_FORBIDDEN, exc) from exc

    start_param = data.get("start_param")
    referral_result = None
    if isinstance(start_param, str) and start_param.startswith("ref_"):
        try:
            await record_telegram_referral_intent(
                session,
                telegram_id=telegram_id,
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
            telegram_id=telegram_id,
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

    await append_account_event(
        session,
        account_id=account.id,
        actor_account_id=account.id,
        event_type="auth.telegram_webapp",
        source="api",
        payload={
            "telegram_id": telegram_id,
            "referral_applied": None
            if referral_result is None
            else referral_result.applied,
            "referral_reason": None
            if referral_result is None
            else referral_result.reason,
        },
    )
    await session.commit()
    await session.refresh(account)
    log_audit_event(
        "auth.telegram_webapp",
        outcome="success",
        category="security",
        account_id=account.id,
        telegram_id=telegram_id,
        referral_applied=None if referral_result is None else referral_result.applied,
        referral_reason=None if referral_result is None else referral_result.reason,
        **request_context,
    )

    return _build_browser_auth_response(
        account,
        referral_result=referral_result,
    )
