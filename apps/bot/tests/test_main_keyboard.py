import unittest
from unittest.mock import patch

from bot.keyboards.main import build_webapp_url


class WebAppUrlTests(unittest.TestCase):
    def test_builds_webapp_url_with_route_and_referral(self) -> None:
        with patch(
            "bot.keyboards.main.settings.webapp_url", "https://example.com/app?foo=bar"
        ):
            self.assertEqual(
                build_webapp_url("ref123", route_path="/plans"),
                "https://example.com/app/plans?foo=bar&ref=ref123",
            )

    def test_returns_base_url_when_route_and_referral_missing(self) -> None:
        with patch("bot.keyboards.main.settings.webapp_url", "https://example.com/app"):
            self.assertEqual(build_webapp_url(), "https://example.com/app")


if __name__ == "__main__":
    unittest.main()
