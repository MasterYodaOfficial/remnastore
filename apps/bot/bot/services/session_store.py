from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from redis.asyncio import Redis

from bot.core.config import settings


def _build_redis_client() -> Redis | None:
    redis_url = settings.redis_url.strip()
    if not redis_url:
        return None
    return Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)


_redis_client: Redis | None = _build_redis_client()
_memory_sessions: dict[int, str] = {}


@dataclass(slots=True)
class MenuSession:
    telegram_id: int
    chat_id: int
    menu_message_id: int
    screen: str = "home"
    screen_params: dict[str, str] = field(default_factory=dict)
    referral_code: str | None = None
    asset_name: str = "welcome"


class MenuSessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = max(60, int(ttl_seconds))

    @staticmethod
    def _key(telegram_id: int) -> str:
        return f"bot:menu:v1:session:{telegram_id}"

    async def get(self, telegram_id: int) -> MenuSession | None:
        if _redis_client is not None:
            raw_value = await _redis_client.get(self._key(telegram_id))
        else:
            raw_value = _memory_sessions.get(telegram_id)

        if not raw_value:
            return None

        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            return None

        if not isinstance(payload, dict):
            return None

        return MenuSession(
            telegram_id=int(payload["telegram_id"]),
            chat_id=int(payload["chat_id"]),
            menu_message_id=int(payload["menu_message_id"]),
            screen=str(payload.get("screen") or "home"),
            screen_params={
                str(key): str(value)
                for key, value in (payload.get("screen_params") or {}).items()
            },
            referral_code=payload.get("referral_code"),
            asset_name=str(payload.get("asset_name") or "welcome"),
        )

    async def save(self, session: MenuSession) -> None:
        raw_value = json.dumps(asdict(session), ensure_ascii=False)
        if _redis_client is not None:
            await _redis_client.set(
                self._key(session.telegram_id), raw_value, ex=self._ttl_seconds
            )
            return

        _memory_sessions[session.telegram_id] = raw_value

    async def delete(self, telegram_id: int) -> None:
        if _redis_client is not None:
            await _redis_client.delete(self._key(telegram_id))
            return
        _memory_sessions.pop(telegram_id, None)

    async def try_acquire_lock(self, telegram_id: int, *, ttl_seconds: int) -> bool:
        if _redis_client is not None:
            return bool(
                await _redis_client.set(
                    f"bot:menu:v1:lock:{telegram_id}",
                    "1",
                    ex=max(1, ttl_seconds),
                    nx=True,
                )
            )

        key = f"bot:menu:v1:lock:{telegram_id}"
        if key in _memory_sessions:
            return False
        _memory_sessions[key] = "1"
        return True

    async def release_lock(self, telegram_id: int) -> None:
        key = f"bot:menu:v1:lock:{telegram_id}"
        if _redis_client is not None:
            await _redis_client.delete(key)
            return
        _memory_sessions.pop(key, None)


_session_store = MenuSessionStore(ttl_seconds=settings.bot_menu_session_ttl_seconds)


def get_menu_session_store() -> MenuSessionStore:
    return _session_store


async def close_menu_session_store() -> None:
    if _redis_client is not None:
        await _redis_client.aclose()
