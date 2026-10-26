from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.services import vk_oauth as oauth

router = APIRouter()


def error_response(error: oauth.VKOAuthError) -> JSONResponse:
    headers = dict(oauth.NO_STORE)
    if error.status == 401:
        headers["WWW-Authenticate"] = (
            'Basic realm="VK OAuth bridge"'
            if error.code == "invalid_client"
            else "Bearer"
        )
    return JSONResponse(
        {"error": error.code, "error_description": str(error)},
        status_code=error.status,
        headers=headers,
    )


@router.get("/vk/authorize")
async def authorize(request: Request):
    try:
        url = await oauth.authorize(oauth.parameters(request.url.query.encode()))
        return RedirectResponse(url, status_code=302, headers=oauth.NO_STORE)
    except oauth.VKOAuthError as error:
        return error_response(error)


@router.get("/vk/callback")
async def callback(request: Request):
    try:
        url = await oauth.callback(oauth.parameters(request.url.query.encode()))
        return RedirectResponse(url, status_code=302, headers=oauth.NO_STORE)
    except oauth.VKOAuthError as error:
        return error_response(error)


@router.post("/vk/token")
async def token(request: Request):
    try:
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip()
            != "application/x-www-form-urlencoded"
        ):
            raise oauth.VKOAuthError(
                "invalid_request", "URL-encoded form is required", 415
            )
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 8192:
                raise oauth.VKOAuthError("invalid_request", "Request is too large", 413)
        result = await oauth.exchange(
            oauth.parameters(bytes(raw)), request.headers.get("authorization")
        )
        return JSONResponse(result, headers=oauth.NO_STORE)
    except oauth.VKOAuthError as error:
        return error_response(error)


@router.get("/vk/userinfo")
async def userinfo(request: Request):
    try:
        return JSONResponse(
            await oauth.userinfo(request.headers.get("authorization")),
            headers=oauth.NO_STORE,
        )
    except oauth.VKOAuthError as error:
        return error_response(error)
