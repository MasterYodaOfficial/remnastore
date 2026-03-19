import logging
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.logging import configure_logging, resolve_log_format, resolve_log_level
from common.logging_setup import SensitiveDataFilter, build_logging_config, redact_sensitive_text


class LoggingConfigTests(unittest.TestCase):
    def test_resolve_log_level_accepts_lowercase_level_name(self) -> None:
        self.assertEqual(resolve_log_level("info"), "INFO")

    def test_resolve_log_level_accepts_numeric_string(self) -> None:
        self.assertEqual(resolve_log_level("20"), 20)

    def test_resolve_log_level_falls_back_to_info_for_blank_string(self) -> None:
        self.assertEqual(resolve_log_level("  "), logging.INFO)

    def test_resolve_log_format_accepts_lowercase_json(self) -> None:
        self.assertEqual(resolve_log_format("json"), "json")

    def test_resolve_log_format_falls_back_to_text_for_blank_string(self) -> None:
        self.assertEqual(resolve_log_format(" "), "text")

    def test_redact_sensitive_text_masks_bearer_and_query_tokens(self) -> None:
        value = "Authorization: Bearer abc123 ?token=secret-token&foo=1"
        self.assertEqual(
            redact_sensitive_text(value),
            "Authorization: Bearer [REDACTED] ?token=[REDACTED]&foo=1",
        )

    def test_sensitive_data_filter_masks_sensitive_extra_fields(self) -> None:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="payload token=%s",
            args=("secret-token",),
            exc_info=None,
        )
        record.access_token = "abc"
        record.metadata = {"refresh_token": "def", "safe": "ok"}

        filter_ = SensitiveDataFilter()
        self.assertTrue(filter_.filter(record))
        self.assertEqual(record.access_token, "[REDACTED]")
        self.assertEqual(record.metadata["refresh_token"], "[REDACTED]")
        self.assertEqual(record.metadata["safe"], "ok")
        self.assertEqual(
            redact_sensitive_text(record.getMessage()),
            "payload token=[REDACTED]",
        )

    def test_build_logging_config_adds_file_handlers_when_enabled(self) -> None:
        config = build_logging_config(
            service_name="remnastore-api",
            component_name="api",
            log_level="INFO",
            log_format="json",
            log_to_file=True,
            log_dir="./.tmp-logs-tests",
            log_file_max_bytes=1024,
            log_file_backup_count=2,
        )

        self.assertIn("app_file", config["handlers"])
        self.assertIn("error_file", config["handlers"])
        self.assertEqual(
            Path(config["handlers"]["app_file"]["filename"]).name,
            "api.log",
        )
        self.assertEqual(
            Path(config["handlers"]["error_file"]["filename"]).name,
            "api.error.log",
        )

    def test_configure_logging_passes_normalized_settings(self) -> None:
        with (
            patch("app.core.logging.settings.log_level", "info"),
            patch("app.core.logging.settings.log_format", "json"),
            patch("app.core.logging.settings.log_to_file", False),
            patch("app.core.logging.settings.log_dir", "./.logs"),
            patch("app.core.logging.settings.log_file_max_bytes", 1024),
            patch("app.core.logging.settings.log_file_backup_count", 3),
            patch("common.logging_setup.dictConfig") as configure_dict,
        ):
            configure_logging(component_name="api")

        (config,), _ = configure_dict.call_args
        self.assertEqual(config["root"]["level"], "INFO")
        self.assertEqual(config["handlers"]["stdout"]["formatter"], "json")
        self.assertIn("redact", config["filters"])


if __name__ == "__main__":
    unittest.main()
