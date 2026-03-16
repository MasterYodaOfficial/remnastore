from aiogram.fsm.state import State, StatesGroup


class MenuState(StatesGroup):
    idle = State()
