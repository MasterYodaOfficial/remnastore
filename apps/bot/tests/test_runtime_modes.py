import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiogram.types import BotCommandScopeChat

from bot.core.config import Settings
from bot.main import (
    WebhookModeSetupError,
    ensure_webhook,
    get_local_bot_healthcheck_url,
    on_startup,
    run_bot,
)


class SettingsValidationTests(unittest.TestCase):
    def test_normalizes_webhook_path(self) -> None:
        config = Settings(_env_file=None, bot_webhook_path="bot/webhook")
        self.assertEqual(config.bot_webhook_path, "/bot/webhook")

    def test_rejects_invalid_webhook_secret(self) -> None:
        with self.assertRaisesRegex(ValueError, "BOT_WEBHOOK_SECRET"):
            Settings(_env_file=None, bot_webhook_secret="contains spaces")

    def test_requires_https_webhook_base_url_in_webhook_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "https://"):
            Settings(
                _env_file=None,
                bot_use_webhook=True,
                bot_webhook_base_url="http://bot.example.com",
            )

    def test_parses_bot_admin_ids_from_spaces_and_commas(self) -> None:
        config = Settings(_env_file=None, bot_admin_ids="101, 202\n202 303")
        self.assertEqual(config.bot_admin_id_list, (101, 202, 303))


class RuntimeModeTests(unittest.IsolatedAsyncioTestCase):
    def test_local_bot_healthcheck_url_uses_loopback_for_wildcard_host(self) -> None:
        with (
            patch("bot.main.settings.bot_web_server_host", "0.0.0.0"),
            patch("bot.main.settings.bot_web_server_port", 8080),
        ):
            self.assertEqual(
                get_local_bot_healthcheck_url(),
                "http://127.0.0.1:8080/health",
            )

    async def test_ensure_webhook_uses_ip_address_and_allowed_updates(self) -> None:
        bot = AsyncMock()
        dp = Mock()
        dp.resolve_used_update_types.return_value = ["message", "callback_query"]

        with (
            patch("bot.main.settings.bot_webhook_base_url", "https://bot.example.com"),
            patch("bot.main.settings.bot_webhook_path", "/bot/webhook"),
            patch("bot.main.settings.bot_webhook_secret", "valid_secret"),
            patch("bot.main.settings.bot_webhook_ip_address", "203.0.113.10"),
            patch("bot.main.settings.bot_webhook_setup_timeout_seconds", 21),
            patch("bot.main.settings.bot_webhook_setup_max_attempts", 1),
        ):
            await ensure_webhook(bot, dp)

        bot.set_webhook.assert_awaited_once_with(
            "https://bot.example.com/bot/webhook",
            ip_address="203.0.113.10",
            allowed_updates=["message", "callback_query"],
            secret_token="valid_secret",
            request_timeout=21,
        )

    async def test_on_startup_registers_master_command_only_for_admin_chats(
        self,
    ) -> None:
        bot = AsyncMock()
        bot.get_me.return_value = SimpleNamespace(id=999)

        with patch("bot.main.settings.bot_admin_ids", "101, 202"):
            await on_startup(bot)

        self.assertEqual(bot.set_my_commands.await_count, 3)

        default_commands_call = bot.set_my_commands.await_args_list[0]
        self.assertEqual(
            [command.command for command in default_commands_call.args[0]],
            ["start"],
        )
        self.assertEqual(default_commands_call.kwargs, {})

        first_admin_call = bot.set_my_commands.await_args_list[1]
        second_admin_call = bot.set_my_commands.await_args_list[2]

        self.assertEqual(
            [command.command for command in first_admin_call.args[0]],
            ["start", "master"],
        )
        self.assertEqual(
            [command.command for command in second_admin_call.args[0]],
            ["start", "master"],
        )
        self.assertIsInstance(first_admin_call.kwargs["scope"], BotCommandScopeChat)
        self.assertIsInstance(second_admin_call.kwargs["scope"], BotCommandScopeChat)
        self.assertEqual(first_admin_call.kwargs["scope"].chat_id, 101)
        self.assertEqual(second_admin_call.kwargs["scope"].chat_id, 202)

    async def test_on_startup_warns_when_bot_id_is_used_as_admin_id(self) -> None:
        bot = AsyncMock()
        bot.get_me.return_value = SimpleNamespace(id=8519354991)

        with (
            patch("bot.main.settings.bot_admin_ids", "8519354991"),
            patch("bot.main.logger.warning") as logger_warning,
        ):
            await on_startup(bot)

        logger_warning.assert_called_once()

    async def test_run_bot_falls_back_to_polling_when_webhook_setup_fails(self) -> None:
        webhook_runtime = (object(), object())
        polling_runtime = (object(), object())

        with (
            patch("bot.main.settings.bot_use_webhook", True),
            patch("bot.main.settings.bot_webhook_fallback_to_polling", True),
            patch(
                "bot.main.build_runtime",
                side_effect=[webhook_runtime, polling_runtime],
            ) as build_runtime,
            patch(
                "bot.main.run_webhook_mode",
                new=AsyncMock(side_effect=WebhookModeSetupError("boom")),
            ) as run_webhook_mode,
            patch("bot.main.run_polling_mode", new=AsyncMock()) as run_polling_mode,
        ):
            result = await run_bot()

        self.assertEqual(result, "polling")
        self.assertEqual(build_runtime.call_count, 2)
        run_webhook_mode.assert_awaited_once_with(*webhook_runtime)
        run_polling_mode.assert_awaited_once_with(
            *polling_runtime,
            clear_existing_webhook=True,
        )

    async def test_run_bot_raises_when_fallback_disabled(self) -> None:
        webhook_runtime = (object(), object())

        with (
            patch("bot.main.settings.bot_use_webhook", True),
            patch("bot.main.settings.bot_webhook_fallback_to_polling", False),
            patch(
                "bot.main.build_runtime",
                return_value=webhook_runtime,
            ) as build_runtime,
            patch(
                "bot.main.run_webhook_mode",
                new=AsyncMock(side_effect=WebhookModeSetupError("boom")),
            ) as run_webhook_mode,
            patch("bot.main.run_polling_mode", new=AsyncMock()) as run_polling_mode,
        ):
            with self.assertRaises(WebhookModeSetupError):
                await run_bot()

        build_runtime.assert_called_once_with()
        run_webhook_mode.assert_awaited_once_with(*webhook_runtime)
        run_polling_mode.assert_not_called()


if __name__ == "__main__":
    unittest.main()
