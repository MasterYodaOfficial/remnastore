import unittest

from bot.services.i18n import translate


class BotI18nTests(unittest.TestCase):
    def test_returns_russian_translation_by_default(self) -> None:
        self.assertEqual(translate("common.actions.open_webapp"), "Открыть кабинет")

    def test_falls_back_to_russian_for_unknown_locale(self) -> None:
        self.assertEqual(
            translate("bot.start.welcome", locale="de-DE"),
            "Добро пожаловать в RemnaStore. Бот помогает быстро открыть кабинет, проверить доступ и перейти к оплате без лишних шагов.",
        )

    def test_formats_named_placeholders(self) -> None:
        self.assertEqual(
            translate("bot.linking.error_with_detail", detail="Токен истек"),
            "Не удалось завершить привязку.\n\nТокен истек\n\nПроверьте ссылку и попробуйте снова. Если она уже открывалась раньше, запросите новую.",
        )


if __name__ == "__main__":
    unittest.main()
