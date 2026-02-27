import httpx

from bot.core.config import settings


class ApiClient:
    def __init__(self) -> None:
        self._base_url = settings.api_base_url.rstrip("/")

    async def get_me(self) -> dict:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=15.0) as client:
            resp = await client.get("/api/v1/users/me")
            resp.raise_for_status()
            return resp.json()

    async def upsert_telegram_user(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        is_premium: bool,
        locale: str | None,
        last_login_source: str,
        email: str | None = None,
        display_name: str | None = None,
    ) -> dict:
        payload = {
            "telegram_id": telegram_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "is_premium": is_premium,
            "locale": locale,
            "last_login_source": last_login_source,
            "email": email,
            "display_name": display_name,
        }
        async with httpx.AsyncClient(base_url=self._base_url, timeout=10.0) as client:
            resp = await client.post("/api/v1/accounts/telegram", json=payload)
            resp.raise_for_status()
            return resp.json()
