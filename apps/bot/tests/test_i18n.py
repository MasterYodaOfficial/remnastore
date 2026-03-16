import unittest

from bot.services.i18n import translate


class BotI18nTests(unittest.TestCase):
    def test_returns_russian_translation_by_default(self) -> None:
        self.assertEqual(translate("common.actions.open_webapp"), "Открыть личный кабинет")

    def test_falls_back_to_russian_for_unknown_locale(self) -> None:
        self.assertEqual(
            translate("bot.start.welcome", locale="de-DE"),
            "Добро пожаловать! Откройте витрину через кнопку ниже.",
        )

    def test_formats_named_placeholders(self) -> None:
        self.assertEqual(
            translate("bot.linking.error_with_detail", detail="Токен истек"),
            "❌ Ошибка: Токен истек\n\nПроверьте ссылку или создайте новую.",
        )


if __name__ == "__main__":
    unittest.main()
