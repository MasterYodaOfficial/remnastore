from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from bot.keyboards.main import main_menu

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    try:
        await message.answer(
            "Добро пожаловать! Откройте витрину через кнопку ниже.",
            reply_markup=main_menu(),
        )
    except TelegramBadRequest:
        # Fallback: send without keyboard if URL/config is invalid (e.g., non-HTTPS).
        await message.answer("Добро пожаловать! Кнопка недоступна, проверьте конфигурацию WebApp URL.")
