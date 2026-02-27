from aiogram.fsm.state import State, StatesGroup


class OrderState(StatesGroup):
    plan = State()
    payment = State()
