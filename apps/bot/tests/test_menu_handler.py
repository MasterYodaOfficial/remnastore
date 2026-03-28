import unittest

from bot.handlers.menu import _normalize_callback_answer_text


class MenuHandlerTests(unittest.TestCase):
    def test_normalize_callback_answer_text_strips_html_markup(self) -> None:
        self.assertEqual(
            _normalize_callback_answer_text(
                "✅ <b>Ссылка на оплату готова</b>", locale="ru"
            ),
            "✅ Ссылка на оплату готова",
        )


if __name__ == "__main__":
    unittest.main()
