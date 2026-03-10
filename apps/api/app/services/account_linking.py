"""Service for managing account linking tokens and operations."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Account,
    AuthAccount,
    AuthLinkToken,
    AuthProvider,
    LoginSource,
    LinkType,
)
from app.services.cache import get_cache
from app.services.ledger import transfer_balance_for_merge


class LinkTokenExpiredError(Exception):
    """Raised when link token has expired."""
    pass


class LinkTokenAlreadyConsumedError(Exception):
    """Raised when link token was already consumed."""
    pass


class LinkTokenNotFoundError(Exception):
    """Raised when link token doesn't exist."""
    pass


class LinkTokenTypeMismatchError(Exception):
    """Raised when link token type doesn't match the requested flow."""
    pass


class AccountMergeConflictError(Exception):
    """Raised when accounts cannot be merged safely."""
    pass


def _utcnow() -> datetime:
    """Return an aware UTC datetime for DB timestamps and comparisons."""
    return datetime.now(timezone.utc)


async def create_telegram_link_token(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    ttl_seconds: int = 3600,
) -> tuple[str, str]:
    """
    Create a link token for Telegram account linking from browser.
    
    Returns:
        (link_token, telegram_link_url)
        Example URL: https://t.me/bot_username?start=link_ABC123
    """
    link_token = f"link_{secrets.token_urlsafe(16)}"
    expires_at = _utcnow() + timedelta(seconds=ttl_seconds)
    
    token = AuthLinkToken(
        account_id=account_id,
        link_token=link_token,
        provider=AuthProvider.SUPABASE,  # Marker for browser OAuth linking
        provider_uid="telegram_link",  # Marker value
        link_type=LinkType.TELEGRAM_FROM_BROWSER,
        expires_at=expires_at,
    )
    
    session.add(token)
    await session.flush()
    
    # Return token and URL template (bot username will be set in config)
    return link_token, f"https://t.me/{{bot_username}}?start={link_token}"


async def create_browser_link_token(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    webapp_url: str,
    ttl_seconds: int = 3600,
) -> tuple[str, str]:
    """
    Create a link token for browser OAuth linking from Telegram.

    Returns:
        (link_token, browser_link_url)
        Example: https://app.example.com/?link_token=link_XYZ789_BROWSER&link_flow=browser
    """
    link_token = f"link_{secrets.token_urlsafe(16)}_BROWSER"
    expires_at = _utcnow() + timedelta(seconds=ttl_seconds)

    token = AuthLinkToken(
        account_id=account_id,
        link_token=link_token,
        provider=AuthProvider.SUPABASE,
        provider_uid="browser_link",
        link_type=LinkType.BROWSER_FROM_TELEGRAM,
        expires_at=expires_at,
    )

    session.add(token)
    await session.flush()

    webapp_base_url = webapp_url.rstrip("/")
    return (
        link_token,
        f"{webapp_base_url}/?link_token={link_token}&link_flow=browser",
    )


async def get_link_token(
    session: AsyncSession,
    *,
    link_token: str,
    expected_link_type: Optional[LinkType] = None,
) -> AuthLinkToken:
    """
    Lock and validate a link token.

    Args:
        link_token: The token to consume
        expected_link_type: Optional flow guard

    Raises:
        LinkTokenNotFoundError: Token doesn't exist
        LinkTokenExpiredError: Token has expired
        LinkTokenAlreadyConsumedError: Token was already consumed
        LinkTokenTypeMismatchError: Token belongs to a different linking flow
    """
    result = await session.execute(
        select(AuthLinkToken)
        .where(AuthLinkToken.link_token == link_token)
        .with_for_update()
    )
    token = result.scalar_one_or_none()

    if token is None:
        raise LinkTokenNotFoundError(f"Link token not found: {link_token}")

    if token.consumed_at is not None:
        raise LinkTokenAlreadyConsumedError(f"Link token already consumed: {link_token}")

    if _utcnow() >= token.expires_at:
        raise LinkTokenExpiredError(f"Link token expired: {link_token}")

    if expected_link_type is not None and token.link_type != expected_link_type:
        raise LinkTokenTypeMismatchError(
            f"Unexpected link token type: {token.link_type}"
        )

    return token


