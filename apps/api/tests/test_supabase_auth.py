import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.core.config import settings
from app.integrations.supabase.client import (
    SupabaseAuthClient,
    SupabaseAuthConfigurationError,
    SupabaseAuthInvalidTokenError,
)


class _DummyCache:
    async def get_json(self, key: str):
        del key
        return None

    async def set_json(self, key: str, value, ttl_seconds: int) -> None:
        del key, value, ttl_seconds

    async def delete(self, *keys: str) -> None:
        del keys

    def supabase_user_key(self, access_token: str) -> str:
        return f"supabase:{access_token}"


class _FakeAsyncClient:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        return None

    async def get(self, path: str, headers: dict[str, str]) -> httpx.Response:
        del path, headers
        return self._response


class SupabaseAuthClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._original_supabase_url = settings.supabase_url
        self._original_supabase_anon_key = settings.supabase_anon_key
        settings.supabase_url = "https://example.supabase.co"
        settings.supabase_anon_key = "test-anon-key"

    def tearDown(self) -> None:
        settings.supabase_url = self._original_supabase_url
        settings.supabase_anon_key = self._original_supabase_anon_key

    async def test_invalid_api_key_response_is_reported_as_configuration_error(
        self,
    ) -> None:
        response = httpx.Response(
            401,
            json={
                "message": "Invalid API key",
                "hint": "Double check your API key.",
            },
        )

        with (
            patch(
                "app.integrations.supabase.client.get_cache", return_value=_DummyCache()
            ),
            patch(
                "app.integrations.supabase.client.httpx.AsyncClient",
                return_value=_FakeAsyncClient(response),
            ),
        ):
            with self.assertRaises(SupabaseAuthConfigurationError):
                await SupabaseAuthClient().get_user("access-token")

    async def test_regular_unauthorized_response_still_maps_to_invalid_token(
        self,
    ) -> None:
        response = httpx.Response(
            401,
            json={
                "message": "invalid JWT",
            },
        )

        cache = _DummyCache()
        cache.delete = AsyncMock()

        with (
            patch("app.integrations.supabase.client.get_cache", return_value=cache),
            patch(
                "app.integrations.supabase.client.httpx.AsyncClient",
                return_value=_FakeAsyncClient(response),
            ),
        ):
            with self.assertRaises(SupabaseAuthInvalidTokenError):
                await SupabaseAuthClient().get_user("access-token")

        cache.delete.assert_awaited_once_with("supabase:access-token")
