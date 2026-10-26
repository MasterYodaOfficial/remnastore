"""An OAuth2 bridge for VK ID; Supabase remains the sole session issuer.

VK's callback device_id and POST userinfo cannot be handled by a generic
Supabase provider. The bridge exposes standard authorize/token/userinfo
endpoints, with single-use Redis state and PKCE-bound authorization codes.
No VK access/refresh token is persisted or returned to Supabase/the browser.
"""

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote_plus, urlencode, urlsplit

import httpx

from app.core.config import settings
from app.services.cache import OAuthStateUnavailable, get_cache


FLOW_TTL = 300
CODE_TTL = 120
TOKEN_TTL = 60
NO_STORE = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
}
VERIFIER = re.compile(r"[A-Za-z0-9._~-]{43,128}\Z")
CHALLENGE = re.compile(r"[A-Za-z0-9_-]{43}\Z")
HANDLE = re.compile(r"[A-Za-z0-9_-]{43}\Z")


class VKOAuthError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


@dataclass(frozen=True)
class VKConfig:
    client_id: str
    secret: str
    callback: str
    supabase_callback: str


def config() -> VKConfig:
    result = VKConfig(
        settings.vk_oauth_client_id.strip(),
        settings.vk_oauth_bridge_secret.get_secret_value(),
        settings.vk_oauth_callback_url.strip(),
        settings.vk_oauth_supabase_callback_url.strip(),
    )
    if not result.client_id or len(result.secret) < 32:
        raise VKOAuthError("temporarily_unavailable", "VK ID is not configured", 503)
    for value in (result.callback, result.supabase_callback):
        try:
            url = urlsplit(value)
        except ValueError:
            raise VKOAuthError(
                "temporarily_unavailable", "VK ID is not configured", 503
            ) from None
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise VKOAuthError(
                "temporarily_unavailable", "VK ID is not configured", 503
            )
    return result


def parameters(raw: bytes) -> dict[str, str]:
    if len(raw) > 8192:
        raise VKOAuthError("invalid_request", "Request is too large", 413)
    try:
        values = parse_qs(
            raw.decode("utf-8"),
            keep_blank_values=True,
            max_num_fields=20,
            errors="strict",
        )
    except (ValueError, UnicodeError):
        raise VKOAuthError("invalid_request", "Invalid OAuth request") from None
    if any(len(value) != 1 for value in values.values()):
        raise VKOAuthError("invalid_request", "Duplicate OAuth parameters")
    return {key: value[0] for key, value in values.items()}


def key(kind: str, value: str) -> str:
    return "oauth:vk:" + kind + ":" + hashlib.sha256(value.encode()).hexdigest()


async def store(kind: str, handle: str, payload: dict, ttl: int) -> None:
    try:
        await get_cache().set_oauth_json(key(kind, handle), payload, ttl)
    except OAuthStateUnavailable:
        raise VKOAuthError(
            "temporarily_unavailable", "VK ID is temporarily unavailable", 503
        ) from None


async def load(kind: str, handle: str, *, consume: bool = False) -> dict | None:
    if not HANDLE.fullmatch(handle):
        return None
    try:
        return await get_cache().get_oauth_json(key(kind, handle), consume=consume)
    except OAuthStateUnavailable:
        raise VKOAuthError(
            "temporarily_unavailable", "VK ID is temporarily unavailable", 503
        ) from None


async def authorize(params: dict[str, str]) -> str:
    cfg = config()
    if (
        params.get("client_id") != cfg.client_id
        or params.get("redirect_uri") != cfg.supabase_callback
    ):
        raise VKOAuthError("invalid_request", "Invalid OAuth client or redirect URI")
    challenge = params.get("code_challenge", "")
    state = params.get("state", "")
    if (
        params.get("response_type") != "code"
        or params.get("code_challenge_method", "").upper() != "S256"
        or not CHALLENGE.fullmatch(challenge)
        or not state
        or len(state) > 2048
    ):
        raise VKOAuthError(
            "invalid_request", "Authorization code flow with PKCE S256 is required"
        )
    vk_state = secrets.token_urlsafe(32)
    await store("state", vk_state, {"state": state, "challenge": challenge}, FLOW_TTL)
    return "https://id.vk.ru/authorize?" + urlencode(
        {
            "response_type": "code",
            "client_id": cfg.client_id,
            "redirect_uri": cfg.callback,
            "state": vk_state,
            "code_challenge": challenge,
            "code_challenge_method": "s256",
            "scope": "email",
        }
    )


async def callback(params: dict[str, str]) -> str:
    cfg = config()
    vk_state = params.get("state", "")
    flow = await load("state", vk_state, consume=True)
    if not flow:
        raise VKOAuthError(
            "invalid_request", "Authorization has expired or was already used"
        )
    result = {"state": flow["state"]}
    if params.get("error"):
        result["error"] = (
            "access_denied" if params["error"] == "access_denied" else "server_error"
        )
        result["error_description"] = "VK ID authorization was not completed"
    else:
        vk_code, device = params.get("code", ""), params.get("device_id", "")
        if not vk_code or not device or len(vk_code) > 2048 or len(device) > 1024:
            raise VKOAuthError(
                "invalid_request", "Missing VK authorization code or device ID"
            )
        code = secrets.token_urlsafe(32)
        await store(
            "code",
            code,
            {**flow, "vk_state": vk_state, "vk_code": vk_code, "device_id": device},
            CODE_TTL,
        )
        result["code"] = code
    return cfg.supabase_callback + "?" + urlencode(result)


