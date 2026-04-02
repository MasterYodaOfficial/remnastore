from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
    WebAppInfo,
)

from bot.callbacks.menu import action, nav
from bot.keyboards.main import build_webapp_url
from bot.services.api import ApiClient
from bot.services.i18n import html_safe, translate, translate_html
from bot.services.media_registry import get_media_registry
from bot.services.session_store import MenuSession, get_menu_session_store

SCREEN_HOME = "home"
SCREEN_SUBSCRIPTION = "subscription"
SCREEN_PLANS = "plans"
SCREEN_PLAN = "plan"
SCREEN_REFERRALS = "referrals"
SCREEN_HELP = "help"
SCREEN_PAYMENT_READY = "payment_ready"

ASSET_WELCOME = "welcome"
ASSET_LOGO = "logo"
BUTTON_STYLE_SUCCESS = "success"
BUTTON_STYLE_DANGER = "danger"
YOOKASSA_IDEMPOTENCY_KEY_MAX_LENGTH = 64


@dataclass(slots=True)
class RenderedMenu:
    caption: str
    reply_markup: InlineKeyboardMarkup
    screen: str
    asset_name: str
    screen_params: dict[str, str] = field(default_factory=dict)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _format_date(value: object, *, locale: str | None) -> str:
    dt = _parse_datetime(value)
    if dt is None:
        return translate("bot.menu.values.not_available", locale=locale)
    return dt.strftime("%d.%m.%Y")


