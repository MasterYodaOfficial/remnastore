import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from bot.services.api import ApiClient


class ApiClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_reports_full_block_for_blocked_telegram_account(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"fully_blocked": True}

        client = AsyncMock()
        client.get.return_value = response

        with patch("bot.services.api.httpx.AsyncClient") as async_client:
            async_client.return_value.__aenter__.return_value = client
            result = await ApiClient().is_telegram_account_fully_blocked(
                telegram_id=700004
            )

        self.assertTrue(result)
        client.get.assert_awaited_once()

    async def test_falls_back_to_not_blocked_when_internal_check_fails(self) -> None:
        client = AsyncMock()
        client.get.side_effect = httpx.HTTPError("boom")

        with patch("bot.services.api.httpx.AsyncClient") as async_client:
            async_client.return_value.__aenter__.return_value = client
            result = await ApiClient().is_telegram_account_fully_blocked(
                telegram_id=700004
            )

        self.assertFalse(result)

    async def test_marks_telegram_account_reachable_via_internal_endpoint(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None

        client = AsyncMock()
        client.post.return_value = response

        with patch("bot.services.api.httpx.AsyncClient") as async_client:
            async_client.return_value.__aenter__.return_value = client
            result = await ApiClient().mark_telegram_account_reachable(
                telegram_id=700004
            )

        self.assertTrue(result)
        client.post.assert_awaited_once()

    async def test_mark_telegram_account_reachable_returns_false_on_http_error(
        self,
    ) -> None:
        client = AsyncMock()
        client.post.side_effect = httpx.HTTPError("boom")

        with patch("bot.services.api.httpx.AsyncClient") as async_client:
            async_client.return_value.__aenter__.return_value = client
            result = await ApiClient().mark_telegram_account_reachable(
                telegram_id=700004
            )

        self.assertFalse(result)

    async def test_get_bot_dashboard_uses_internal_authorization(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"telegram_id": 700004, "exists": True}

        client = AsyncMock()
        client.get.return_value = response

        with patch("bot.services.api.httpx.AsyncClient") as async_client:
            async_client.return_value.__aenter__.return_value = client
            payload = await ApiClient().get_bot_dashboard(telegram_id=700004)

        self.assertEqual(payload["telegram_id"], 700004)
        client.get.assert_awaited_once()

    async def test_create_bot_yookassa_payment_sends_idempotency_key(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"provider": "yookassa"}

        client = AsyncMock()
        client.post.return_value = response

        with patch("bot.services.api.httpx.AsyncClient") as async_client:
            async_client.return_value.__aenter__.return_value = client
            payload = await ApiClient().create_bot_yookassa_payment(
                telegram_id=700004,
                plan_code="basic",
                idempotency_key="idem-123",
            )

        self.assertEqual(payload["provider"], "yookassa")
        client.post.assert_awaited_once()
        _, kwargs = client.post.await_args
        self.assertEqual(
            kwargs["json"],
            {"telegram_id": 700004, "idempotency_key": "idem-123"},
        )