def authenticate(
    params: dict[str, str], authorization: str | None, cfg: VKConfig
) -> None:
    client_id, secret = params.get("client_id", ""), params.get("client_secret", "")
    if authorization:
        if client_id or secret:
            raise VKOAuthError("invalid_client", "Invalid OAuth client", 401)
        scheme, _, value = authorization.partition(" ")
        try:
            if scheme.lower() != "basic":
                raise ValueError()
            client_id, secret = (
                base64.b64decode(value, validate=True).decode().split(":", 1)
            )
            client_id, secret = unquote_plus(client_id), unquote_plus(secret)
        except (ValueError, UnicodeError):
            raise VKOAuthError("invalid_client", "Invalid OAuth client", 401) from None
    if not hmac.compare_digest(
        client_id.encode(), cfg.client_id.encode()
    ) or not hmac.compare_digest(secret.encode(), cfg.secret.encode()):
        raise VKOAuthError("invalid_client", "Invalid OAuth client", 401)


async def vk_post(client: httpx.AsyncClient, endpoint: str, data: dict) -> dict:
    try:
        response = await client.post("https://id.vk.ru/oauth2/" + endpoint, data=data)
        payload = response.json()
    except (httpx.RequestError, ValueError):
        raise VKOAuthError(
            "temporarily_unavailable", "VK ID is temporarily unavailable", 502
        ) from None
    if response.status_code >= 500 or response.status_code == 429:
        raise VKOAuthError(
            "temporarily_unavailable", "VK ID is temporarily unavailable", 502
        )
    if (
        response.status_code != 200
        or not isinstance(payload, dict)
        or payload.get("error")
    ):
        raise VKOAuthError("invalid_grant", "VK ID authorization failed")
    return payload


def user_id(value) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    value = str(value)
    return (
        value
        if len(value) <= 32 and value.isascii() and value.isdigit() and int(value) > 0
        else None
    )


async def exchange(params: dict[str, str], authorization: str | None) -> dict:
    cfg = config()
    authenticate(params, authorization, cfg)
    if params.get("grant_type") != "authorization_code":
        raise VKOAuthError(
            "unsupported_grant_type", "Only authorization code exchange is supported"
        )
    if params.get("redirect_uri") != cfg.supabase_callback:
        raise VKOAuthError("invalid_grant", "Invalid redirect URI")
    code, verifier = params.get("code", ""), params.get("code_verifier", "")
    flow = await load("code", code)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    if (
        not flow
        or not VERIFIER.fullmatch(verifier)
        or not hmac.compare_digest(challenge, flow["challenge"])
    ):
        raise VKOAuthError("invalid_grant", "Invalid or expired authorization code")
    if not await load("code", code, consume=True):
        raise VKOAuthError("invalid_grant", "Authorization code was already used")
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        token = await vk_post(
            client,
            "auth",
            {
                "grant_type": "authorization_code",
                "client_id": cfg.client_id,
                "redirect_uri": cfg.callback,
                "code": flow["vk_code"],
                "code_verifier": verifier,
                "device_id": flow["device_id"],
                "state": flow["vk_state"],
            },
        )
        subject = user_id(token.get("user_id"))
        vk_token = token.get("access_token")
        if (
            not subject
            or not isinstance(vk_token, str)
            or not vk_token
            or token.get("state") != flow["vk_state"]
        ):
            raise VKOAuthError("invalid_grant", "Invalid VK token response")
        profile = (
            await vk_post(
                client,
                "user_info",
                {"client_id": cfg.client_id, "access_token": vk_token},
            )
        ).get("user")
    if not isinstance(profile, dict) or user_id(profile.get("user_id")) != subject:
        raise VKOAuthError(
            "invalid_grant", "VK profile does not match the authorized user"
        )
    claims = {"sub": subject, "email_verified": False}
    email = profile.get("email")
    if isinstance(email, str) and email.strip():
        claims["email"] = email.strip()
    names = [profile.get("first_name"), profile.get("last_name")]
    name = " ".join(
        value.strip() for value in names if isinstance(value, str) and value.strip()
    )
    if name:
        claims["name"] = name
    access_token = secrets.token_urlsafe(32)
    await store("token", access_token, claims, TOKEN_TTL)
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": TOKEN_TTL,
    }


async def userinfo(authorization: str | None) -> dict:
    config()
    scheme, _, token = (authorization or "").partition(" ")
    claims = await load("token", token) if scheme.lower() == "bearer" else None
    if not claims:
        raise VKOAuthError("invalid_token", "Invalid or expired profile token", 401)
    return claims
