from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.services.api import ApiClient
from bot.services.menu_renderer import show_menu_for_message
from bot.states.menu import MenuState

router = Router()


@router.message()
async def any_message(message: Message, state: FSMContext) -> None:
    if message.from_user is not None:
        if await ApiClient().is_telegram_account_fully_blocked(telegram_id=message.from_user.id):
            return
    await state.set_state(MenuState.idle)
    await show_menu_for_message(message)
