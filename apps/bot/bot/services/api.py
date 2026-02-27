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