def _format_integer(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _format_percent(value: object) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value <= 1:
            return str(int(round(value * 100)))
        return str(int(round(value)))
    if isinstance(value, str) and value.strip():
        try:
            numeric_value = float(value)
        except ValueError:
            return "0"
        if numeric_value <= 1:
            return str(int(round(numeric_value * 100)))
        return str(int(round(numeric_value)))
    return "0"


def _safe_string(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _normalize_promo_code(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(value.strip().upper().split())


def _safe_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _safe_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _top_webapp_row(
    *, locale: str | None, referral_code: str | None
) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text=translate("common.actions.open_webapp", locale=locale),
            style=BUTTON_STYLE_SUCCESS,
            web_app=WebAppInfo(url=build_webapp_url(referral_code)),
        )
    ]


def _back_button(*, locale: str | None, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=translate("common.actions.back", locale=locale),
        style=BUTTON_STYLE_DANGER,
        callback_data=callback_data,
    )


def _build_bot_payment_idempotency_key(*, provider: str, telegram_id: int) -> str:
    # YooKassa rejects Idempotence-Key values longer than 64 chars.
    key = f"bot:{provider}:{telegram_id}:{uuid4().hex}"
    return key[:YOOKASSA_IDEMPOTENCY_KEY_MAX_LENGTH]


def _subscription_status(subscription: dict[str, Any], *, locale: str | None) -> str:
    if not subscription:
        return translate("bot.menu.values.not_connected", locale=locale)

    if subscription.get("is_trial"):
        trial_ends_at = subscription.get("trial_ends_at") or subscription.get(
            "expires_at"
        )
        if trial_ends_at:
            return translate(
                "bot.menu.values.trial_active_until",
                locale=locale,
                date=_format_date(trial_ends_at, locale=locale),
            )
        return translate("bot.menu.values.trial_access", locale=locale)

    if subscription.get("is_active"):
        expires_at = subscription.get("expires_at")
        if expires_at:
            return translate(
                "bot.menu.values.active_until",
                locale=locale,
                date=_format_date(expires_at, locale=locale),
            )
        return translate("bot.menu.values.active", locale=locale)

    return translate("bot.menu.values.not_connected", locale=locale)


def _access_type(subscription: dict[str, Any], *, locale: str | None) -> str:
    if subscription.get("is_trial"):
        return translate("bot.menu.values.trial_access", locale=locale)
    if subscription.get("is_active"):
        return translate("bot.menu.values.paid_access", locale=locale)
    return translate("bot.menu.values.not_available", locale=locale)


def _trial_status(
    subscription: dict[str, Any],
    trial_eligibility: dict[str, Any],
    *,
    locale: str | None,
) -> str:
    if subscription.get("is_trial"):
        trial_ends_at = subscription.get("trial_ends_at") or subscription.get(
            "expires_at"
        )
        if trial_ends_at:
            return translate(
                "bot.menu.values.trial_active_until",
                locale=locale,
                date=_format_date(trial_ends_at, locale=locale),
            )
        return translate("bot.menu.values.trial_access", locale=locale)

    if trial_eligibility.get("eligible"):
        return translate("bot.menu.values.trial_available", locale=locale)
    if trial_eligibility.get("has_used_trial") or subscription.get("has_used_trial"):
        return translate("bot.menu.values.trial_used", locale=locale)
    return translate("bot.menu.values.trial_unavailable", locale=locale)


def _config_status(subscription: dict[str, Any], *, locale: str | None) -> str:
    return translate(
        "bot.menu.values.yes"
        if subscription.get("subscription_url")
        else "bot.menu.values.no",
        locale=locale,
    )


def _price_stars_label(plan: dict[str, Any], *, locale: str | None) -> str:
    price_stars = plan.get("price_stars")
    if price_stars is None:
        return translate("bot.menu.values.stars_not_available", locale=locale)
    return str(_format_integer(price_stars))


def _features_block(plan: dict[str, Any], *, locale: str | None) -> str:
    features = plan.get("features")
    if not isinstance(features, list) or not features:
        return html_safe(translate_html("bot.menu.values.not_available", locale=locale))
    return html_safe(
        "\n".join(
            translate_html("bot.menu.feature_line", locale=locale, feature=str(feature))
            for feature in features
            if str(feature).strip()
        )
    )


def _plans_overview(plans: list[dict[str, Any]], *, locale: str | None) -> str:
    if not plans:
        return html_safe(translate_html("bot.menu.plans.empty", locale=locale))

    return html_safe(
        "\n".join(
            translate_html(
                "bot.menu.plan_line",
                locale=locale,
                name=_safe_string(
                    plan.get("name"),
                    fallback=_safe_string(
                        plan.get("code"),
                        fallback=translate(
                            "bot.menu.values.plan_fallback", locale=locale
                        ),
                    ),
                ),
                price_rub=_format_integer(plan.get("price_rub")),
                duration_days=_format_integer(plan.get("duration_days")),
                price_stars=_price_stars_label(plan, locale=locale),
            )
            for plan in plans
        )
    )


def _provider_label(provider: str, *, locale: str | None) -> str:
    if provider == "telegram_stars":
        return translate("bot.menu.providers.telegram_stars", locale=locale)
    if provider == "yookassa":
        return translate("bot.menu.providers.yookassa", locale=locale)
    return provider


def _amount_label(amount: object, currency: object, *, locale: str | None) -> str:
    normalized_currency = _safe_string(currency, fallback="")
    normalized_amount = _format_integer(amount)
    if normalized_currency == "RUB":
        return f"{normalized_amount} ₽"
    if normalized_currency == "XTR":
        return f"{normalized_amount} {translate('bot.menu.providers.telegram_stars', locale=locale)}"
    if normalized_currency:
        return f"{normalized_amount} {normalized_currency}"
    return str(normalized_amount)


def _extract_http_error_detail(
    exc: httpx.HTTPStatusError, *, locale: str | None
) -> str:
    detail = translate("bot.menu.messages.generic_error", locale=locale)
    response = exc.response
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        raw_detail = payload.get("detail")
        if isinstance(raw_detail, str) and raw_detail.strip():
            detail = raw_detail.strip()
    return translate("bot.errors.api_http_error", locale=locale, detail=detail)


async def _get_dashboard_payload(
    client: ApiClient, *, telegram_id: int
) -> dict[str, Any]:
    try:
        return _safe_dict(await client.get_bot_dashboard(telegram_id=telegram_id))
    except httpx.HTTPError:
        return {}


async def _get_plans_payload(client: ApiClient) -> list[dict[str, Any]]:
    try:
        payload = _safe_dict(await client.get_bot_plans())
    except httpx.HTTPError:
        return []
    return _safe_list(payload.get("items"))


def _build_home_keyboard(
    *, locale: str | None, referral_code: str | None
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            _top_webapp_row(locale=locale, referral_code=referral_code),
            [
                InlineKeyboardButton(
                    text=translate("common.actions.subscription", locale=locale),
                    callback_data=nav(SCREEN_SUBSCRIPTION),
                ),
                InlineKeyboardButton(
                    text=translate("common.actions.plans", locale=locale),
                    callback_data=nav(SCREEN_PLANS),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("common.actions.referrals", locale=locale),
                    callback_data=nav(SCREEN_REFERRALS),
                ),
                InlineKeyboardButton(
                    text=translate("common.actions.help", locale=locale),
                    callback_data=nav(SCREEN_HELP),
                ),
            ],
        ]
    )


