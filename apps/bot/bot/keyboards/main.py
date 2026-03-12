from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bot.core.config import settings


def build_webapp_url(referral_code: str | None = None) -> str:
    base_url = settings.webapp_url.strip()
    if not base_url or not referral_code:
        return base_url

    parsed = urlsplit(base_url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_params["ref"] = referral_code
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query_params),
            parsed.fragment,
        )
    )


def main_menu(*, referral_code: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть WebApp",
                    web_app=WebAppInfo(url=build_webapp_url(referral_code)),
                )
            ],
        ]
    )
