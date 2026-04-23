from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.i18n import translate


def admin_menu_keyboard(*, locale: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("bot.admin.buttons.broadcast", locale=locale),
                    callback_data="admin:broadcast",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate("bot.admin.buttons.status", locale=locale),
                    callback_data="admin:status",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate("bot.admin.buttons.stats", locale=locale),
                    callback_data="admin:stats",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate("bot.admin.buttons.close", locale=locale),
                    callback_data="admin:close",
                )
            ],
        ]
    )


def admin_section_keyboard(*, locale: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("bot.admin.buttons.back", locale=locale),
                    callback_data="admin:menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate("bot.admin.buttons.close", locale=locale),
                    callback_data="admin:close",
                )
            ],
        ]
    )


def admin_broadcast_draft_keyboard(
    *,
    locale: str | None = None,
    can_send: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_send:
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate("bot.admin.buttons.test_to_self", locale=locale),
                    callback_data="admin:broadcast_test",
                ),
                InlineKeyboardButton(
                    text=translate("bot.admin.buttons.send_now", locale=locale),
                    callback_data="admin:broadcast_send",
                ),
            ]
        )

    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=translate("bot.admin.buttons.new_draft", locale=locale),
                    callback_data="admin:broadcast",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate("bot.admin.buttons.back", locale=locale),
                    callback_data="admin:menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate("bot.admin.buttons.close", locale=locale),
                    callback_data="admin:close",
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