def mark_link_token_consumed(token: AuthLinkToken) -> None:
    """Mark a link token as consumed after a successful linking operation."""
    token.consumed_at = _utcnow()


async def _load_account_for_update(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
) -> Account:
    result = await session.execute(
        select(Account).where(Account.id == account_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise ValueError(f"Account not found: {account_id}")
    return account


def _ensure_no_scalar_conflicts(target: Account, source: Account) -> None:
    conflict_fields = (
        ("telegram_id", target.telegram_id, source.telegram_id),
        ("email", target.email, source.email),
        ("remnawave_user_uuid", target.remnawave_user_uuid, source.remnawave_user_uuid),
        ("subscription_url", target.subscription_url, source.subscription_url),
        ("subscription_status", target.subscription_status, source.subscription_status),
        ("subscription_expires_at", target.subscription_expires_at, source.subscription_expires_at),
        (
            "subscription_last_synced_at",
            target.subscription_last_synced_at,
            source.subscription_last_synced_at,
        ),
        ("trial_used_at", target.trial_used_at, source.trial_used_at),
        ("trial_ends_at", target.trial_ends_at, source.trial_ends_at),
        ("referred_by_account_id", target.referred_by_account_id, source.referred_by_account_id),
    )
    for field_name, target_value, source_value in conflict_fields:
        if source_value is None or target_value is None:
            continue
        if target_value != source_value:
            raise AccountMergeConflictError(
                f"Cannot merge accounts with different {field_name}"
            )


async def _move_auth_accounts(
    session: AsyncSession,
    *,
    source_account_id: uuid.UUID,
    target_account_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(AuthAccount).where(AuthAccount.account_id == source_account_id)
    )
    source_auth_accounts = result.scalars().all()

    result = await session.execute(
        select(AuthAccount).where(AuthAccount.account_id == target_account_id)
    )
    target_auth_accounts = {
        (auth.provider, auth.provider_uid): auth for auth in result.scalars().all()
    }

    for auth_account in source_auth_accounts:
        key = (auth_account.provider, auth_account.provider_uid)
        existing = target_auth_accounts.get(key)
        if existing is None:
            auth_account.account_id = target_account_id
            target_auth_accounts[key] = auth_account
            continue

        existing.email = existing.email or auth_account.email
        existing.display_name = existing.display_name or auth_account.display_name
        await session.delete(auth_account)


async def _clear_account_cache(*account_ids: uuid.UUID) -> None:
    cache = get_cache()
    cache_keys = [cache.account_response_key(str(account_id)) for account_id in account_ids]
    await cache.delete(*cache_keys)


async def merge_accounts(
    session: AsyncSession,
    *,
    source_account_id: uuid.UUID,
    target_account_id: uuid.UUID,
    last_login_source: LoginSource,
) -> Account:
    """Merge source account into target account and return target."""
    target_account = await _load_account_for_update(session, account_id=target_account_id)

    if source_account_id == target_account_id:
        target_account.last_login_source = last_login_source
        target_account.last_seen_at = _utcnow()
        await session.flush()
        await _clear_account_cache(target_account.id)
        return target_account

    source_account = await _load_account_for_update(session, account_id=source_account_id)
    _ensure_no_scalar_conflicts(target_account, source_account)

    moved_telegram_id = source_account.telegram_id if target_account.telegram_id is None else None

    # Flush source unique values away before target takes them to avoid transient unique violations.
    if moved_telegram_id is not None:
        source_account.telegram_id = None
        await session.flush()

    target_account.email = target_account.email or source_account.email
    target_account.display_name = target_account.display_name or source_account.display_name
    target_account.telegram_id = target_account.telegram_id or moved_telegram_id
    target_account.username = target_account.username or source_account.username
    target_account.first_name = target_account.first_name or source_account.first_name
    target_account.last_name = target_account.last_name or source_account.last_name
    target_account.is_premium = target_account.is_premium or source_account.is_premium
    target_account.locale = target_account.locale or source_account.locale
    target_account.remnawave_user_uuid = (
        target_account.remnawave_user_uuid or source_account.remnawave_user_uuid
    )
    target_account.subscription_url = target_account.subscription_url or source_account.subscription_url
    target_account.subscription_status = (
        target_account.subscription_status or source_account.subscription_status
    )
    target_account.subscription_expires_at = (
        target_account.subscription_expires_at or source_account.subscription_expires_at
    )
    target_account.subscription_last_synced_at = (
        target_account.subscription_last_synced_at or source_account.subscription_last_synced_at
    )
    target_account.subscription_is_trial = (
        target_account.subscription_is_trial or source_account.subscription_is_trial
    )
    target_account.trial_used_at = target_account.trial_used_at or source_account.trial_used_at
    target_account.trial_ends_at = target_account.trial_ends_at or source_account.trial_ends_at
    target_account.referred_by_account_id = (
        target_account.referred_by_account_id or source_account.referred_by_account_id
    )

    if source_account.balance > 0:
        await transfer_balance_for_merge(
            session,
            source_account=source_account,
            target_account=target_account,
            amount=source_account.balance,
            reference_id=uuid.uuid4().hex,
        )
    target_account.referral_earnings += source_account.referral_earnings
    target_account.referrals_count += source_account.referrals_count
    target_account.referral_reward_rate = max(
        float(target_account.referral_reward_rate or 0),
        float(source_account.referral_reward_rate or 0),
    )
    target_account.last_login_source = last_login_source
    target_account.last_seen_at = _utcnow()

    await _move_auth_accounts(
        session,
        source_account_id=source_account.id,
        target_account_id=target_account.id,
    )
    await session.flush()
    await session.delete(source_account)
    await session.flush()
    await _clear_account_cache(source_account.id, target_account.id)
    return target_account


async def link_telegram_to_account(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    is_premium: bool = False,
) -> Account:
    """
    Link a Telegram account to an existing browser OAuth account.
    """
    account = await _load_account_for_update(session, account_id=account_id)

    result = await session.execute(
        select(Account).where(Account.telegram_id == telegram_id).with_for_update()
    )
    telegram_account = result.scalar_one_or_none()

    if telegram_account is not None and telegram_account.id != account.id:
        account = await merge_accounts(
            session,
            source_account_id=telegram_account.id,
            target_account_id=account.id,
            last_login_source=LoginSource.BROWSER_OAUTH,
        )

    account.telegram_id = telegram_id
    account.username = username or account.username
    account.first_name = first_name or account.first_name
    account.last_name = last_name or account.last_name
    account.is_premium = account.is_premium or is_premium
    account.last_login_source = LoginSource.BROWSER_OAUTH
    account.last_seen_at = _utcnow()

    await session.flush()
    await _clear_account_cache(account.id)
    return account


async def link_browser_oauth_to_telegram_account(
    session: AsyncSession,
    *,
    telegram_account_id: uuid.UUID,
    browser_account_id: uuid.UUID,
) -> Account:
    """
    Merge a browser OAuth account into an existing Telegram account.
    """
    account = await merge_accounts(
        session,
        source_account_id=browser_account_id,
        target_account_id=telegram_account_id,
        last_login_source=LoginSource.BROWSER_OAUTH,
    )
    await session.flush()
    return account


async def get_valid_link_token(
    session: AsyncSession,
    link_token: str,
) -> Optional[AuthLinkToken]:
    """Get a non-expired, non-consumed link token."""
    result = await session.execute(
        select(AuthLinkToken).where(
            and_(
                AuthLinkToken.link_token == link_token,
                AuthLinkToken.consumed_at.is_(None),
                AuthLinkToken.expires_at > _utcnow(),
            )
        )
    )
    return result.scalar_one_or_none()
