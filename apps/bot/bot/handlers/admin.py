from __future__ import annotations

import httpx

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.core.config import settings
from bot.keyboards.admin import (
    admin_broadcast_draft_keyboard,
    admin_menu_keyboard,
    admin_section_keyboard,
)
from bot.services.api import ApiClient
from bot.services.i18n import translate, translate_html
from bot.states.admin import AdminState

router = Router()
ADMIN_CALLBACK_PREFIX = "admin:"
DRAFT_PREVIEW_LIMIT = 180


def _is_admin_user(user_id: int | None) -> bool:
    return user_id is not None and user_id in settings.bot_admin_id_list


def _draft_preview_text(message: Message) -> str:
    raw_text = (message.text or message.caption or "").strip()
    if not raw_text:
        return ""
    normalized = " ".join(raw_text.split())
    if len(normalized) <= DRAFT_PREVIEW_LIMIT:
        return normalized
    return normalized[: DRAFT_PREVIEW_LIMIT - 3].rstrip() + "..."


def _message_kind(message: Message) -> str:
    if message.media_group_id:
        return "media_group"
    if message.text:
        return "text"
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.animation:
        return "animation"
    if message.document:
        return "document"
    if message.audio:
        return "audio"
    if message.voice:
        return "voice"
    if message.video_note:
        return "video_note"
    if message.sticker:
        return "sticker"
    if message.poll:
        return "poll"
    if message.contact:
        return "contact"
    if message.location:
        return "location"
    if message.venue:
        return "venue"
    return "unknown"


def _localized_message_kind(message: Message, *, locale: str | None) -> str:
    kind = _message_kind(message)
    return translate(f"bot.admin.broadcast.content_types.{kind}", locale=locale)


def _format_source_message_ids(message_ids: list[int]) -> str:
    if not message_ids:
        return "—"
    if len(message_ids) <= 6:
        return ", ".join(str(item) for item in message_ids)
    preview_ids = ", ".join(str(item) for item in message_ids[:6])
    return f"{preview_ids}..."


def _merge_source_message_ids(
    existing_ids: list[int] | None, *, message_id: int
) -> list[int]:
    merged_ids = list(existing_ids or [])
    if message_id not in merged_ids:
        merged_ids.append(message_id)
    merged_ids.sort()
    return merged_ids


def _build_api_broadcast_payload(
    message: Message,
    *,
    locale: str | None,
    current_draft: dict[str, object] | None,
) -> tuple[dict[str, object] | None, str | None]:
    message_kind = _message_kind(message)
    if message_kind == "unknown":
        return None, translate(
            "bot.admin.broadcast.unsupported_type",
            locale=locale,
            content_type=translate(
                f"bot.admin.broadcast.content_types.{message_kind}", locale=locale
            ),
        )
    source_message_ids = [message.message_id]
    media_group_id = str(message.media_group_id) if message.media_group_id else None
    if (
        media_group_id
        and current_draft is not None
        and current_draft.get("media_group_id") == media_group_id
        and current_draft.get("source_chat_id") == message.chat.id
    ):
        existing_ids = current_draft.get("source_message_ids")
        if isinstance(existing_ids, list):
            source_message_ids = _merge_source_message_ids(
                [int(item) for item in existing_ids],
                message_id=message.message_id,
            )
    return {
        "source_chat_id": message.chat.id,
        "source_message_ids": source_message_ids,
        "media_group_id": media_group_id,
    }, None


async def _get_broadcast_draft_payload(state: FSMContext) -> dict[str, object] | None:
    data = await state.get_data()
    if not isinstance(data, dict):
        return None
    draft = data.get("admin_broadcast_draft")
    if not isinstance(draft, dict):
        return None
    api_payload = draft.get("api_payload")
    return api_payload if isinstance(api_payload, dict) else None


def _format_status_screen(payload: dict, *, locale: str | None) -> str:
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return translate_html("bot.admin.status.empty", locale=locale)

    lines = [translate_html("bot.admin.status.caption", locale=locale), ""]
    for item in items:
        if not isinstance(item, dict):
            continue
        lines.append(
            translate_html(
                "bot.admin.status.item",
                locale=locale,
                broadcast_id=item.get("broadcast_id", "—"),
                content_type=translate(
                    f"bot.admin.broadcast.content_types.{item.get('content_type', 'unknown')}",
                    locale=locale,
                ),
                status=item.get("status", "—"),
                latest_run_status=item.get("latest_run_status") or "—",
                estimated_telegram_recipients=item.get(
                    "estimated_telegram_recipients", 0
                ),
                pending_deliveries=item.get("pending_deliveries", 0),
                delivered_deliveries=item.get("delivered_deliveries", 0),
                failed_deliveries=item.get("failed_deliveries", 0),
                skipped_deliveries=item.get("skipped_deliveries", 0),
            )
        )
        lines.append("")
    return "\n".join(lines).rstrip()


