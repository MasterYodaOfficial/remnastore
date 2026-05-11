import base64
import hashlib
import hmac
import json
import time
import unittest
from urllib.parse import urlencode

from fastapi import HTTPException

from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    verify_telegram_init_data,
)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign_custom_token(claims: dict[str, object], *, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode()
    )
    claims_b64 = _b64encode(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
    )
    signing_input = f"{header_b64}.{claims_b64}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{claims_b64}.{_b64encode(signature)}"


def _build_init_data(bot_token: str, **fields: str) -> str:
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    data_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode({**fields, "hash": data_hash})


class SecurityTests(unittest.TestCase):
    def test_access_token_round_trip_preserves_payload(self) -> None:
        token = create_access_token(
            {"sub": "account-1", "scope": "account"},
            secret="jwt-secret",
            expires_in_seconds=300,
        )

        claims = decode_access_token(token, secret="jwt-secret")

        self.assertEqual(claims["sub"], "account-1")
        self.assertEqual(claims["scope"], "account")
        self.assertIsInstance(claims["iat"], int)
        self.assertGreater(claims["exp"], claims["iat"])

    def test_decode_access_token_rejects_invalid_format(self) -> None:
        with self.assertRaisesRegex(TokenError, "invalid token format"):
            decode_access_token("not-a-jwt", secret="jwt-secret")

    def test_decode_access_token_rejects_signature_mismatch(self) -> None:
        token = create_access_token(
            {"sub": "account-1"},
            secret="jwt-secret",
            expires_in_seconds=300,
        )

        with self.assertRaisesRegex(TokenError, "signature mismatch"):
            decode_access_token(token, secret="other-secret")

    def test_decode_access_token_rejects_missing_exp_claim(self) -> None:
        token = _sign_custom_token(
            {"sub": "account-1", "iat": int(time.time())},
            secret="jwt-secret",
        )

        with self.assertRaisesRegex(TokenError, "token missing exp"):
            decode_access_token(token, secret="jwt-secret")

    def test_decode_access_token_rejects_expired_token(self) -> None:
        token = create_access_token(
            {"sub": "account-1"},
            secret="jwt-secret",
            expires_in_seconds=-1,
        )

        with self.assertRaisesRegex(TokenError, "token expired"):
            decode_access_token(token, secret="jwt-secret")

    def test_verify_telegram_init_data_requires_bot_token(self) -> None:
        with self.assertRaises(HTTPException) as captured:
            verify_telegram_init_data(
                "auth_date=1&hash=test",
                bot_token="",
                max_age_seconds=60,
            )

        self.assertEqual(captured.exception.status_code, 500)

    def test_verify_telegram_init_data_rejects_missing_hash(self) -> None:
        with self.assertRaises(HTTPException) as captured:
            verify_telegram_init_data(
                "auth_date=1&user=%7B%7D",
                bot_token="bot-secret",
                max_age_seconds=60,
            )

        self.assertEqual(captured.exception.status_code, 400)

    def test_verify_telegram_init_data_rejects_invalid_signature(self) -> None:
        init_data = urlencode({"auth_date": str(int(time.time())), "hash": "bad"})

        with self.assertRaises(HTTPException) as captured:
            verify_telegram_init_data(
                init_data,
                bot_token="bot-secret",
                max_age_seconds=60,
            )

        self.assertEqual(captured.exception.status_code, 401)

    def test_verify_telegram_init_data_rejects_invalid_or_expired_auth_date(
        self,
    ) -> None:
        valid_hash = _build_init_data("bot-secret", auth_date="not-an-int")
        with self.assertRaises(HTTPException) as captured:
            verify_telegram_init_data(
                valid_hash,
                bot_token="bot-secret",
                max_age_seconds=60,
            )
        self.assertEqual(captured.exception.status_code, 400)

        expired_hash = _build_init_data(
            "bot-secret",
            auth_date=str(int(time.time()) - 3600),
        )
        with self.assertRaises(HTTPException) as captured:
            verify_telegram_init_data(
                expired_hash,
                bot_token="bot-secret",
                max_age_seconds=60,
            )
        self.assertEqual(captured.exception.status_code, 401)

    def test_verify_telegram_init_data_rejects_invalid_user_payload(self) -> None:
        init_data = _build_init_data(
            "bot-secret",
            auth_date=str(int(time.time())),
            user="{bad-json}",
        )

        with self.assertRaises(HTTPException) as captured:
            verify_telegram_init_data(
                init_data,
                bot_token="bot-secret",
                max_age_seconds=60,
            )

        self.assertEqual(captured.exception.status_code, 400)

    def test_verify_telegram_init_data_returns_parsed_payload(self) -> None:
        user_payload = json.dumps({"id": 700001, "username": "tester"})
        init_data = _build_init_data(
            "bot-secret",
            auth_date=str(int(time.time())),
            query_id="query-1",
            user=user_payload,
        )

        parsed = verify_telegram_init_data(
            init_data,
            bot_token="bot-secret",
            max_age_seconds=60,
        )

        self.assertEqual(parsed["query_id"], "query-1")
        self.assertEqual(parsed["user"]["id"], 700001)
        self.assertIn("hash", parsed)
