from datetime import UTC, datetime
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Account, AccountStatus, AuthAccount, AuthProvider, LoginSource
from app.integrations.supabase.models import SupabaseIdentity, SupabaseUser
from app.services.cache import get_cache
from app.services.i18n import translate


class AccountIdentityConflictError(Exception):
    pass


class AccountBlockedError(Exception):
    code = "account_blocked"


BASE_SUPABASE_IDENTITY_PROVIDERS = {
    "google": AuthProvider.GOOGLE,
    "yandex": AuthProvider.YANDEX,
}


def _map_supabase_identity_provider(provider_name: str | None) -> AuthProvider | None:
    if not provider_name:
        return None
    return BASE_SUPABASE_IDENTITY_PROVIDERS.get(provider_name.strip().lower())


def _ensure_referral_code(account: Account) -> None:
    if account.referral_code is None:
        account.referral_code = f"ref-{uuid.uuid4().hex[:8]}"


async def get_account_by_id(session: AsyncSession, account_id) -> Account | None:
    try:
        account_uuid = uuid.UUID(str(account_id))
    except (TypeError, ValueError):
        return None
    result = await session.execute(select(Account).where(Account.id == account_uuid))
    return result.scalar_one_or_none()


async def get_account_by_telegram_id(
    session: AsyncSession, *, telegram_id: int
) -> Account | None:
    result = await session.execute(
        select(Account).where(Account.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def mark_telegram_bot_blocked(
    session: AsyncSession,
    *,
    account: Account,
    blocked_at: datetime | None = None,
) -> None:
    if account.telegram_bot_blocked_at is not None:
        return

    account.telegram_bot_blocked_at = blocked_at or datetime.now(UTC)
    await session.flush()
    await get_cache().delete(get_cache().account_response_key(str(account.id)))


async def mark_telegram_account_reachable(
    session: AsyncSession,
    *,
    telegram_id: int,
) -> Account | None:
    account = await get_account_by_telegram_id(session, telegram_id=telegram_id)
    if account is None:
        return None

    account.telegram_bot_blocked_at = None
    account.last_seen_at = datetime.now(UTC)
    await session.flush()
    await get_cache().delete(get_cache().account_response_key(str(account.id)))
    return account


async def _get_auth_account(
    session: AsyncSession,
    *,
    provider: AuthProvider,
    provider_uid: str,
) -> AuthAccount | None:
    result = await session.execute(
        select(AuthAccount)
        .options(selectinload(AuthAccount.account))
        .where(
            AuthAccount.provider == provider,
            AuthAccount.provider_uid == provider_uid,
        )
    )
    return result.scalar_one_or_none()


def _build_supabase_identity_links(
    supabase_user: SupabaseUser,
) -> list[tuple[AuthProvider, str]]:
    links: list[tuple[AuthProvider, str]] = [(AuthProvider.SUPABASE, supabase_user.id)]
    seen = {(AuthProvider.SUPABASE, supabase_user.id)}

    for identity in supabase_user.identities:
        provider = _map_supabase_identity_provider(identity.provider)
        provider_uid = identity.provider_uid
        if provider is None or not provider_uid:
            continue

        key = (provider, provider_uid)
        if key in seen:
            continue

        seen.add(key)
        links.append(key)

    return links


def _find_matching_supabase_identity(
    supabase_user: SupabaseUser,
    *,
    provider: AuthProvider,
    provider_uid: str,
) -> SupabaseIdentity | None:
    for identity in supabase_user.identities:
        if _map_supabase_identity_provider(identity.provider) != provider:
            continue
        if identity.provider_uid != provider_uid:
            continue
        return identity

    return None


def _identity_display_name(
    supabase_user: SupabaseUser,
    identity: SupabaseIdentity | None = None,
) -> str | None:
    if supabase_user.display_name:
        return supabase_user.display_name

    if identity is None:
        return None

    for key in ("full_name", "name", "display_name"):
        value = identity.identity_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


async def upsert_supabase_account(
    session: AsyncSession,
    *,
    supabase_user: SupabaseUser,
) -> Account:
    for attempt in range(2):
        try:
            return await _upsert_supabase_account_once(
                session,
                supabase_user=supabase_user,
            )
        except IntegrityError as exc:
            await session.rollback()
            if "uq_auth_provider_uid" not in str(exc):
                raise

            if attempt == 1:
                raise AccountIdentityConflictError(
                    "supabase identity link could not be persisted consistently"
                ) from exc

    raise AssertionError("unreachable")


async def _upsert_supabase_account_once(
    session: AsyncSession,
    *,
    supabase_user: SupabaseUser,
) -> Account:
    now = datetime.utcnow()
    identity_links = _build_supabase_identity_links(supabase_user)

    resolved_account: Account | None = None
    existing_links: dict[tuple[AuthProvider, str], AuthAccount] = {}

    # ЭТАП 1: Поиск по провайдерам (существующая логика)
    for provider, provider_uid in identity_links:
        auth_account = await _get_auth_account(
            session, provider=provider, provider_uid=provider_uid
        )
        if auth_account is None:
            continue

        existing_links[(provider, provider_uid)] = auth_account
        if resolved_account is None:
            resolved_account = auth_account.account
            continue

        if resolved_account.id != auth_account.account_id:
            raise AccountIdentityConflictError(
                "supabase identities point to different local accounts"
            )

    # ЭТАП 2: Поиск по email (НОВОЕ)
    if (
        resolved_account is None
        and supabase_user.email
        and supabase_user.email_confirmed_at
    ):
        result = await session.execute(
            select(Account).where(Account.email == supabase_user.email)
        )
        email_account = result.scalar_one_or_none()
        if email_account is not None:
            resolved_account = email_account

    display_name = _identity_display_name(supabase_user)
    locale = supabase_user.locale

    # ЭТАП 3: Создание нового аккаунта
    if resolved_account is None:
        resolved_account = Account(
            email=supabase_user.email,
            display_name=display_name,
            locale=locale,
            status=AccountStatus.ACTIVE,
            last_login_source=LoginSource.BROWSER_OAUTH,
            last_seen_at=now,
        )
        _ensure_referral_code(resolved_account)
        session.add(resolved_account)
        await session.flush()
    else:
        resolved_account.email = supabase_user.email or resolved_account.email
        resolved_account.display_name = display_name or resolved_account.display_name
        resolved_account.locale = locale or resolved_account.locale
        resolved_account.last_login_source = LoginSource.BROWSER_OAUTH
        resolved_account.last_seen_at = now
        _ensure_referral_code(resolved_account)

    for provider, provider_uid in identity_links:
        auth_account = existing_links.get((provider, provider_uid))
        identity = (
            None
            if provider == AuthProvider.SUPABASE
            else _find_matching_supabase_identity(
                supabase_user,
                provider=provider,
                provider_uid=provider_uid,
            )
        )
        link_display_name = _identity_display_name(supabase_user, identity)

        if auth_account is None:
            session.add(
                AuthAccount(
                    account_id=resolved_account.id,
                    provider=provider,
                    provider_uid=provider_uid,
                    email=supabase_user.email,
                    display_name=link_display_name,
                )
            )
            continue

        auth_account.email = supabase_user.email or auth_account.email
        auth_account.display_name = link_display_name or auth_account.display_name

    await session.commit()
    await session.refresh(resolved_account)
    await get_cache().delete(get_cache().account_response_key(str(resolved_account.id)))
    return resolved_account


async def upsert_telegram_account(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
    is_premium: bool,
    locale: Optional[str],
    email: Optional[str],
    display_name: Optional[str],
    last_login_source: LoginSource,
) -> Account:
    result = await session.execute(
        select(Account).where(Account.telegram_id == telegram_id)
    )
    account = result.scalar_one_or_none()

    now = datetime.utcnow()

    if account is None:
        account = Account(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            is_premium=is_premium,
            locale=locale,
            email=email,
            display_name=display_name,
            status=AccountStatus.ACTIVE,
            last_login_source=last_login_source,
            last_seen_at=now,
        )
        session.add(account)
    else:
        if account.status == AccountStatus.BLOCKED:
            raise AccountBlockedError(translate("api.accounts.errors.account_blocked"))
        account.username = username or account.username
        account.first_name = first_name or account.first_name
        account.last_name = last_name or account.last_name
        account.is_premium = is_premium or account.is_premium
        account.locale = locale or account.locale
        account.email = email or account.email
        account.display_name = display_name or account.display_name
        account.last_login_source = last_login_source
        account.last_seen_at = now
        account.telegram_bot_blocked_at = None

    _ensure_referral_code(account)

    await session.commit()
    await session.refresh(account)
    await get_cache().delete(get_cache().account_response_key(str(account.id)))
    return account
