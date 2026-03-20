from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bot.core.config import settings
from bot.services.i18n import translate


def _join_webapp_path(base_path: str, route_path: str | None) -> str:
    normalized_base = base_path or "/"
    normalized_route = (route_path or "").strip()
    if not normalized_route:
        return normalized_base

    if not normalized_route.startswith("/"):
        normalized_route = f"/{normalized_route}"

    base_prefix = normalized_base.rstrip("/")
    if not base_prefix:
        return normalized_route

    return f"{base_prefix}{normalized_route}"


def build_webapp_url(
    referral_code: str | None = None,
    *,
    route_path: str | None = None,
    query_params: dict[str, str | None] | None = None,
) -> str:
    base_url = settings.webapp_url.strip()
    if not base_url:
        return base_url

    parsed = urlsplit(base_url)
    resolved_query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if referral_code:
        resolved_query_params["ref"] = referral_code
    for key, value in (query_params or {}).items():
        if value:
            resolved_query_params[key] = value

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            _join_webapp_path(parsed.path, route_path),
            urlencode(resolved_query_params),
            parsed.fragment,
        )
    )


def main_menu(
    *,
    referral_code: str | None = None,
    locale: str | None = None,
    route_path: str | None = None,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("common.actions.open_webapp", locale=locale),
                    web_app=WebAppInfo(
                        url=build_webapp_url(referral_code, route_path=route_path)
                    ),
                )
            ],
        ]
    )
