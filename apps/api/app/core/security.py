import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict
from urllib.parse import parse_qsl

from fastapi import HTTPException, status

from app.services.i18n import translate


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _constant_time_compare(val1: bytes, val2: bytes) -> bool:
    return hmac.compare_digest(val1, val2)


def create_access_token(
    payload: Dict[str, Any], *, secret: str, expires_in_seconds: int
) -> str:
    now = int(time.time())
    claims = {**payload, "exp": now + expires_in_seconds, "iat": now}

    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode()
    )
    claims_b64 = _b64encode(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
    )
    signing_input = f"{header_b64}.{claims_b64}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64encode(signature)
    return f"{header_b64}.{claims_b64}.{signature_b64}"


class TokenError(Exception):
    pass


def decode_access_token(token: str, *, secret: str) -> Dict[str, Any]:
    try:
        header_b64, claims_b64, signature_b64 = token.split(".")
    except ValueError as exc:  # wrong segments
        raise TokenError("invalid token format") from exc

    signing_input = f"{header_b64}.{claims_b64}".encode()
    expected_sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    try:
        signature = _b64decode(signature_b64)
    except Exception as exc:  # pragma: no cover - decode error
        raise TokenError("invalid signature encoding") from exc

    if not _constant_time_compare(signature, expected_sig):
        raise TokenError("signature mismatch")

    try:
        claims: Dict[str, Any] = json.loads(_b64decode(claims_b64))
    except Exception as exc:  # pragma: no cover
        raise TokenError("invalid claims encoding") from exc

    exp = claims.get("exp")
    if exp is None or not isinstance(exp, int):
        raise TokenError("token missing exp")
    if int(time.time()) >= exp:
        raise TokenError("token expired")

    return claims


def verify_telegram_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int,
) -> Dict[str, Any]:
    """Validate Telegram WebApp initData payload.

    Steps per Telegram docs:
    1) Parse query-string-like init_data into key/value pairs.
    2) Build data_check_string excluding `hash`, sorted by key.
    3) Compute secret_key = HMAC_SHA256(bot_token, key="WebAppData").
    4) Compute HMAC-SHA256 of data_check_string using secret_key.
    4) Compare with provided hash, enforce TTL via auth_date.
    """

    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=translate("api.auth.errors.bot_token_not_configured"),
        )

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    provided_hash = parsed.pop("hash", None)
    if not provided_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("api.auth.errors.hash_missing"),
        )

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, provided_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=translate("api.auth.errors.invalid_signature"),
        )

    auth_date_raw = parsed.get("auth_date")
    try:
        auth_date = int(auth_date_raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("api.auth.errors.auth_date_invalid"),
        )

    if int(time.time()) - auth_date > max_age_seconds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=translate("api.auth.errors.init_data_expired"),
        )

    # Convert user JSON (if present) into dict for convenience
    if "user" in parsed:
        try:
            parsed["user"] = json.loads(parsed["user"])
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=translate("api.auth.errors.user_payload_invalid"),
            )

    parsed["hash"] = provided_hash
    return parsed
