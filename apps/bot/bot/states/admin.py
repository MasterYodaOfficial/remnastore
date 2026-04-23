from aiogram.fsm.state import State, StatesGroup


class AdminState(StatesGroup):
    awaiting_broadcast_message = State()
    broadcast_draft_ready = State()
