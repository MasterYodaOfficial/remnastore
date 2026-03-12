from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_access_token, TokenError
from app.db.models import Account, AccountStatus, Admin
from app.db.session import get_session
from app.integrations.supabase import (
    SupabaseAuthClient,
    SupabaseAuthConfigurationError,
    SupabaseAuthError,
    SupabaseAuthInvalidTokenError,
)
from app.services.accounts import (
    AccountIdentityConflictError,
    get_account_by_id,
    upsert_supabase_account,
)
from app.services.admin_auth import get_admin_by_id
from app.services.cache import get_cache


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_account(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> Account:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing credentials")

    token = credentials.credentials
    cache = get_cache()
    try:
        claims = decode_access_token(token, secret=settings.jwt_secret)
    except TokenError:
        claims = None

    if claims is not None:
        account_id = claims.get("sub")
        if not account_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token missing subject",
            )

        account = await get_account_by_id(session, account_id)
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="account not found"
            )

        if account.status == AccountStatus.BLOCKED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="account blocked"
            )

        return account

    cached_account_id = await cache.get_str(cache.auth_token_account_key(token))
    if cached_account_id:
        account = await get_account_by_id(session, cached_account_id)
        if account is not None:
            if account.status == AccountStatus.BLOCKED:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account blocked")
            return account

        await cache.delete(
            cache.auth_token_account_key(token),
            cache.account_response_key(cached_account_id),
        )

    try:
        supabase_user = await SupabaseAuthClient().get_user(token)
    except SupabaseAuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except SupabaseAuthInvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except SupabaseAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    try:
        account = await upsert_supabase_account(session, supabase_user=supabase_user)
    except AccountIdentityConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if account.status == AccountStatus.BLOCKED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account blocked")

    await cache.set_str(
        cache.auth_token_account_key(token),
        str(account.id),
        settings.auth_token_cache_ttl_seconds,
    )

    return account


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> Admin:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing credentials")

    try:
        claims = decode_access_token(credentials.credentials, secret=settings.jwt_secret)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc

    if claims.get("scope") != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")

    admin_id = claims.get("sub")
    if not admin_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token missing subject")

    admin = await get_admin_by_id(session, admin_id)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin not found")
    if not admin.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin disabled")
    return admin
