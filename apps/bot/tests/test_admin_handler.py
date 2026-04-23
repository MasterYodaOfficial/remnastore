import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot.handlers.admin import (
    admin_broadcast_draft_handler,
    admin_callback_handler,
    master_handler,
)
from bot.states.admin import AdminState


class AdminHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_master_handler_opens_menu_for_admin_only(self) -> None:
        message = Mock()
        message.from_user = SimpleNamespace(id=101, language_code="ru")
        message.answer = AsyncMock()
        state = AsyncMock()

        with patch("bot.handlers.admin.settings.bot_admin_ids", "101"):
            await master_handler(message, state)

        state.clear.assert_awaited_once()
        message.answer.assert_awaited_once()
        self.assertIn("Админ-меню", message.answer.await_args.args[0])
        self.assertIsNotNone(message.answer.await_args.kwargs["reply_markup"])

    async def test_master_handler_ignores_non_admin_user(self) -> None:
        message = Mock()
        message.from_user = SimpleNamespace(id=101, language_code="ru")
        message.answer = AsyncMock()
        state = AsyncMock()

        with patch("bot.handlers.admin.settings.bot_admin_ids", "202"):
            await master_handler(message, state)

        state.clear.assert_not_awaited()
        message.answer.assert_not_awaited()

    async def test_broadcast_callback_puts_admin_into_draft_state(self) -> None:
        callback = Mock()
        callback.data = "admin:broadcast"
        callback.from_user = SimpleNamespace(id=101, language_code="ru")
        callback.message = Mock()
        callback.message.edit_text = AsyncMock()
        callback.answer = AsyncMock()
        state = AsyncMock()

        with patch("bot.handlers.admin.settings.bot_admin_ids", "101"):
            await admin_callback_handler(callback, state)

        state.set_state.assert_awaited_once_with(AdminState.awaiting_broadcast_message)
        callback.message.edit_text.assert_awaited_once()
        callback.answer.assert_awaited_once()

    async def test_broadcast_draft_handler_saves_source_message_metadata(self) -> None:
        message = Mock()
        message.from_user = SimpleNamespace(id=101, language_code="ru")
        message.chat = SimpleNamespace(id=9001)
        message.message_id = 77
        message.text = "Тестовый пост для админки"
        message.caption = None
        message.photo = None
        message.video = None
        message.animation = None
        message.document = None
        message.audio = None
        message.voice = None
        message.video_note = None
        message.sticker = None
        message.media_group_id = None
        message.answer = AsyncMock()
        state = AsyncMock()

        with patch("bot.handlers.admin.settings.bot_admin_ids", "101"):
            await admin_broadcast_draft_handler(message, state)

        state.update_data.assert_awaited_once()
        draft_payload = state.update_data.await_args.kwargs["admin_broadcast_draft"]
        self.assertEqual(
            draft_payload,
            {
                "source_chat_id": 9001,
                "source_message_ids": [77],
                "content_type": "text",
                "media_group_id": None,
                "preview": "Тестовый пост для админки",
                "caption": False,
                "api_payload": {
                    "source_chat_id": 9001,
                    "source_message_ids": [77],
                    "media_group_id": None,
                },
                "unsupported_reason": None,
            },
        )
        state.set_state.assert_awaited_once_with(AdminState.broadcast_draft_ready)
        message.answer.assert_awaited_once()
        self.assertIn("Черновик сохранён", message.answer.await_args.args[0])
        self.assertIsNotNone(message.answer.await_args.kwargs["reply_markup"])

    async def test_broadcast_test_callback_calls_internal_api(self) -> None:
        callback = Mock()
        callback.data = "admin:broadcast_test"
        callback.from_user = SimpleNamespace(id=101, language_code="ru")
        callback.message = Mock()
        callback.message.answer = AsyncMock()
        callback.answer = AsyncMock()
        state = AsyncMock()
        state.get_data.return_value = {
            "admin_broadcast_draft": {
                "api_payload": {
                    "source_chat_id": 9001,
                    "source_message_ids": [77],
                    "media_group_id": None,
                }
            }
        }
        api_client = AsyncMock()
        api_client.test_bot_admin_broadcast.return_value = {
            "content_type": "telegram_copy",
            "telegram_message_ids": ["msg-1"],
        }

        with (
            patch("bot.handlers.admin.settings.bot_admin_ids", "101"),
            patch("bot.handlers.admin.ApiClient", return_value=api_client),
        ):
            await admin_callback_handler(callback, state)

        api_client.test_bot_admin_broadcast.assert_awaited_once_with(
            admin_telegram_id=101,
            source_chat_id=9001,
            source_message_ids=[77],
            media_group_id=None,
        )
        callback.message.answer.assert_awaited_once()
        callback.answer.assert_awaited_once()

    async def test_media_group_messages_accumulate_ids_in_same_draft(self) -> None:
        message = Mock()
        message.from_user = SimpleNamespace(id=101, language_code="ru")
        message.chat = SimpleNamespace(id=9001)
        message.message_id = 78
        message.text = None
        message.caption = "Альбом"
        message.photo = [Mock()]
        message.video = None
        message.animation = None
        message.document = None
        message.audio = None
        message.voice = None
        message.video_note = None
        message.sticker = None
        message.poll = None
        message.contact = None
        message.location = None
        message.venue = None
        message.media_group_id = "album-1"
        message.answer = AsyncMock()
        state = AsyncMock()
        state.get_data.return_value = {
            "admin_broadcast_draft": {
                "source_chat_id": 9001,
                "source_message_ids": [77],
                "media_group_id": "album-1",
            }
        }

        with patch("bot.handlers.admin.settings.bot_admin_ids", "101"):
            await admin_broadcast_draft_handler(message, state)

        draft_payload = state.update_data.await_args.kwargs["admin_broadcast_draft"]
        self.assertEqual(draft_payload["source_message_ids"], [77, 78])
        self.assertEqual(
            draft_payload["api_payload"]["source_message_ids"],
            [77, 78],
        )

    async def test_status_callback_renders_items_from_internal_api(self) -> None:
        callback = Mock()
        callback.data = "admin:status"
        callback.from_user = SimpleNamespace(id=101, language_code="ru")
        callback.message = Mock()
        callback.message.edit_text = AsyncMock()
        callback.answer = AsyncMock()
        state = AsyncMock()
        api_client = AsyncMock()
        api_client.get_bot_admin_broadcast_statuses.return_value = {
            "items": [
                {
                    "broadcast_id": 12,
                    "content_type": "text",
                    "status": "running",
                    "latest_run_status": "running",
                    "estimated_telegram_recipients": 25,
                    "pending_deliveries": 25,
                    "delivered_deliveries": 0,
                    "failed_deliveries": 0,
                    "skipped_deliveries": 0,
                }
            ]
        }

        with (
            patch("bot.handlers.admin.settings.bot_admin_ids", "101"),
            patch("bot.handlers.admin.ApiClient", return_value=api_client),
        ):
            await admin_callback_handler(callback, state)

        state.clear.assert_awaited_once()
        api_client.get_bot_admin_broadcast_statuses.assert_awaited_once_with(
            admin_telegram_id=101
        )
        callback.message.edit_text.assert_awaited_once()
        self.assertIn("#12", callback.message.edit_text.await_args.args[0])
        callback.answer.assert_awaited_once()

    async def test_stats_callback_renders_summary_from_internal_api(self) -> None:
        callback = Mock()
        callback.data = "admin:stats"
        callback.from_user = SimpleNamespace(id=101, language_code="ru")
        callback.message = Mock()
        callback.message.edit_text = AsyncMock()
        callback.answer = AsyncMock()
        state = AsyncMock()
        api_client = AsyncMock()
        api_client.get_bot_admin_stats_summary.return_value = {
            "total_accounts": 120,
            "active_subscriptions": 55,
            "accounts_with_telegram": 110,
            "paying_accounts_last_30d": 38,
            "blocked_accounts": 3,
            "new_accounts_last_7d": 14,
            "pending_payments": 4,
            "pending_withdrawals": 2,
            "successful_payments_amount_rub_last_30d": 45000,
            "successful_payments_rub_last_30d": 40,
            "direct_plan_revenue_rub_last_30d": 32000,
            "direct_plan_purchases_rub_last_30d": 29,
            "direct_plan_revenue_stars_last_30d": 1500,
            "direct_plan_purchases_stars_last_30d": 9,
            "total_wallet_balance": 12000,
            "total_referral_earnings": 3500,
        }

        with (
            patch("bot.handlers.admin.settings.bot_admin_ids", "101"),
            patch("bot.handlers.admin.ApiClient", return_value=api_client),
        ):
            await admin_callback_handler(callback, state)

        state.clear.assert_awaited_once()
        api_client.get_bot_admin_stats_summary.assert_awaited_once_with(
            admin_telegram_id=101
        )
        callback.message.edit_text.assert_awaited_once()
        rendered_text = callback.message.edit_text.await_args.args[0]
        self.assertIn("Статистика бота", rendered_text)
        self.assertIn("120", rendered_text)
        self.assertIn("45000", rendered_text)
        callback.answer.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
