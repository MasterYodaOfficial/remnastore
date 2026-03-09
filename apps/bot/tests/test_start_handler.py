import unittest
from unittest.mock import patch

from bot.handlers.start import build_api_headers


class StartHandlerHeaderTests(unittest.TestCase):
    def test_skips_authorization_header_when_api_token_empty(self) -> None:
        with patch("bot.handlers.start.settings.api_token", ""):
            self.assertEqual(build_api_headers(), {})

    def test_sets_authorization_header_when_api_token_present(self) -> None:
        with patch("bot.handlers.start.settings.api_token", "secret-token"):
            self.assertEqual(
                build_api_headers(),
                {"Authorization": "Bearer secret-token"},
            )


if __name__ == "__main__":
    unittest.main()
