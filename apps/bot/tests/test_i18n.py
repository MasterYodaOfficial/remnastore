import unittest

from bot.services.i18n import translate, translate_html


class BotI18nTests(unittest.TestCase):
    def test_returns_russian_translation_by_default(self) -> None:
        self.assertIn("Открыть кабинет", translate("common.actions.open_webapp"))

    def test_falls_back_to_russian_for_unknown_locale(self) -> None:
        self.assertEqual(
            translate("bot.start.welcome", locale="de-DE"),
            translate("bot.start.welcome", locale="ru"),
        )

    def test_formats_named_placeholders(self) -> None:
        text = translate("bot.linking.error_with_detail", detail="Токен истек")

        self.assertIn("Токен истек", text)
        self.assertIn("Не удалось завершить привязку", text)

    def test_translate_html_escapes_params_but_keeps_locale_markup(self) -> None:
        text = translate_html(
            "bot.linking.error_with_detail",
            detail='<b>Токен</b> & "истек"',
        )

        self.assertIn("&lt;b&gt;Токен&lt;/b&gt;", text)
        self.assertIn("&amp; &quot;истек&quot;", text)
        self.assertNotIn("<b>Токен</b>", text)


if __name__ == "__main__":
    unittest.main()
