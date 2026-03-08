import httpx

from app.core.config import settings
from app.integrations.supabase.models import SupabaseUser
from app.services.cache import get_cache


class SupabaseAuthError(Exception):
    pass


class SupabaseAuthConfigurationError(SupabaseAuthError):
    pass


class SupabaseAuthInvalidTokenError(SupabaseAuthError):
    pass


class SupabaseAuthClient:
    def __init__(self) -> None:
        self._base_url = settings.supabase_url.rstrip("/")
        self._anon_key = settings.supabase_anon_key

        if not self._base_url or not self._anon_key:
            raise SupabaseAuthConfigurationError("supabase auth is not configured")

    async def get_user(self, access_token: str) -> SupabaseUser:
        cache = get_cache()
        cached_user = await cache.get_json(cache.supabase_user_key(access_token))
        if isinstance(cached_user, dict):
            try:
                return SupabaseUser.model_validate(cached_user)
            except Exception:
                await cache.delete(cache.supabase_user_key(access_token))

        headers = {
            "apikey": self._anon_key,
            "Authorization": f"Bearer {access_token}",
        }

        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=10.0) as client:
                response = await client.get("/auth/v1/user", headers=headers)
        except httpx.HTTPError as exc:
            raise SupabaseAuthError("failed to reach supabase auth") from exc

        if response.status_code == 200:
            user = SupabaseUser.model_validate(response.json())
            await cache.set_json(
                cache.supabase_user_key(access_token),
                user.model_dump(mode="json"),
                settings.supabase_user_cache_ttl_seconds,
            )
            return user

        if response.status_code in {401, 403}:
            await cache.delete(cache.supabase_user_key(access_token))
            raise SupabaseAuthInvalidTokenError("invalid access token")

        response.raise_for_status()
        raise SupabaseAuthError("unexpected supabase auth response")
