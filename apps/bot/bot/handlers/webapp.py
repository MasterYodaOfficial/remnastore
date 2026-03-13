from aiogram import Router
from aiogram.types import Message

from bot.services.api import ApiClient

router = Router()


@router.message()
async def any_message(message: Message) -> None:
    if message.from_user is not None:
        if await ApiClient().is_telegram_account_fully_blocked(telegram_id=message.from_user.id):
            return
    await message.answer("Для покупки используйте WebApp.")
