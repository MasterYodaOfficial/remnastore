from __future__ import annotations

import httpx
from aiogram import F, Bot, Router
from aiogram.types import Message, PreCheckoutQuery

from bot.core.config import settings
from bot.services.i18n import translate, translate_html
from bot.services.menu_renderer import (
    build_browser_link_markup,
    refresh_menu_for_telegram_user,
)

router = Router()


def build_api_headers() -> dict[str, str]:
    token = settings.api_token.strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


async def _post_api(path: str, payload: dict, *, timeout: float) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(
            f"{settings.api_url}{path}",
            json=payload,
            headers=build_api_headers(),
        )


@router.pre_checkout_query()
async def handle_pre_checkout_query(
    pre_checkout_query: PreCheckoutQuery, bot: Bot
) -> None:
    locale = (
        pre_checkout_query.from_user.language_code
        if pre_checkout_query.from_user
        else None
    )
    if pre_checkout_query.currency != "XTR":
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message=translate(
                "bot.payments.pre_checkout_unsupported_currency",
                locale=locale,
            ),
        )
        return

    try:
        response = await _post_api(
            "/api/v1/webhooks/payments/telegram-stars/pre-checkout",
            {
                "telegram_id": pre_checkout_query.from_user.id,
                "invoice_payload": pre_checkout_query.invoice_payload,
                "total_amount": pre_checkout_query.total_amount,
                "currency": pre_checkout_query.currency,
                "pre_checkout_query_id": pre_checkout_query.id,
            },
            timeout=5.0,
        )
    except httpx.HTTPError:
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message=translate(
                "bot.payments.pre_checkout_service_unavailable",
                locale=locale,
            ),
        )
        return

    if response.status_code != 200:
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message=translate(
                "bot.payments.pre_checkout_confirmation_failed",
                locale=locale,
            ),
        )
        return

    payload = response.json()
    ok = bool(payload.get("ok"))
    error_message = payload.get("error_message")
    await bot.answer_pre_checkout_query(
        pre_checkout_query.id,
        ok=ok,
        error_message=error_message or None,
    )


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    if payment is None:
        return

    response = await _post_api(
        "/api/v1/webhooks/payments/telegram-stars",
        {
            "event_type": "successful_payment",
            "telegram_id": message.from_user.id if message.from_user else None,
            "currency": payment.currency,
            "total_amount": payment.total_amount,
            "invoice_payload": payment.invoice_payload,
            "telegram_payment_charge_id": payment.telegram_payment_charge_id,
            "provider_payment_charge_id": payment.provider_payment_charge_id,
        },
        timeout=10.0,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Telegram Stars payment finalization failed: {response.status_code} {response.text}"
        )

    locale = message.from_user.language_code if message.from_user is not None else None
    success_reply_markup = build_browser_link_markup(locale=locale)
    await message.answer(
        translate_html("bot.payments.subscription_updated", locale=locale),
        message_effect_id=settings.telegram_purchase_message_effect_id.strip() or None,
        reply_markup=success_reply_markup,
    )
    if message.from_user is not None:
        await refresh_menu_for_telegram_user(
            message.bot,
            telegram_id=message.from_user.id,
            locale=locale,
            screen="subscription",
        )
