import unittest

from bot.handlers.menu import _normalize_callback_answer_text
from bot.callbacks.menu import action, nav, parse_menu_callback


class MenuCallbackTests(unittest.TestCase):
    def test_builds_navigation_callback(self) -> None:
        self.assertEqual(nav("home"), "m1:n:home")

    def test_parses_action_callback_with_value(self) -> None:
        parsed = parse_menu_callback(action("plan", "open", "basic"))

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.scope, "plan")
        self.assertEqual(parsed.action, "open")
        self.assertEqual(parsed.value, "basic")

    def test_truncates_callback_answer_text_to_telegram_limit(self) -> None:
        text = _normalize_callback_answer_text("x" * 500, locale="ru")

        self.assertEqual(len(text), 200)
        self.assertTrue(text.endswith("..."))


if __name__ == "__main__":
    unittest.main()
