from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError, api_error, api_error_from_exception
from app.api.dependencies import bearer_scheme, get_current_account
from app.core.audit import build_request_audit_context, log_audit_event
from app.core.config import settings
from app.db.session import get_session
from app.schemas.account import (
    AccountResponse,
    LinkBrowserResponse,
    LinkTelegramResponse,
    TelegramUpsertRequest,
)
from app.services.accounts import upsert_telegram_account
from app.services.account_linking import (
    AccountMergeConflictError,
    create_telegram_link_token,
    create_browser_link_token,
    get_link_token,
    link_browser_oauth_to_telegram_account,
    mark_link_token_consumed,
    LinkTokenAlreadyConsumedError,
    LinkTokenExpiredError,
    LinkTokenNotFoundError,
    LinkTokenTypeMismatchError,
)
from app.db.models import Account, LinkType
from app.services.cache import get_cache
from app.services.i18n import translate

router = APIRouter()


class LinkBrowserCompleteRequest(BaseModel):
    link_token: str


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


@router.post("/accounts/telegram", response_model=AccountResponse)
async def upsert_account_from_telegram(
    payload: TelegramUpsertRequest,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> AccountResponse:
    # Ensure the caller updates only their own account
    if current_account.telegram_id != payload.telegram_id:
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            translate("api.linking.errors.cannot_modify_another_account"),
            error_code="cannot_modify_another_account",
        )

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
    cache = get_cache()
    cache_key = cache.account_response_key(str(current_account.id))
    cached_response = await cache.get_json(cache_key)

    if isinstance(cached_response, dict):
        try:
            return AccountResponse.model_validate(cached_response)
        except Exception:
            await cache.delete(cache_key)

    response = AccountResponse.model_validate(current_account)
    await cache.set_json(
        cache_key,
        response.model_dump(mode="json"),
        settings.account_response_cache_ttl_seconds,
    )
    return response


@router.post("/accounts/link-telegram", response_model=LinkTelegramResponse)
async def generate_telegram_link(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> LinkTelegramResponse:
    """Generate a link to bind Telegram account to browser OAuth account."""
    request_context = build_request_audit_context(request)
    if current_account.telegram_id is not None:
        log_audit_event(
            "account.link.telegram_token.create",
            outcome="denied",
            category="security",
            reason="account_already_linked",
            account_id=current_account.id,
            telegram_id=current_account.telegram_id,
            **request_context,
        )
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            translate("api.linking.errors.telegram_already_linked"),
            error_code="telegram_already_linked",
        )

    link_token, link_url_template = await create_telegram_link_token(
        session,
        account_id=current_account.id,
        ttl_seconds=3600,
    )
    await session.commit()

    # Replace placeholder with actual bot username from config
    link_url = link_url_template.format(bot_username=settings.telegram_bot_username)
    log_audit_event(
        "account.link.telegram_token.create",
        outcome="success",
        category="security",
        account_id=current_account.id,
        expires_in_seconds=3600,
        **request_context,
    )

    return LinkTelegramResponse(
        link_url=link_url,
        link_token=link_token,
        expires_in_seconds=3600,
    )


@router.post("/accounts/link-browser", response_model=LinkBrowserResponse)
async def generate_browser_link(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> LinkBrowserResponse:
    """Generate a browser URL to bind OAuth auth to the current Telegram account."""
    request_context = build_request_audit_context(request)
    if current_account.telegram_id is None:
        log_audit_event(
            "account.link.browser_token.create",
            outcome="denied",
            category="security",
            reason="telegram_account_required",
            account_id=current_account.id,
            **request_context,
        )
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            translate("api.linking.errors.telegram_required"),
            error_code="telegram_required",
        )

    if not settings.webapp_url:
        log_audit_event(
            "account.link.browser_token.create",
            outcome="error",
            category="security",
            reason="webapp_url_missing",
            account_id=current_account.id,
            telegram_id=current_account.telegram_id,
            **request_context,
        )
        raise api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            translate("api.linking.errors.webapp_url_missing"),
            error_code="webapp_url_missing",
        )

    link_token, link_url_template = await create_browser_link_token(
        session,
        account_id=current_account.id,
        webapp_url=settings.webapp_url,
        ttl_seconds=3600,
    )
    await session.commit()
    log_audit_event(
        "account.link.browser_token.create",
        outcome="success",
        category="security",
        account_id=current_account.id,
        telegram_id=current_account.telegram_id,
        expires_in_seconds=3600,
        **request_context,
    )

    return LinkBrowserResponse(
        link_url=link_url_template,
        link_token=link_token,
        expires_in_seconds=3600,
    )


@router.post("/accounts/link-browser-complete", response_model=AccountResponse)
async def complete_browser_link(
    payload: LinkBrowserCompleteRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    current_account: Account = Depends(get_current_account),
) -> AccountResponse:
    """Complete Telegram -> browser linking after browser auth succeeds."""
    request_context = build_request_audit_context(request)
    try:
        token = await get_link_token(
            session,
            link_token=payload.link_token,
            expected_link_type=LinkType.BROWSER_FROM_TELEGRAM,
        )
    except (
        LinkTokenNotFoundError,
        LinkTokenExpiredError,
        LinkTokenAlreadyConsumedError,
        LinkTokenTypeMismatchError,
    ) as exc:
        log_audit_event(
            "account.link.browser_complete",
            outcome="failure",
            category="security",
            reason=type(exc).__name__,
            browser_account_id=current_account.id,
            **request_context,
        )
        raise _link_token_http_error(exc) from exc

    try:
        account = await link_browser_oauth_to_telegram_account(
            session,
            telegram_account_id=token.account_id,
            browser_account_id=current_account.id,
        )
    except (ValueError, AccountMergeConflictError) as exc:
        await session.rollback()
        log_audit_event(
            "account.link.browser_complete",
            outcome="failure",
            category="security",
            reason=type(exc).__name__,
            telegram_account_id=token.account_id,
            browser_account_id=current_account.id,
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

    if credentials is not None:
        cache = get_cache()
        await cache.set_str(
            cache.auth_token_account_key(credentials.credentials),
            str(account.id),
            settings.auth_token_cache_ttl_seconds,
        )
    log_audit_event(
        "account.link.browser_complete",
        outcome="success",
        category="security",
        account_id=account.id,
        telegram_account_id=token.account_id,
        browser_account_id=current_account.id,
        **request_context,
    )

    return AccountResponse.model_validate(account)
