"""Public linking endpoints (no authentication required)."""

from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError, api_error, api_error_from_exception
from app.core.audit import build_request_audit_context, log_audit_event
from app.db.session import get_session
from app.schemas.account import AccountResponse
from app.services.account_linking import (
    AccountMergeConflictError,
    get_link_token,
    link_telegram_to_account,
    mark_link_token_consumed,
    LinkTokenExpiredError,
    LinkTokenAlreadyConsumedError,
    LinkTokenNotFoundError,
    LinkTokenTypeMismatchError,
)
from app.db.models import LinkType
from app.services.i18n import translate

router = APIRouter()


class LinkTelegramConfirmRequest(BaseModel):
    link_token: str
    telegram_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    is_premium: bool = False


class LinkBrowserConfirmRequest(BaseModel):
    link_token: str
    telegram_id: int


def _link_token_http_error(exc: Exception) -> ApiError:
    if isinstance(exc, LinkTokenNotFoundError):
        return api_error(
            status.HTTP_404_NOT_FOUND,
            translate("api.linking.errors.token_not_found"),
            error_code="token_not_found",
        )
    if isinstance(exc, LinkTokenExpiredError):
        return api_error(
            status.HTTP_400_BAD_REQUEST,
            translate("api.linking.errors.token_expired"),
            error_code="token_expired",
        )
    if isinstance(exc, LinkTokenAlreadyConsumedError):
        return api_error(
            status.HTTP_400_BAD_REQUEST,
            translate("api.linking.errors.token_already_used"),
            error_code="token_already_used",
        )
    if isinstance(exc, LinkTokenTypeMismatchError):
        return api_error(
            status.HTTP_400_BAD_REQUEST,
            translate("api.linking.errors.token_type_invalid"),
            error_code="token_type_invalid",
        )
    return api_error_from_exception(status.HTTP_400_BAD_REQUEST, exc)


@router.post("/link-telegram-confirm", response_model=AccountResponse)
async def confirm_telegram_link(
    payload: LinkTelegramConfirmRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    """Confirm and consume Telegram linking token (called from bot)."""
    request_context = build_request_audit_context(request)
    try:
        token = await get_link_token(
            session,
            link_token=payload.link_token,
            expected_link_type=LinkType.TELEGRAM_FROM_BROWSER,
        )
    except (
        LinkTokenNotFoundError,
        LinkTokenExpiredError,
        LinkTokenAlreadyConsumedError,
        LinkTokenTypeMismatchError,
    ) as exc:
        log_audit_event(
            "account.link.telegram_confirm",
            outcome="failure",
            category="security",
            reason=type(exc).__name__,
            telegram_id=payload.telegram_id,
            **request_context,
        )
        raise _link_token_http_error(exc) from exc

    token_account_id = token.account_id
    try:
        account = await link_telegram_to_account(
            session,
            account_id=token_account_id,
            telegram_id=payload.telegram_id,
            username=payload.username,
            first_name=payload.first_name,
            last_name=payload.last_name,
            is_premium=payload.is_premium,
        )
    except (ValueError, AccountMergeConflictError) as exc:
        await session.rollback()
        log_audit_event(
            "account.link.telegram_confirm",
            outcome="failure",
            category="security",
            reason=type(exc).__name__,
            account_id=token_account_id,
            telegram_id=payload.telegram_id,
            **request_context,
        )
        error_code = "account_not_found" if isinstance(exc, ValueError) else None
        raise api_error_from_exception(
            status.HTTP_400_BAD_REQUEST,
            exc,
            error_code=error_code,
        ) from exc

    mark_link_token_consumed(token)
    await session.commit()
    await session.refresh(account)
    log_audit_event(
        "account.link.telegram_confirm",
        outcome="success",
        category="security",
        account_id=account.id,
        telegram_id=payload.telegram_id,
        **request_context,
    )
    return AccountResponse.model_validate(account)


@router.post("/link-browser-confirm", response_model=AccountResponse)
async def confirm_browser_link(
    payload: LinkBrowserConfirmRequest,
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    """Legacy endpoint kept only to fail explicitly for deprecated bot-only flow."""
    del payload, session
    raise api_error(
        status.HTTP_400_BAD_REQUEST,
        translate("api.linking.errors.browser_complete_in_browser"),
        error_code="browser_complete_in_browser",
    )
