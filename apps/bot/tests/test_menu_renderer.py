import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from aiogram.types import InlineKeyboardMarkup

from bot.services.i18n import translate
from bot.services.menu_renderer import (
    ASSET_WELCOME,
    BUTTON_STYLE_DANGER,
    BUTTON_STYLE_SUCCESS,
    SCREEN_HOME,
    SCREEN_PLAN,
    YOOKASSA_IDEMPOTENCY_KEY_MAX_LENGTH,
    RenderedMenu,
    _build_bot_payment_idempotency_key,
    _build_help_keyboard,
    _build_plan_detail_keyboard,
    _top_webapp_row,
    build_rendered_menu,
    create_plan_payment_and_render,
    present_menu,
)
from bot.services.session_store import MenuSession


class PresentMenuTests(unittest.IsolatedAsyncioTestCase):
    async def test_force_new_sends_new_message_and_deactivates_previous_keyboard(
        self,
    ) -> None:
        existing_session = MenuSession(
            telegram_id=758107031,
            chat_id=42,
            menu_message_id=100,
            screen=SCREEN_HOME,
            screen_params={},
            referral_code="ref123",
            asset_name=ASSET_WELCOME,
        )
        rendered = RenderedMenu(
            caption="Menu caption",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
            screen=SCREEN_HOME,
            asset_name=ASSET_WELCOME,
        )

        store = Mock()
        store.get = AsyncMock(return_value=existing_session)
        store.save = AsyncMock()

        registry = Mock()
        registry.get_input_file = AsyncMock(return_value="welcome-file")
        registry.remember_message_media = AsyncMock()

        bot = AsyncMock()
        sent_message = Mock(message_id=200)
        bot.send_photo.return_value = sent_message

        with (
            patch(
                "bot.services.menu_renderer.get_menu_session_store", return_value=store
            ),
            patch(
                "bot.services.menu_renderer.get_media_registry", return_value=registry
            ),
            patch(
                "bot.services.menu_renderer.build_rendered_menu",
                new=AsyncMock(return_value=rendered),
            ),
        ):
            result = await present_menu(
                bot,
                chat_id=42,
                telegram_id=758107031,
                locale="ru",
                force_new=True,
            )

        self.assertIs(result, sent_message)
        bot.send_photo.assert_awaited_once_with(
            chat_id=42,
            photo="welcome-file",
            caption="Menu caption",
            reply_markup=rendered.reply_markup,
        )
        bot.edit_message_reply_markup.assert_awaited_once_with(
            chat_id=42,
            message_id=100,
            reply_markup=None,
        )
        registry.remember_message_media.assert_awaited_once_with(
            ASSET_WELCOME, sent_message
        )

        saved_session = store.save.await_args.args[0]
        self.assertEqual(saved_session.menu_message_id, 200)
        self.assertEqual(saved_session.referral_code, "ref123")

    def test_top_webapp_button_uses_success_style(self) -> None:
        button = _top_webapp_row(locale="ru", referral_code=None)[0]

        self.assertEqual(button.style, BUTTON_STYLE_SUCCESS)
        self.assertEqual(button.text, "Открыть кабинет")

    def test_back_buttons_use_danger_style(self) -> None:
        keyboard = _build_help_keyboard(locale="ru", referral_code=None)
        back_button = keyboard.inline_keyboard[-1][0]

        self.assertEqual(back_button.style, BUTTON_STYLE_DANGER)
        self.assertEqual(
            back_button.text, translate("common.actions.back", locale="ru")
        )

    def test_stars_purchase_button_mentions_telegram_stars(self) -> None:
        keyboard = _build_plan_detail_keyboard(
            locale="ru",
            referral_code=None,
            plan={"code": "plan_1m", "price_stars": 90},
            account_exists=True,
        )
        stars_button = keyboard.inline_keyboard[1][0]

        self.assertEqual(stars_button.text, "Оплатить в Telegram Stars")

    async def test_build_rendered_menu_plan_includes_promo_code_and_actions(
        self,
    ) -> None:
        client = AsyncMock()
        client.get_bot_plans.return_value = {
            "items": [
                {
                    "code": "plan_1m",
                    "name": "1 месяц",
                    "price_rub": 299,
                    "price_stars": 90,
                    "duration_days": 30,
                    "features": ["Безлимит"],
                    "popular": True,
                }
            ]
        }
        client.get_bot_dashboard.return_value = {"exists": True}

        with patch("bot.keyboards.main.settings.webapp_url", "https://example.com/app"):
            rendered = await build_rendered_menu(
                telegram_id=758107031,
                locale="ru",
                screen=SCREEN_PLAN,
                screen_params={"plan_code": "plan_1m", "promo_code": " spring20 "},
                referral_code=None,
                api_client=client,
            )

        self.assertIn("Промокод: SPRING20", rendered.caption)
        self.assertEqual(
            rendered.screen_params,
            {"plan_code": "plan_1m", "promo_code": "SPRING20"},
        )
        self.assertIn("Код сохранен.", rendered.caption)
        buttons = [
            button for row in rendered.reply_markup.inline_keyboard for button in row
        ]
        button_texts = [button.text for button in buttons]
        self.assertIn("Открыть тариф с кодом", button_texts)
        self.assertIn("Открыть в браузере", button_texts)
        self.assertIn("Ввести промокод", button_texts)
        self.assertIn("Убрать код", button_texts)
        browser_button = next(
            button for button in buttons if button.text == "Открыть в браузере"
        )
        self.assertIn("promo=SPRING20", browser_button.url)
        self.assertIn("plan=plan_1m", browser_button.url)

    async def test_yookassa_gateway_failure_returns_short_payment_error(self) -> None:
        request = httpx.Request(
            "POST",
            "http://api:8000/api/v1/internal/bot/payments/yookassa/plans/plan_1m",
        )
        response = httpx.Response(502, json={"detail": "Y" * 1000}, request=request)
        client = AsyncMock()
        client.create_bot_yookassa_payment.side_effect = httpx.HTTPStatusError(
            "upstream failure",
            request=request,
            response=response,
        )

        _, error_text = await create_plan_payment_and_render(
            AsyncMock(),
            chat_id=42,
            telegram_id=758107031,
            locale="ru",
            referral_code=None,
            provider="yookassa",
            plan_code="plan_1m",
            api_client=client,
        )

        self.assertEqual(
            error_text,
            "Не удалось подготовить оплату. Попробуйте позже или откройте кабинет.",
        )

    def test_build_bot_payment_idempotency_key_fits_yookassa_limit(self) -> None:
        key = _build_bot_payment_idempotency_key(
            provider="yookassa",
            telegram_id=758107031,
        )

        self.assertLessEqual(len(key), YOOKASSA_IDEMPOTENCY_KEY_MAX_LENGTH)
        self.assertTrue(key.startswith("bot:yookassa:758107031:"))


if __name__ == "__main__":
    unittest.main()
