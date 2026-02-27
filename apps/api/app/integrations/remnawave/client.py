from typing import Any

import httpx

from app.core.config import settings


class RemnawaveClient:
    def __init__(self) -> None:
        self._base_url = settings.remnawave_api_url.rstrip("/")
        self._token = settings.remnawave_api_token

    async def _request(self, method: str, path: str, json: dict | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(base_url=self._base_url, headers=headers, timeout=20.0) as client:
            resp = await client.request(method, path, json=json)
            resp.raise_for_status()
            return resp.json()

    async def list_nodes(self) -> Any:
        return await self._request("GET", "/nodes")
