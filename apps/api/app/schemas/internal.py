from pydantic import BaseModel

from app.db.models import AccountStatus


class TelegramAccountAccessResponse(BaseModel):
    telegram_id: int
    exists: bool
    status: AccountStatus | None = None
    fully_blocked: bool
