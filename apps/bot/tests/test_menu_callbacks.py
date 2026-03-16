import unittest

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


if __name__ == "__main__":
    unittest.main()
