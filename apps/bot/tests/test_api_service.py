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
            result = await ApiClient().is_telegram_account_fully_blocked(telegram_id=700004)

        self.assertTrue(result)
        client.get.assert_awaited_once()

    async def test_falls_back_to_not_blocked_when_internal_check_fails(self) -> None:
        client = AsyncMock()
        client.get.side_effect = httpx.HTTPError("boom")

        with patch("bot.services.api.httpx.AsyncClient") as async_client:
            async_client.return_value.__aenter__.return_value = client
            result = await ApiClient().is_telegram_account_fully_blocked(telegram_id=700004)

        self.assertFalse(result)
