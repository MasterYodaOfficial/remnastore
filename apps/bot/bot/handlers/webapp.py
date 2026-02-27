from aiogram import Router
from aiogram.types import Message

router = Router()


@router.message()
async def any_message(message: Message) -> None:
    await message.answer("Для покупки используйте WebApp.")
