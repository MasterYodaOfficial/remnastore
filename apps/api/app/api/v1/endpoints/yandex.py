"""Translate Yandex's profile into the claims expected by Supabase custom OAuth.

OAuth code exchange, state and PKCE remain entirely in Supabase Auth. This
endpoint accepts only a Yandex token for our configured application, never a
client-supplied profile or email. Tokens are not persisted or logged.
"""

import httpx
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings

router = APIRouter()
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def fail(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail, headers=NO_STORE)


@router.get("/yandex/userinfo")
async def yandex_userinfo(authorization: str | None = Header(default=None)):
    client_id = settings.yandex_oauth_client_id.strip()
    if not client_id:
        raise fail(503, "Yandex sign-in is not configured")
    scheme, _, token = (authorization or "").partition(" ")
    if (
        scheme.lower() not in {"bearer", "oauth"}
        or not token
        or any(c.isspace() for c in token)
    ):
        raise fail(401, "A Yandex access token is required")

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get(
                "https://login.yandex.ru/info",
                params={"format": "json"},
                headers={"Authorization": f"OAuth {token}"},
            )
    except httpx.RequestError:
        raise fail(502, "Yandex is temporarily unavailable") from None
    if response.status_code in {401, 403}:
        raise fail(401, "Invalid Yandex access token")
    if response.status_code != 200:
        raise fail(502, "Yandex is temporarily unavailable")
    try:
        profile = response.json()
    except ValueError:
        raise fail(502, "Invalid Yandex profile") from None
    if not isinstance(profile, dict):
        raise fail(502, "Invalid Yandex profile")
    if profile.get("client_id") != client_id:
        raise fail(401, "Token belongs to a different Yandex application")
    subject = profile.get("id")
    if not isinstance(subject, str) or not subject.strip():
        raise fail(502, "Yandex profile has no subject")
    email = profile.get("default_email")
    if not isinstance(email, str) or not email.strip():
        raise fail(422, "Yandex email permission is required")

    claims = {
        "sub": subject,
        "email": email.strip(),
        # Yandex /info does not attest email verification. Supabase must verify
        # it before using it for account linking; do not infer this from a domain.
        "email_verified": False,
    }
    for source, destination in (
        ("real_name", "name"),
        ("display_name", "nickname"),
        ("login", "preferred_username"),
    ):
        value = profile.get(source)
        if isinstance(value, str) and value.strip():
            claims[destination] = value.strip()
    return JSONResponse(claims, headers=NO_STORE)
