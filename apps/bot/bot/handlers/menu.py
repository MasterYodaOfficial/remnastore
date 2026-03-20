from __future__ import annotations

import httpx

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.callbacks.menu import parse_menu_callback
from bot.core.config import settings
from bot.services.menu_renderer import (
    SCREEN_HELP,
    SCREEN_HOME,
    SCREEN_PLAN,
    SCREEN_PLANS,
    SCREEN_REFERRALS,
    SCREEN_SUBSCRIPTION,
    activate_trial_and_render,
    create_plan_payment_and_render,
    present_menu,
)
from bot.services.i18n import translate
from bot.services.session_store import get_menu_session_store
from bot.states.menu import MenuState

router = Router()
CALLBACK_ANSWER_TEXT_LIMIT = 200


def _normalize_callback_answer_text(text: str | None, *, locale: str | None) -> str:
    normalized = " ".join((text or "").split())
    if not normalized:
        return translate("bot.menu.messages.generic_error", locale=locale)
    if len(normalized) <= CALLBACK_ANSWER_TEXT_LIMIT:
        return normalized
    return normalized[: CALLBACK_ANSWER_TEXT_LIMIT - 3].rstrip() + "..."


def _normalize_promo_code(raw_value: str | None) -> str:
    return "".join((raw_value or "").strip().upper().split())


async def _answer_callback(
    callback: CallbackQuery,
    *,
    locale: str | None,
    text: str | None = None,
    show_alert: bool = False,
) -> None:
    if text is None:
        await callback.answer()
        return
    await callback.answer(
        _normalize_callback_answer_text(text, locale=locale),
        show_alert=show_alert,
    )


@router.callback_query(F.data.startswith("m1:"))
async def handle_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None or callback.message is None:
        await _answer_callback(callback, locale=None)
        return

    locale = callback.from_user.language_code
    session_store = get_menu_session_store()
    if not await session_store.try_acquire_lock(
        callback.from_user.id,
        ttl_seconds=settings.bot_callback_lock_ttl_seconds,
    ):
        await _answer_callback(
            callback,
            locale=locale,
            text=translate("bot.menu.messages.processing", locale=locale),
        )
        return

    try:
        parsed = parse_menu_callback(callback.data)
        if parsed is None:
            await _answer_callback(callback, locale=locale)
            return

        session = await session_store.get(callback.from_user.id)
        referral_code = session.referral_code if session is not None else None
        await state.set_state(MenuState.idle)

        if parsed.scope == "n" and parsed.action in {
            SCREEN_HOME,
            SCREEN_SUBSCRIPTION,
            SCREEN_PLANS,
            SCREEN_REFERRALS,
            SCREEN_HELP,
        }:
            await present_menu(
                callback.bot,
                chat_id=callback.message.chat.id,
                telegram_id=callback.from_user.id,
                locale=locale,
                screen=parsed.action,
                referral_code=referral_code,
            )
            await _answer_callback(callback, locale=locale)
            return

        if parsed.scope == "plan" and parsed.action == "open" and parsed.value:
            screen_params = {"plan_code": parsed.value}
            if (
                session is not None
                and session.screen_params.get("plan_code") == parsed.value
            ):
                promo_code = _normalize_promo_code(
                    session.screen_params.get("promo_code")
                )
                if promo_code:
                    screen_params["promo_code"] = promo_code
            await present_menu(
                callback.bot,
                chat_id=callback.message.chat.id,
                telegram_id=callback.from_user.id,
                locale=locale,
                screen=SCREEN_PLAN,
                screen_params=screen_params,
                referral_code=referral_code,
            )
            await _answer_callback(callback, locale=locale)
            return

        if parsed.scope == "promo" and parsed.action == "enter" and parsed.value:
            await state.set_state(MenuState.awaiting_promo_code)
            await state.update_data(plan_code=parsed.value)
            await _answer_callback(
                callback,
                locale=locale,
                text=translate("bot.menu.messages.enter_promo_code", locale=locale),
            )
            return

        if parsed.scope == "promo" and parsed.action == "clear" and parsed.value:
            await present_menu(
                callback.bot,
                chat_id=callback.message.chat.id,
                telegram_id=callback.from_user.id,
                locale=locale,
                screen=SCREEN_PLAN,
                screen_params={"plan_code": parsed.value},
                referral_code=referral_code,
            )
            await _answer_callback(
                callback,
                locale=locale,
                text=translate("bot.menu.messages.promo_cleared", locale=locale),
            )
            return

        if parsed.scope == "trial" and parsed.action == "activate":
            _, error_text = await activate_trial_and_render(
                callback.bot,
                chat_id=callback.message.chat.id,
                telegram_id=callback.from_user.id,
                locale=locale,
                referral_code=referral_code,
            )
            if error_text:
                await _answer_callback(
                    callback,
                    locale=locale,
                    text=error_text,
                    show_alert=True,
                )
            else:
                await _answer_callback(
                    callback,
                    locale=locale,
                    text=translate("bot.menu.messages.trial_activated", locale=locale),
                )
            return

        if (
            parsed.scope == "pay"
            and parsed.action in {"stars", "yookassa"}
            and parsed.value
        ):
            provider = "telegram_stars" if parsed.action == "stars" else "yookassa"
            _, error_text = await create_plan_payment_and_render(
                callback.bot,
                chat_id=callback.message.chat.id,
                telegram_id=callback.from_user.id,
                locale=locale,
                referral_code=referral_code,
                provider=provider,
                plan_code=parsed.value,
            )
            if error_text:
                await _answer_callback(
                    callback,
                    locale=locale,
                    text=error_text,
                    show_alert=True,
                )
            else:
                await _answer_callback(
                    callback,
                    locale=locale,
                    text=translate("bot.menu.messages.payment_ready", locale=locale),
                )
            return
        await _answer_callback(callback, locale=locale)
    except (httpx.HTTPError, RuntimeError):
        await _answer_callback(
            callback,
            locale=locale,
            text=translate("bot.menu.messages.generic_error", locale=locale),
            show_alert=True,
        )
    finally:
        await session_store.release_lock(callback.from_user.id)


@router.message(StateFilter(MenuState.awaiting_promo_code))
async def handle_plan_promo_code_message(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    promo_code = _normalize_promo_code(message.text)
    locale = message.from_user.language_code
    data = await state.get_data()
    plan_code = str(data.get("plan_code") or "")
    if not promo_code:
        await message.answer(
            translate("bot.menu.messages.enter_promo_code", locale=locale)
        )
        return

    await state.clear()
    session = await get_menu_session_store().get(message.from_user.id)
    await present_menu(
        message.bot,
        chat_id=message.chat.id,
        telegram_id=message.from_user.id,
        locale=locale,
        screen=SCREEN_PLAN,
        screen_params={
            "plan_code": plan_code,
            "promo_code": promo_code,
        },
        referral_code=session.referral_code if session is not None else None,
    )
