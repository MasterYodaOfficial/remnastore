from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from bot.keyboards.main import main_menu
from bot.services.api import ApiClient

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    api = ApiClient()
    tg_user = message.from_user

    # try to upsert user in API
    try:
        await api.upsert_telegram_user(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            is_premium=bool(getattr(tg_user, "is_premium", False)),
            locale=tg_user.language_code,
            last_login_source="telegram_bot_start",
        )
    except Exception:
        # silent fail; we still want to respond to user
        pass

    try:
        await message.answer(
            "Добро пожаловать! Откройте витрину через кнопку ниже.",
            reply_markup=main_menu(),
        )
    except TelegramBadRequest:
        # Fallback: send without keyboard if URL/config is invalid (e.g., non-HTTPS).
        await message.answer("Добро пожаловать! Кнопка недоступна, проверьте конфигурацию WebApp URL.")