def _build_subscription_keyboard(
    subscription: dict[str, Any],
    trial_eligibility: dict[str, Any],
    *,
    locale: str | None,
    referral_code: str | None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        _top_webapp_row(locale=locale, referral_code=referral_code)
    ]

    subscription_url = _safe_string(subscription.get("subscription_url"), fallback="")
    if subscription_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate("common.actions.get_config", locale=locale),
                    url=subscription_url,
                )
            ]
        )

    if bool(trial_eligibility.get("eligible")):
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate("common.actions.activate_trial", locale=locale),
                    callback_data=action("trial", "activate"),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=translate("common.actions.plans", locale=locale),
                callback_data=nav(SCREEN_PLANS),
            ),
            InlineKeyboardButton(
                text=translate(
                    "common.actions.open_subscription_in_webapp", locale=locale
                ),
                web_app=WebAppInfo(url=build_webapp_url(referral_code, route_path="/")),
            ),
        ]
    )
    rows.append([_back_button(locale=locale, callback_data=nav(SCREEN_HOME))])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_plans_keyboard(
    plans: list[dict[str, Any]],
    *,
    locale: str | None,
    referral_code: str | None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        _top_webapp_row(locale=locale, referral_code=referral_code)
    ]

    for plan in plans:
        plan_code = _safe_string(plan.get("code"), fallback="")
        if not plan_code:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{_safe_string(plan.get('name'), fallback=plan_code)} · {_format_integer(plan.get('price_rub'))} ₽",
                    callback_data=action("plan", "open", plan_code),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=translate("common.actions.open_plans_in_webapp", locale=locale),
                web_app=WebAppInfo(
                    url=build_webapp_url(referral_code, route_path="/plans")
                ),
            )
        ]
    )
    rows.append([_back_button(locale=locale, callback_data=nav(SCREEN_HOME))])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_plan_detail_keyboard(
    *,
    locale: str | None,
    referral_code: str | None,
    plan: dict[str, Any],
    account_exists: bool,
    promo_code: str | None = None,
) -> InlineKeyboardMarkup:
    plan_code = _safe_string(plan.get("code"), fallback="")
    rows: list[list[InlineKeyboardButton]] = [
        _top_webapp_row(locale=locale, referral_code=referral_code)
    ]
    promo_checkout_url = ""
    if plan_code and promo_code:
        promo_checkout_url = build_webapp_url(
            referral_code,
            route_path="/plans",
            query_params={
                "tab": "plans",
                "plan": plan_code,
                "promo": promo_code,
            },
        )

    if promo_checkout_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate(
                        "common.actions.apply_promo_in_webapp", locale=locale
                    ),
                    web_app=WebAppInfo(url=promo_checkout_url),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate("common.actions.open_in_browser", locale=locale),
                    url=promo_checkout_url,
                )
            ]
        )
    elif account_exists and plan_code:
        if plan.get("price_stars") is not None:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=translate("common.actions.buy_in_telegram", locale=locale),
                        callback_data=action("pay", "stars", plan_code),
                    )
                ]
            )

        rows.append(
            [
                InlineKeyboardButton(
                    text=translate("common.actions.pay_by_card", locale=locale),
                    callback_data=action("pay", "yookassa", plan_code),
                )
            ]
        )
    if plan_code:
        promo_buttons = [
            InlineKeyboardButton(
                text=translate("common.actions.enter_promo_code", locale=locale),
                callback_data=action("promo", "enter", plan_code),
            )
        ]
        if promo_code:
            promo_buttons.append(
                InlineKeyboardButton(
                    text=translate("common.actions.clear_promo_code", locale=locale),
                    callback_data=action("promo", "clear", plan_code),
                )
            )
        rows.append(promo_buttons)

    rows.append(
        [
            InlineKeyboardButton(
                text=translate("common.actions.open_plans_in_webapp", locale=locale),
                web_app=WebAppInfo(
                    url=build_webapp_url(referral_code, route_path="/plans")
                ),
            )
        ]
    )
    rows.append([_back_button(locale=locale, callback_data=nav(SCREEN_PLANS))])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_referrals_keyboard(
    *, locale: str | None, referral_code: str | None
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            _top_webapp_row(locale=locale, referral_code=referral_code),
            [
                InlineKeyboardButton(
                    text=translate(
                        "common.actions.open_referrals_in_webapp", locale=locale
                    ),
                    web_app=WebAppInfo(
                        url=build_webapp_url(referral_code, route_path="/referral")
                    ),
                )
            ],
            [_back_button(locale=locale, callback_data=nav(SCREEN_HOME))],
        ]
    )


