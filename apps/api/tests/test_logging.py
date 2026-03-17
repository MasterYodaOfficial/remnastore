import logging
import unittest
from unittest.mock import patch

from app.core.logging import configure_logging, resolve_log_level


class LoggingConfigTests(unittest.TestCase):
    def test_resolve_log_level_accepts_lowercase_level_name(self) -> None:
        self.assertEqual(resolve_log_level("info"), "INFO")

    def test_resolve_log_level_accepts_numeric_string(self) -> None:
        self.assertEqual(resolve_log_level("20"), 20)

    def test_resolve_log_level_falls_back_to_info_for_blank_string(self) -> None:
        self.assertEqual(resolve_log_level("  "), logging.INFO)

    def test_configure_logging_normalizes_settings_log_level(self) -> None:
        with (
            patch("app.core.logging.settings.log_level", "info"),
            patch("app.core.logging.logging.basicConfig") as basic_config,
        ):
            configure_logging()

        _, kwargs = basic_config.call_args
        self.assertEqual(kwargs["level"], "INFO")


if __name__ == "__main__":
    unittest.main()