def _format_stats_screen(payload: dict, *, locale: str | None) -> str:
    return translate_html(
        "bot.admin.stats.summary",
        locale=locale,
        total_accounts=payload.get("total_accounts", 0),
        active_subscriptions=payload.get("active_subscriptions", 0),
        accounts_with_telegram=payload.get("accounts_with_telegram", 0),
        paying_accounts_last_30d=payload.get("paying_accounts_last_30d", 0),
        blocked_accounts=payload.get("blocked_accounts", 0),
        new_accounts_last_7d=payload.get("new_accounts_last_7d", 0),
        pending_payments=payload.get("pending_payments", 0),
        pending_withdrawals=payload.get("pending_withdrawals", 0),
        successful_payments_amount_rub_last_30d=payload.get(
            "successful_payments_amount_rub_last_30d", 0
        ),
        successful_payments_rub_last_30d=payload.get(
            "successful_payments_rub_last_30d", 0
        ),
        direct_plan_revenue_rub_last_30d=payload.get(
            "direct_plan_revenue_rub_last_30d", 0
        ),
        direct_plan_purchases_rub_last_30d=payload.get(
            "direct_plan_purchases_rub_last_30d", 0
        ),
        direct_plan_revenue_stars_last_30d=payload.get(
            "direct_plan_revenue_stars_last_30d", 0
        ),
        direct_plan_purchases_stars_last_30d=payload.get(
            "direct_plan_purchases_stars_last_30d", 0
        ),
        total_wallet_balance=payload.get("total_wallet_balance", 0),
        total_referral_earnings=payload.get("total_referral_earnings", 0),
    )


async def _answer_callback(
    callback: CallbackQuery,
    *,
    text: str | None = None,
) -> None:
    if text is None:
        await callback.answer()
        return
    await callback.answer(text)


async def _render_admin_menu(target: Message, *, locale: str | None) -> None:
    await target.answer(
        translate_html("bot.admin.menu.caption", locale=locale),
        reply_markup=admin_menu_keyboard(locale=locale),
    )


async def _edit_admin_screen(
    callback: CallbackQuery,
    *,
    locale: str | None,
    text_key: str,
    reply_markup,
) -> None:
    if callback.message is None:
        return
    await callback.message.edit_text(
        translate_html(text_key, locale=locale),
        reply_markup=reply_markup,
    )


