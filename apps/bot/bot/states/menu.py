from aiogram.fsm.state import State, StatesGroup


class MenuState(StatesGroup):
    idle = State()
    awaiting_promo_code = State()
