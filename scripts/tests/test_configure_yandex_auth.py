import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import configure_yandex_auth as tool


class ConfigureYandexAuthTests(unittest.TestCase):
    def run_configuration(self, *, existing=None, enable=False, failure=None):
        with tempfile.TemporaryDirectory() as directory:
            credentials = Path(directory) / "credentials.json"
            credentials.write_text(
                json.dumps(
                    {"client_id": "test-client", "client_secret": "test-secret"}
                ),
                encoding="utf-8",
            )
            argv = [
                "configure_yandex_auth.py",
                "--auth-container",
                "test-auth",
                "--credentials-file",
                str(credentials),
                "--userinfo-url",
                "https://api.example.test/api/v1/auth/yandex/userinfo",
            ]
            if enable:
                argv.append("--enable")
            lookup = (
                io.BytesIO(json.dumps(existing).encode())
                if existing
                else HTTPError("http://localhost", 404, "Not found", {}, None)
            )
            update = failure or io.BytesIO(json.dumps({"enabled": enable}).encode())
            container = [{"Config": {"Env": ["GOTRUE_JWT_SECRET=test-signing-secret"]}}]
            output = io.StringIO()
            with (
                patch("sys.argv", argv),
                patch.object(
                    tool.subprocess,
                    "check_output",
                    return_value=json.dumps(container).encode(),
                ),
                patch.object(tool, "urlopen", side_effect=[lookup, update]) as request,
                redirect_stdout(output),
            ):
                tool.main()
            return request.call_args_list[-1].args[0], output.getvalue()

    def test_creates_disabled_provider_without_printing_credentials(self):
        request, output = self.run_configuration()
        payload = json.loads(request.data)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(payload["identifier"], "custom:yandex")
        self.assertFalse(payload["enabled"])
        self.assertTrue(payload["pkce_enabled"])
        self.assertEqual(payload["scopes"], [])
        self.assertNotIn("test-secret", output)
        self.assertNotIn("test-signing-secret", output)
        self.assertNotIn(request.get_header("Authorization"), output)

    def test_updates_existing_provider_without_creating_duplicate(self):
        request, _ = self.run_configuration(existing={"identifier": "custom:yandex"})
        self.assertEqual(request.get_method(), "PUT")
        self.assertTrue(
            request.full_url.endswith("/admin/custom-providers/custom:yandex")
        )
        payload = json.loads(request.data)
        self.assertNotIn("identifier", payload)
        self.assertNotIn("provider_type", payload)
        self.assertFalse(payload["enabled"])

    def test_enables_provider_only_when_requested(self):
        request, _ = self.run_configuration(enable=True)
        self.assertTrue(json.loads(request.data)["enabled"])

    def test_configuration_failure_does_not_expose_upstream_response(self):
        failure = HTTPError(
            "http://localhost", 400, "Bad request", {}, io.BytesIO(b"test-secret")
        )
        with self.assertRaises(SystemExit) as error:
            self.run_configuration(failure=failure)
        self.assertEqual(
            str(error.exception), "Provider configuration failed: HTTP 400"
        )