@router.message(Command("master"))
async def master_handler(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _is_admin_user(message.from_user.id):
        return

    await state.clear()
    await _render_admin_menu(message, locale=message.from_user.language_code)


@router.callback_query(F.data.startswith(ADMIN_CALLBACK_PREFIX))
async def admin_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    locale = callback.from_user.language_code if callback.from_user else None
    if callback.from_user is None or not _is_admin_user(callback.from_user.id):
        await _answer_callback(callback)
        return

    action = callback.data.removeprefix(ADMIN_CALLBACK_PREFIX)

    if action == "menu":
        await state.clear()
        await _edit_admin_screen(
            callback,
            locale=locale,
            text_key="bot.admin.menu.caption",
            reply_markup=admin_menu_keyboard(locale=locale),
        )
        await _answer_callback(callback)
        return

    if action == "broadcast":
        await state.set_state(AdminState.awaiting_broadcast_message)
        await _edit_admin_screen(
            callback,
            locale=locale,
            text_key="bot.admin.broadcast.prompt",
            reply_markup=admin_section_keyboard(locale=locale),
        )
        await _answer_callback(callback)
        return

    if action == "status":
        await state.clear()
        try:
            payload = await ApiClient().get_bot_admin_broadcast_statuses(
                admin_telegram_id=callback.from_user.id
            )
        except httpx.HTTPError:
            await _answer_callback(
                callback,
                text=translate("bot.admin.errors.backend_unavailable", locale=locale),
            )
            return

        if callback.message is not None:
            await callback.message.edit_text(
                _format_status_screen(payload, locale=locale),
                reply_markup=admin_section_keyboard(locale=locale),
            )
        await _answer_callback(callback)
        return

    if action == "stats":
        await state.clear()
        try:
            payload = await ApiClient().get_bot_admin_stats_summary(
                admin_telegram_id=callback.from_user.id
            )
        except httpx.HTTPError:
            await _answer_callback(
                callback,
                text=translate("bot.admin.errors.backend_unavailable", locale=locale),
            )
            return

        if callback.message is not None:
            await callback.message.edit_text(
                _format_stats_screen(payload, locale=locale),
                reply_markup=admin_section_keyboard(locale=locale),
            )
        await _answer_callback(callback)
        return

    if action == "broadcast_test":
        draft_payload = await _get_broadcast_draft_payload(state)
        if draft_payload is None:
            await _answer_callback(
                callback,
                text=translate("bot.admin.broadcast.draft_missing", locale=locale),
            )
            return
        try:
            payload = await ApiClient().test_bot_admin_broadcast(
                admin_telegram_id=callback.from_user.id,
                source_chat_id=int(draft_payload["source_chat_id"]),
                source_message_ids=[
                    int(item)
                    for item in list(draft_payload.get("source_message_ids") or [])
                ],
                media_group_id=(
                    str(draft_payload["media_group_id"])
                    if draft_payload.get("media_group_id") is not None
                    else None
                ),
            )
        except httpx.HTTPError:
            await _answer_callback(
                callback,
                text=translate("bot.admin.errors.backend_unavailable", locale=locale),
            )
            return

        if callback.message is not None:
            await callback.message.answer(
                translate_html(
                    "bot.admin.broadcast.test_success",
                    locale=locale,
                    content_type=translate(
                        f"bot.admin.broadcast.content_types.{payload.get('content_type', 'unknown')}",
                        locale=locale,
                    ),
                    copied_messages_count=len(payload.get("telegram_message_ids", [])),
                    telegram_message_ids=", ".join(
                        payload.get("telegram_message_ids", [])
                    )
                    or "—",
                )
            )
        await _answer_callback(callback)
        return

    if action == "broadcast_send":
        draft_payload = await _get_broadcast_draft_payload(state)
        if draft_payload is None:
            await _answer_callback(
                callback,
                text=translate("bot.admin.broadcast.draft_missing", locale=locale),
            )
            return
        try:
            payload = await ApiClient().send_now_bot_admin_broadcast(
                admin_telegram_id=callback.from_user.id,
                source_chat_id=int(draft_payload["source_chat_id"]),
                source_message_ids=[
                    int(item)
                    for item in list(draft_payload.get("source_message_ids") or [])
                ],
                media_group_id=(
                    str(draft_payload["media_group_id"])
                    if draft_payload.get("media_group_id") is not None
                    else None
                ),
            )
        except httpx.HTTPError:
            await _answer_callback(
                callback,
                text=translate("bot.admin.errors.backend_unavailable", locale=locale),
            )
            return

        await state.clear()
        if callback.message is not None:
            await callback.message.answer(
                translate_html(
                    "bot.admin.broadcast.send_now_success",
                    locale=locale,
                    broadcast_id=payload.get("broadcast_id", "—"),
                    estimated_telegram_recipients=payload.get(
                        "estimated_telegram_recipients", 0
                    ),
                    pending_deliveries=payload.get("pending_deliveries", 0),
                    delivered_deliveries=payload.get("delivered_deliveries", 0),
                    failed_deliveries=payload.get("failed_deliveries", 0),
                    skipped_deliveries=payload.get("skipped_deliveries", 0),
                    status=payload.get("status", "—"),
                    latest_run_status=payload.get("latest_run_status") or "—",
                ),
                reply_markup=admin_menu_keyboard(locale=locale),
            )
        await _answer_callback(callback)
        return

    if action == "close":
        await state.clear()
        if callback.message is not None:
            await callback.message.edit_text(
                translate_html("bot.admin.menu.closed", locale=locale),
            )
        await _answer_callback(callback)
        return

    await _answer_callback(callback)


@router.message(
    StateFilter(AdminState.awaiting_broadcast_message, AdminState.broadcast_draft_ready)
)
async def admin_broadcast_draft_handler(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _is_admin_user(message.from_user.id):
        return

    locale = message.from_user.language_code
    data = await state.get_data()
    if not isinstance(data, dict):
        data = {}
    current_draft = (
        data.get("admin_broadcast_draft")
        if isinstance(data.get("admin_broadcast_draft"), dict)
        else None
    )
    preview = _draft_preview_text(message)
    normalized_media_group_id = (
        str(message.media_group_id) if message.media_group_id is not None else None
    )
    api_payload, unsupported_reason = _build_api_broadcast_payload(
        message,
        locale=locale,
        current_draft=current_draft,
    )
    source_message_ids = (
        [int(item) for item in list(api_payload.get("source_message_ids") or [])]
        if api_payload is not None
        else [message.message_id]
    )
    media_group_line = ""
    if normalized_media_group_id is not None:
        media_group_line = translate(
            "bot.admin.broadcast.media_group_line",
            locale=locale,
            media_group_id=normalized_media_group_id,
            messages_count=len(source_message_ids),
        )
    preview_line = ""
    if preview:
        preview_line = translate(
            "bot.admin.broadcast.preview_line",
            locale=locale,
            preview=preview,
        )

    await state.update_data(
        admin_broadcast_draft={
            "source_chat_id": message.chat.id,
            "source_message_ids": source_message_ids,
            "content_type": _message_kind(message),
            "media_group_id": normalized_media_group_id,
            "preview": preview,
            "caption": bool(message.caption),
            "api_payload": api_payload,
            "unsupported_reason": unsupported_reason,
        }
    )
    await state.set_state(AdminState.broadcast_draft_ready)
    await message.answer(
        translate_html(
            "bot.admin.broadcast.draft_saved",
            locale=locale,
            content_type=_localized_message_kind(message, locale=locale),
            source_chat_id=message.chat.id,
            source_message_id=_format_source_message_ids(source_message_ids),
            media_group_line=media_group_line,
            preview_line=preview_line,
            unsupported_line=(
                translate(
                    "bot.admin.broadcast.unsupported_line",
                    locale=locale,
                    reason=unsupported_reason,
                )
                if unsupported_reason
                else ""
            ),
        ),
        reply_markup=admin_broadcast_draft_keyboard(
            locale=locale, can_send=api_payload is not None
        ),
    )
