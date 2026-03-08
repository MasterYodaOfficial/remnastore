from pydantic import BaseModel, Field

from app.schemas.account import AccountResponse


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(..., description="Telegram WebApp initData string")


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    account: AccountResponse