def _build_help_keyboard(
    *, locale: str | None, referral_code: str | None
) -> InlineKeyboardMarkup:
    from bot.core.config import settings

    rows: list[list[InlineKeyboardButton]] = [
        _top_webapp_row(locale=locale, referral_code=referral_code)
    ]

    help_buttons: list[InlineKeyboardButton] = []
    if settings.bot_help_telegram_url.strip():
        help_buttons.append(
            InlineKeyboardButton(
                text=translate("common.actions.instructions_channel", locale=locale),
                url=settings.bot_help_telegram_url.strip(),
            )
        )
    if settings.support_telegram_url.strip():
        help_buttons.append(
            InlineKeyboardButton(
                text=translate("common.actions.support", locale=locale),
                url=settings.support_telegram_url.strip(),
            )
        )
    if help_buttons:
        rows.append(help_buttons)

    rows.append(
        [
            InlineKeyboardButton(
                text=translate("common.actions.faq_in_webapp", locale=locale),
                web_app=WebAppInfo(
                    url=build_webapp_url(referral_code, route_path="/faq")
                ),
            )
        ]
    )
    rows.append([_back_button(locale=locale, callback_data=nav(SCREEN_HOME))])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_payment_ready_keyboard(
    *,
    locale: str | None,
    referral_code: str | None,
    payment_url: str,
    plan_code: str | None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        _top_webapp_row(locale=locale, referral_code=referral_code)
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=translate("common.actions.pay_now", locale=locale),
                url=payment_url,
            )
        ]
    )

    if plan_code:
        rows.append(
            [
                _back_button(
                    locale=locale, callback_data=action("plan", "open", plan_code)
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate("common.actions.home", locale=locale),
                    callback_data=nav(SCREEN_HOME),
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def build_rendered_menu(
    *,
    telegram_id: int,
    locale: str | None,
    screen: str,
    screen_params: dict[str, str] | None = None,
    referral_code: str | None = None,
    api_client: ApiClient | None = None,
) -> RenderedMenu:
    client = api_client or ApiClient()
    params = dict(screen_params or {})

    if screen == SCREEN_HOME:
        dashboard = await _get_dashboard_payload(client, telegram_id=telegram_id)
        if not dashboard.get("exists"):
            return RenderedMenu(
                caption=translate_html("bot.menu.home.guest_caption", locale=locale),
                reply_markup=_build_home_keyboard(
                    locale=locale, referral_code=referral_code
                ),
                screen=SCREEN_HOME,
                asset_name=ASSET_WELCOME,
            )

        referral = _safe_dict(dashboard.get("referral"))
        account = _safe_dict(dashboard.get("account"))
        subscription = _safe_dict(dashboard.get("subscription"))
        return RenderedMenu(
            caption=translate_html(
                "bot.menu.home.caption",
                locale=locale,
                balance_rub=_format_integer(account.get("balance")),
                subscription_status=_subscription_status(subscription, locale=locale),
                referrals_count=_format_integer(referral.get("referrals_count")),
                available_for_withdraw_rub=_format_integer(
                    referral.get("available_for_withdraw")
                ),
            ),
            reply_markup=_build_home_keyboard(
                locale=locale, referral_code=referral_code
            ),
            screen=SCREEN_HOME,
            asset_name=ASSET_WELCOME,
        )

    if screen == SCREEN_SUBSCRIPTION:
        dashboard = await _get_dashboard_payload(client, telegram_id=telegram_id)
        if not dashboard.get("exists"):
            return RenderedMenu(
                caption=translate_html(
                    "bot.menu.subscription.guest_caption", locale=locale
                ),
                reply_markup=_build_subscription_keyboard(
                    {},
                    {},
                    locale=locale,
                    referral_code=referral_code,
                ),
                screen=SCREEN_SUBSCRIPTION,
                asset_name=ASSET_LOGO,
            )

        subscription = _safe_dict(dashboard.get("subscription"))
        trial_eligibility = _safe_dict(dashboard.get("trial_eligibility"))
        return RenderedMenu(
            caption=translate_html(
                "bot.menu.subscription.caption",
                locale=locale,
                status=_subscription_status(subscription, locale=locale),
                expires_at=_format_date(subscription.get("expires_at"), locale=locale),
                days_left=subscription.get("days_left")
                if subscription.get("days_left") is not None
                else translate("bot.menu.values.days_unknown", locale=locale),
                access_type=_access_type(subscription, locale=locale),
                config_status=_config_status(subscription, locale=locale),
                trial_status=_trial_status(
                    subscription, trial_eligibility, locale=locale
                ),
            ),
            reply_markup=_build_subscription_keyboard(
                subscription,
                trial_eligibility,
                locale=locale,
                referral_code=referral_code,
            ),
            screen=SCREEN_SUBSCRIPTION,
            asset_name=ASSET_LOGO,
        )

    if screen == SCREEN_PLANS:
        plans = await _get_plans_payload(client)
        return RenderedMenu(
            caption=translate_html(
                "bot.menu.plans.caption",
                locale=locale,
                plans_overview=_plans_overview(plans, locale=locale),
            ),
            reply_markup=_build_plans_keyboard(
                plans, locale=locale, referral_code=referral_code
            ),
            screen=SCREEN_PLANS,
            asset_name=ASSET_LOGO,
        )

    if screen == SCREEN_PLAN:
        plans = await _get_plans_payload(client)
        plan_code = _safe_string(params.get("plan_code"), fallback="")
        promo_code = _normalize_promo_code(params.get("promo_code"))
        selected_plan = next(
            (
                plan
                for plan in plans
                if _safe_string(plan.get("code"), fallback="") == plan_code
            ),
            None,
        )
        if selected_plan is None:
            return await build_rendered_menu(
                telegram_id=telegram_id,
                locale=locale,
                screen=SCREEN_PLANS,
                referral_code=referral_code,
                api_client=client,
            )

        dashboard = await _get_dashboard_payload(client, telegram_id=telegram_id)
        caption_key = (
            "bot.menu.plan_detail.caption"
            if dashboard.get("exists")
            else "bot.menu.plan_detail.guest_caption"
        )
        caption = translate_html(
            caption_key,
            locale=locale,
            plan_name=_safe_string(selected_plan.get("name"), fallback=plan_code),
            duration_days=_format_integer(selected_plan.get("duration_days")),
            price_rub=_format_integer(selected_plan.get("price_rub")),
            price_stars=_price_stars_label(selected_plan, locale=locale),
            features_block=_features_block(selected_plan, locale=locale),
        )
        if promo_code:
            caption = "\n\n".join(
                [
                    caption,
                    translate_html(
                        "bot.menu.plan_detail.promo_line",
                        locale=locale,
                        promo_code=promo_code,
                    ),
                    translate_html("bot.menu.plan_detail.promo_hint", locale=locale),
                ]
            )
        rendered_screen_params = {"plan_code": plan_code}
        if promo_code:
            rendered_screen_params["promo_code"] = promo_code
        return RenderedMenu(
            caption=caption,
            reply_markup=_build_plan_detail_keyboard(
                locale=locale,
                referral_code=referral_code,
                plan=selected_plan,
                account_exists=bool(dashboard.get("exists")),
                promo_code=promo_code or None,
            ),
            screen=SCREEN_PLAN,
            asset_name=ASSET_LOGO,
            screen_params=rendered_screen_params,
        )

    if screen == SCREEN_REFERRALS:
        dashboard = await _get_dashboard_payload(client, telegram_id=telegram_id)
        if not dashboard.get("exists"):
            return RenderedMenu(
                caption=translate_html(
                    "bot.menu.referrals.guest_caption", locale=locale
                ),
                reply_markup=_build_referrals_keyboard(
                    locale=locale, referral_code=referral_code
                ),
                screen=SCREEN_REFERRALS,
                asset_name=ASSET_LOGO,
            )

        referral = _safe_dict(dashboard.get("referral"))
        return RenderedMenu(
            caption=translate_html(
                "bot.menu.referrals.caption",
                locale=locale,
                referral_code=_safe_string(
                    referral.get("referral_code"),
                    fallback=translate("bot.menu.values.not_available", locale=locale),
                ),
                referrals_count=_format_integer(referral.get("referrals_count")),
                total_earnings_rub=_format_integer(referral.get("referral_earnings")),
                available_for_withdraw_rub=_format_integer(
                    referral.get("available_for_withdraw")
                ),
                reward_rate_percent=_format_percent(
                    referral.get("effective_reward_rate")
                ),
            ),
            reply_markup=_build_referrals_keyboard(
                locale=locale, referral_code=referral_code
            ),
            screen=SCREEN_REFERRALS,
            asset_name=ASSET_LOGO,
        )

    if screen == SCREEN_HELP:
        return RenderedMenu(
            caption=translate_html("bot.menu.help.caption", locale=locale),
            reply_markup=_build_help_keyboard(
                locale=locale, referral_code=referral_code
            ),
            screen=SCREEN_HELP,
            asset_name=ASSET_LOGO,
        )

    if screen == SCREEN_PAYMENT_READY:
        payment_url = _safe_string(params.get("payment_url"), fallback="")
        return RenderedMenu(
            caption=translate_html(
                "bot.menu.payment_ready.caption",
                locale=locale,
                plan_name=_safe_string(
                    params.get("plan_name"),
                    fallback=_safe_string(
                        params.get("plan_code"),
                        fallback=translate(
                            "bot.menu.values.plan_fallback", locale=locale
                        ),
                    ),
                ),
                provider_label=_provider_label(
                    _safe_string(params.get("provider"), fallback=""),
                    locale=locale,
                ),
                amount_label=_amount_label(
                    params.get("amount"),
                    params.get("currency"),
                    locale=locale,
                ),
            ),
            reply_markup=_build_payment_ready_keyboard(
                locale=locale,
                referral_code=referral_code,
                payment_url=payment_url,
                plan_code=params.get("plan_code"),
            ),
            screen=SCREEN_PAYMENT_READY,
            asset_name=ASSET_LOGO,
            screen_params=params,
        )

    return await build_rendered_menu(
        telegram_id=telegram_id,
        locale=locale,
        screen=SCREEN_HOME,
        referral_code=referral_code,
        api_client=client,
    )


async def present_menu(
    bot: Bot,
    *,
    chat_id: int,
    telegram_id: int,
    locale: str | None,
    screen: str = SCREEN_HOME,
    screen_params: dict[str, str] | None = None,
    referral_code: str | None = None,
    api_client: ApiClient | None = None,
    force_new: bool = False,
) -> Message | None:
    session_store = get_menu_session_store()
    existing_session = await session_store.get(telegram_id)
    effective_referral_code = referral_code
    if effective_referral_code is None and existing_session is not None:
        effective_referral_code = existing_session.referral_code

    rendered = await build_rendered_menu(
        telegram_id=telegram_id,
        locale=locale,
        screen=screen,
        screen_params=screen_params,
        referral_code=effective_referral_code,
        api_client=api_client,
    )

    media_registry = get_media_registry()
    if existing_session is not None and not force_new:
        target_chat_id = existing_session.chat_id
        try:
            if existing_session.asset_name == rendered.asset_name:
                result = await bot.edit_message_caption(
                    chat_id=target_chat_id,
                    message_id=existing_session.menu_message_id,
                    caption=rendered.caption,
                    parse_mode="HTML",
                    reply_markup=rendered.reply_markup,
                )
                sent_message = result if isinstance(result, Message) else None
            else:
                result = await bot.edit_message_media(
                    chat_id=target_chat_id,
                    message_id=existing_session.menu_message_id,
                    media=InputMediaPhoto(
                        media=await media_registry.get_input_file(rendered.asset_name),
                        caption=rendered.caption,
                        parse_mode="HTML",
                    ),
                    reply_markup=rendered.reply_markup,
                )
                sent_message = result if isinstance(result, Message) else None
                await media_registry.remember_message_media(
                    rendered.asset_name, sent_message
                )

            await session_store.save(
                MenuSession(
                    telegram_id=telegram_id,
                    chat_id=target_chat_id,
                    menu_message_id=existing_session.menu_message_id,
                    screen=rendered.screen,
                    screen_params=rendered.screen_params,
                    referral_code=effective_referral_code,
                    asset_name=rendered.asset_name,
                )
            )
            return sent_message
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                await session_store.save(
                    MenuSession(
                        telegram_id=telegram_id,
                        chat_id=target_chat_id,
                        menu_message_id=existing_session.menu_message_id,
                        screen=rendered.screen,
                        screen_params=rendered.screen_params,
                        referral_code=effective_referral_code,
                        asset_name=rendered.asset_name,
                    )
                )
                return None

    sent_message = await bot.send_photo(
        chat_id=chat_id,
        photo=await media_registry.get_input_file(rendered.asset_name),
        caption=rendered.caption,
        parse_mode="HTML",
        reply_markup=rendered.reply_markup,
    )
    await media_registry.remember_message_media(rendered.asset_name, sent_message)
    if force_new and existing_session is not None:
        try:
            await bot.edit_message_reply_markup(
                chat_id=existing_session.chat_id,
                message_id=existing_session.menu_message_id,
                reply_markup=None,
            )
        except TelegramBadRequest:
            pass
    await session_store.save(
        MenuSession(
            telegram_id=telegram_id,
            chat_id=chat_id,
            menu_message_id=sent_message.message_id,
            screen=rendered.screen,
            screen_params=rendered.screen_params,
            referral_code=effective_referral_code,
            asset_name=rendered.asset_name,
        )
    )
    return sent_message


async def show_menu_for_message(
    message: Message,
    *,
    screen: str = SCREEN_HOME,
    screen_params: dict[str, str] | None = None,
    referral_code: str | None = None,
    api_client: ApiClient | None = None,
    force_new: bool = False,
) -> Message | None:
    if message.from_user is None:
        return None
    return await present_menu(
        message.bot,
        chat_id=message.chat.id,
        telegram_id=message.from_user.id,
        locale=message.from_user.language_code,
        screen=screen,
        screen_params=screen_params,
        referral_code=referral_code,
        api_client=api_client,
        force_new=force_new,
    )


async def refresh_menu_for_telegram_user(
    bot: Bot,
    *,
    telegram_id: int,
    locale: str | None,
    screen: str | None = None,
    screen_params: dict[str, str] | None = None,
    api_client: ApiClient | None = None,
) -> Message | None:
    session_store = get_menu_session_store()
    session = await session_store.get(telegram_id)
    if session is None:
        return None

    return await present_menu(
        bot,
        chat_id=session.chat_id,
        telegram_id=telegram_id,
        locale=locale,
        screen=screen or session.screen,
        screen_params=screen_params or session.screen_params,
        referral_code=session.referral_code,
        api_client=api_client,
    )


async def activate_trial_and_render(
    bot: Bot,
    *,
    chat_id: int,
    telegram_id: int,
    locale: str | None,
    referral_code: str | None,
    api_client: ApiClient | None = None,
) -> tuple[Message | None, str | None]:
    client = api_client or ApiClient()
    try:
        await client.activate_bot_trial(telegram_id=telegram_id)
    except httpx.HTTPStatusError as exc:
        return None, _extract_http_error_detail(exc, locale=locale)
    return (
        await present_menu(
            bot,
            chat_id=chat_id,
            telegram_id=telegram_id,
            locale=locale,
            screen=SCREEN_SUBSCRIPTION,
            referral_code=referral_code,
            api_client=client,
        ),
        None,
    )


async def create_plan_payment_and_render(
    bot: Bot,
    *,
    chat_id: int,
    telegram_id: int,
    locale: str | None,
    referral_code: str | None,
    provider: str,
    plan_code: str,
    api_client: ApiClient | None = None,
) -> tuple[Message | None, str | None]:
    client = api_client or ApiClient()
    try:
        idempotency_key = _build_bot_payment_idempotency_key(
            provider=provider,
            telegram_id=telegram_id,
        )
        if provider == "telegram_stars":
            payment = await client.create_bot_telegram_stars_payment(
                telegram_id=telegram_id,
                plan_code=plan_code,
                idempotency_key=idempotency_key,
            )
        else:
            payment = await client.create_bot_yookassa_payment(
                telegram_id=telegram_id,
                plan_code=plan_code,
                idempotency_key=idempotency_key,
            )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code >= 500:
            return None, translate("bot.menu.messages.payment_failed", locale=locale)
        return None, _extract_http_error_detail(exc, locale=locale)

    payment_data = _safe_dict(payment)
    payment_url = _safe_string(payment_data.get("confirmation_url"), fallback="")
    if not payment_url:
        return None, translate("bot.menu.messages.payment_failed", locale=locale)

    plans = await _get_plans_payload(client)
    selected_plan = next(
        (
            plan
            for plan in plans
            if _safe_string(plan.get("code"), fallback="") == plan_code
        ),
        None,
    )
    plan_name = _safe_string(
        payment_data.get("plan_code"),
        fallback=plan_code,
    )
    if selected_plan is not None:
        plan_name = _safe_string(selected_plan.get("name"), fallback=plan_name)

    return (
        await present_menu(
            bot,
            chat_id=chat_id,
            telegram_id=telegram_id,
            locale=locale,
            screen=SCREEN_PAYMENT_READY,
            screen_params={
                "plan_code": plan_code,
                "plan_name": plan_name,
                "provider": _safe_string(
                    payment_data.get("provider"), fallback=provider
                ),
                "amount": str(payment_data.get("amount") or ""),
                "currency": _safe_string(payment_data.get("currency"), fallback=""),
                "payment_url": payment_url,
            },
            referral_code=referral_code,
            api_client=client,
        ),
        None,
    )
