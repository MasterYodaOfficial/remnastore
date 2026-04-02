import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot.handlers.start import build_api_headers, start_handler
from bot.states.menu import MenuState


class StartHandlerHeaderTests(unittest.TestCase):
    def test_skips_authorization_header_when_api_token_empty(self) -> None:
        with patch("bot.handlers.start.settings.api_token", ""):
            self.assertEqual(build_api_headers(), {})

    def test_sets_authorization_header_when_api_token_present(self) -> None:
        with patch("bot.handlers.start.settings.api_token", "secret-token"):
            self.assertEqual(
                build_api_headers(),
                {"Authorization": "Bearer secret-token"},
            )


class StartHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_regular_start_forces_new_menu_message(self) -> None:
        message = Mock()
        message.text = "/start"
        message.from_user = SimpleNamespace(id=758107031, language_code="ru")
        state = AsyncMock()

        api_client = AsyncMock()
        api_client.is_telegram_account_fully_blocked.return_value = False

        with (
            patch("bot.handlers.start.ApiClient", return_value=api_client),
            patch(
                "bot.handlers.start.show_menu_for_message", new=AsyncMock()
            ) as show_menu,
        ):
            await start_handler(message, state)

        api_client.mark_telegram_account_reachable.assert_awaited_once_with(
            telegram_id=758107031
        )
        state.set_state.assert_awaited_once_with(MenuState.idle)
        show_menu.assert_awaited_once_with(message, force_new=True)

    async def test_referral_start_forces_new_menu_message_and_preserves_referral_code(
        self,
    ) -> None:
        message = Mock()
        message.text = "/start ref_ref123"
        message.from_user = SimpleNamespace(id=758107031, language_code="ru")
        message.answer = AsyncMock()
        state = AsyncMock()

        api_client = AsyncMock()
        api_client.is_telegram_account_fully_blocked.return_value = False

        referral_response = Mock()
        referral_response.status_code = 200

        http_client = AsyncMock()
        http_client.post.return_value = referral_response

        with (
            patch("bot.handlers.start.ApiClient", return_value=api_client),
            patch(
                "bot.handlers.start.show_menu_for_message", new=AsyncMock()
            ) as show_menu,
            patch("bot.handlers.start.httpx.AsyncClient") as async_client,
        ):
            async_client.return_value.__aenter__.return_value = http_client
            await start_handler(message, state)

        api_client.mark_telegram_account_reachable.assert_awaited_once_with(
            telegram_id=758107031
        )
        state.set_state.assert_awaited_once_with(MenuState.idle)
        show_menu.assert_awaited_once_with(
            message, referral_code="ref123", force_new=True
        )
        message.answer.assert_awaited_once()
        http_client.post.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
