import unittest
from unittest.mock import AsyncMock, patch

from redis.exceptions import RedisError

from app.services.cache import RedisCache


class _FakeRedisClient:
    def __init__(self) -> None:
        self.ping = AsyncMock(return_value=True)
        self.aclose = AsyncMock(return_value=None)
        self.set = AsyncMock(return_value=True)
        self.eval = AsyncMock(return_value=1)
        self.get = AsyncMock(return_value=None)
        self.delete = AsyncMock(return_value=0)


class RedisCacheTests(unittest.IsolatedAsyncioTestCase):
    def test_disabled_cache_does_not_create_client(self) -> None:
        cache = RedisCache("   ")

        self.assertFalse(cache.enabled)
        self.assertIsNone(cache._client_or_none())

    def test_token_based_keys_hash_raw_token(self) -> None:
        cache = RedisCache("redis://localhost/0")

        supabase_key = cache.supabase_user_key("access-token")
        auth_key = cache.auth_token_account_key("access-token")

        self.assertTrue(supabase_key.startswith("cache:supabase-user:"))
        self.assertTrue(auth_key.startswith("cache:auth-token-account:"))
        self.assertNotIn("access-token", supabase_key)
        self.assertNotIn("access-token", auth_key)
        self.assertEqual(
            cache.account_response_key("abc"), "cache:account-response:abc"
        )

    def test_client_or_none_initializes_client_once(self) -> None:
        client = _FakeRedisClient()

        with patch(
            "app.services.cache.Redis.from_url", return_value=client
        ) as from_url:
            cache = RedisCache("redis://localhost/0")

            self.assertIs(cache._client_or_none(), client)
            self.assertIs(cache._client_or_none(), client)

        from_url.assert_called_once_with(
            "redis://localhost/0",
            encoding="utf-8",
            decode_responses=True,
        )

    async def test_ping_returns_false_when_cache_disabled(self) -> None:
        cache = RedisCache("")

        self.assertFalse(await cache.ping())

    async def test_ping_returns_true_for_healthy_client(self) -> None:
        client = _FakeRedisClient()
        cache = RedisCache("redis://localhost/0")
        cache._client = client

        self.assertTrue(await cache.ping())
        client.ping.assert_awaited_once()

    async def test_ping_handles_redis_errors(self) -> None:
        client = _FakeRedisClient()
        client.ping.side_effect = RedisError("boom")
        cache = RedisCache("redis://localhost/0")
        cache._client = client

        with self.assertLogs("app.services.cache", level="ERROR"):
            self.assertFalse(await cache.ping())

    async def test_close_resets_client_even_when_aclose_fails(self) -> None:
        client = _FakeRedisClient()
        client.aclose.side_effect = RedisError("close failed")
        cache = RedisCache("redis://localhost/0")
        cache._client = client

        with self.assertLogs("app.services.cache", level="ERROR"):
            await cache.close()

        self.assertIsNone(cache._client)
        client.aclose.assert_awaited_once()

    async def test_try_acquire_lock_returns_local_lock_when_cache_disabled(
        self,
    ) -> None:
        cache = RedisCache("")

        self.assertEqual(await cache.try_acquire_lock("key", 15), "local-lock")

    async def test_try_acquire_lock_returns_token_on_success(self) -> None:
        client = _FakeRedisClient()
        cache = RedisCache("redis://localhost/0")
        cache._client = client

        lock_token = await cache.try_acquire_lock("key", 15)

        self.assertIsNotNone(lock_token)
        client.set.assert_awaited_once()
        set_args = client.set.await_args
        self.assertEqual(set_args.args[0], "key")
        self.assertEqual(set_args.kwargs["ex"], 15)
        self.assertTrue(set_args.kwargs["nx"])

    async def test_try_acquire_lock_returns_none_when_not_acquired(self) -> None:
        client = _FakeRedisClient()
        client.set.return_value = False
        cache = RedisCache("redis://localhost/0")
        cache._client = client

        self.assertIsNone(await cache.try_acquire_lock("key", 15))

    async def test_try_acquire_lock_handles_redis_errors(self) -> None:
        client = _FakeRedisClient()
        client.set.side_effect = RedisError("lock failed")
        cache = RedisCache("redis://localhost/0")
        cache._client = client

        with self.assertLogs("app.services.cache", level="ERROR"):
            self.assertIsNone(await cache.try_acquire_lock("key", 15))

    async def test_release_lock_skips_local_lock(self) -> None:
        cache = RedisCache("")
        await cache.release_lock("key", "local-lock")

    async def test_release_lock_handles_redis_errors(self) -> None:
        client = _FakeRedisClient()
        client.eval.side_effect = RedisError("release failed")
        cache = RedisCache("redis://localhost/0")
        cache._client = client

        with self.assertLogs("app.services.cache", level="ERROR"):
            await cache.release_lock("key", "token")

        client.eval.assert_awaited_once()

    async def test_get_json_returns_none_when_cache_disabled_or_value_missing(
        self,
    ) -> None:
        cache = RedisCache("")
        self.assertIsNone(await cache.get_json("key"))

        client = _FakeRedisClient()
        cache = RedisCache("redis://localhost/0")
        cache._client = client
        client.get.return_value = None

        self.assertIsNone(await cache.get_json("key"))

    async def test_get_json_handles_redis_errors_and_invalid_json(self) -> None:
        client = _FakeRedisClient()
        cache = RedisCache("redis://localhost/0")
        cache._client = client

        client.get.side_effect = RedisError("get failed")
        with self.assertLogs("app.services.cache", level="ERROR"):
            self.assertIsNone(await cache.get_json("key"))

        client.get.side_effect = None
        client.get.return_value = "not-json"
        with self.assertLogs("app.services.cache", level="WARNING"):
            self.assertIsNone(await cache.get_json("key"))

    async def test_get_json_parses_json_payload(self) -> None:
        client = _FakeRedisClient()
        client.get.return_value = '{"value": 1}'
        cache = RedisCache("redis://localhost/0")
        cache._client = client

        self.assertEqual(await cache.get_json("key"), {"value": 1})

    async def test_set_json_handles_type_errors_and_redis_errors(self) -> None:
        client = _FakeRedisClient()
        cache = RedisCache("redis://localhost/0")
        cache._client = client

        with self.assertLogs("app.services.cache", level="ERROR"):
            await cache.set_json("key", {"bad": object()}, 10)

        client.set.side_effect = RedisError("set failed")
        with self.assertLogs("app.services.cache", level="ERROR"):
            await cache.set_json("key", {"good": 1}, 10)

    async def test_get_str_and_set_str_cover_success_and_errors(self) -> None:
        client = _FakeRedisClient()
        cache = RedisCache("redis://localhost/0")
        cache._client = client

        client.get.return_value = 42
        self.assertEqual(await cache.get_str("key"), "42")

        client.get.return_value = None
        self.assertIsNone(await cache.get_str("key"))

        client.get.side_effect = RedisError("get failed")
        with self.assertLogs("app.services.cache", level="ERROR"):
            self.assertIsNone(await cache.get_str("key"))
        client.get.side_effect = None

        await cache.set_str("key", "value", 5)
        client.set.assert_awaited()

        client.set.side_effect = RedisError("set failed")
        with self.assertLogs("app.services.cache", level="ERROR"):
            await cache.set_str("key", "value", 5)

    async def test_delete_skips_empty_and_handles_errors(self) -> None:
        client = _FakeRedisClient()
        cache = RedisCache("redis://localhost/0")
        cache._client = client

        await cache.delete()
        client.delete.assert_not_awaited()

        await cache.delete("key-1", "key-2")
        client.delete.assert_awaited_once_with("key-1", "key-2")

        client.delete.side_effect = RedisError("delete failed")
        with self.assertLogs("app.services.cache", level="ERROR"):
            await cache.delete("key-3")
