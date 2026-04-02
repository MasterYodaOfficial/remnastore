import httpx

from bot.core.config import settings


def build_api_headers() -> dict[str, str]:
    token = settings.api_token.strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


class ApiClient:
    def __init__(self) -> None:
        self._base_url = settings.api_url.rstrip("/")

    async def _get(self, path: str, *, authorized: bool = False) -> dict:
        headers = build_api_headers() if authorized else {}
        async with httpx.AsyncClient(base_url=self._base_url, timeout=15.0) as client:
            resp = await client.get(path, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def _post(
        self, path: str, payload: dict, *, authorized: bool = False
    ) -> dict:
        headers = build_api_headers() if authorized else {}
        async with httpx.AsyncClient(base_url=self._base_url, timeout=15.0) as client:
            resp = await client.post(path, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def get_me(self) -> dict:
        return await self._get("/api/v1/users/me")

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

    async def is_telegram_account_fully_blocked(self, *, telegram_id: int) -> bool:
        try:
            payload = await self._get(
                f"/api/v1/internal/telegram-accounts/{telegram_id}/access",
                authorized=True,
            )
        except httpx.HTTPError:
            return False
        return bool(payload.get("fully_blocked"))

    async def mark_telegram_account_reachable(self, *, telegram_id: int) -> bool:
        try:
            await self._post(
                f"/api/v1/internal/telegram-accounts/{telegram_id}/reachable",
                {},
                authorized=True,
            )
        except httpx.HTTPError:
            return False
        return True

    async def get_bot_dashboard(self, *, telegram_id: int) -> dict:
        return await self._get(
            f"/api/v1/internal/bot/dashboard/{telegram_id}", authorized=True
        )

    async def get_bot_plans(self) -> dict:
        return await self._get("/api/v1/internal/bot/plans", authorized=True)

    async def activate_bot_trial(self, *, telegram_id: int) -> dict:
        return await self._post(
            f"/api/v1/internal/bot/subscriptions/trial/{telegram_id}",
            {},
            authorized=True,
        )

    async def create_bot_telegram_stars_payment(
        self,
        *,
        telegram_id: int,
        plan_code: str,
        idempotency_key: str | None = None,
    ) -> dict:
        return await self._post(
            f"/api/v1/internal/bot/payments/telegram-stars/plans/{plan_code}",
            {"telegram_id": telegram_id, "idempotency_key": idempotency_key},
            authorized=True,
        )

    async def create_bot_yookassa_payment(
        self,
        *,
        telegram_id: int,
        plan_code: str,
        idempotency_key: str | None = None,
    ) -> dict:
        return await self._post(
            f"/api/v1/internal/bot/payments/yookassa/plans/{plan_code}",
            {"telegram_id": telegram_id, "idempotency_key": idempotency_key},
            authorized=True,
        )
