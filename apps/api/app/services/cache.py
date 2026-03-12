import hashlib
import json
import logging
import uuid
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings


logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url.strip()
        self._client: Redis | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._redis_url)

    def _client_or_none(self) -> Redis | None:
        if not self.enabled:
            return None

        if self._client is None:
            self._client = Redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )

        return self._client

    async def ping(self) -> bool:
        client = self._client_or_none()
        if client is None:
            return False

        try:
            await client.ping()
        except RedisError:
            logger.exception("redis ping failed")
            return False

        return True

    async def close(self) -> None:
        client = self._client
        if client is None:
            return

        try:
            await client.aclose()
        except RedisError:
            logger.exception("redis close failed")
        finally:
            self._client = None

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def supabase_user_key(self, access_token: str) -> str:
        return f"cache:supabase-user:{self._token_hash(access_token)}"

    def auth_token_account_key(self, access_token: str) -> str:
        return f"cache:auth-token-account:{self._token_hash(access_token)}"

    def account_response_key(self, account_id: str) -> str:
        return f"cache:account-response:{account_id}"

    def subscription_access_key(self, account_id: str) -> str:
        return f"cache:subscription-access:{account_id}"

    async def try_acquire_lock(self, key: str, ttl_seconds: int) -> str | None:
        client = self._client_or_none()
        if client is None:
            return "local-lock"

        lock_token = uuid.uuid4().hex
        try:
            acquired = await client.set(key, lock_token, ex=max(1, ttl_seconds), nx=True)
        except RedisError:
            logger.exception("redis try_acquire_lock failed for key=%s", key)
            return None

        if not acquired:
            return None

        return lock_token

    async def release_lock(self, key: str, lock_token: str) -> None:
        if lock_token == "local-lock":
            return

        client = self._client_or_none()
        if client is None:
            return

        try:
            await client.eval(
                """
                if redis.call('get', KEYS[1]) == ARGV[1] then
                    return redis.call('del', KEYS[1])
                end
                return 0
                """,
                1,
                key,
                lock_token,
            )
        except RedisError:
            logger.exception("redis release_lock failed for key=%s", key)

    async def get_json(self, key: str) -> dict[str, Any] | list[Any] | None:
        client = self._client_or_none()
        if client is None:
            return None

        try:
            value = await client.get(key)
        except RedisError:
            logger.exception("redis get_json failed for key=%s", key)
            return None

        if not value:
            return None

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning("redis returned invalid json for key=%s", key)
            return None

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        client = self._client_or_none()
        if client is None:
            return

        try:
            await client.set(key, json.dumps(value), ex=ttl_seconds)
        except (RedisError, TypeError):
            logger.exception("redis set_json failed for key=%s", key)

    async def get_str(self, key: str) -> str | None:
        client = self._client_or_none()
        if client is None:
            return None

        try:
            value = await client.get(key)
        except RedisError:
            logger.exception("redis get_str failed for key=%s", key)
            return None

        if value is None:
            return None

        return str(value)

    async def set_str(self, key: str, value: str, ttl_seconds: int) -> None:
        client = self._client_or_none()
        if client is None:
            return

        try:
            await client.set(key, value, ex=ttl_seconds)
        except RedisError:
            logger.exception("redis set_str failed for key=%s", key)

    async def delete(self, *keys: str) -> None:
        if not keys:
            return

        client = self._client_or_none()
        if client is None:
            return

        try:
            await client.delete(*keys)
        except RedisError:
            logger.exception("redis delete failed")


_cache = RedisCache(settings.redis_url)


def get_cache() -> RedisCache:
    return _cache
