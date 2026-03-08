from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models import AccountStatus, LoginSource


class TelegramUpsertRequest(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_premium: bool = False
    locale: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    last_login_source: LoginSource = LoginSource.TELEGRAM_WEBAPP


class AccountResponse(BaseModel):
    id: UUID
    telegram_id: Optional[int] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_premium: bool = False
    locale: Optional[str] = None
    status: AccountStatus
    remnawave_user_uuid: Optional[UUID] = None
    subscription_url: Optional[str] = None
    last_login_source: Optional[LoginSource] = None
    last_seen_at: Optional[datetime] = None
    balance: int = 0
    referral_code: Optional[str] = None
    referral_earnings_cents: int = 0
    referrals_count: int = 0
    referral_reward_rate: float = 0
    referred_by_account_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LinkTelegramResponse(BaseModel):
    """Response for generating Telegram linking URL."""
    link_url: str = Field(..., description="URL to open in Telegram to link account")
    link_token: str = Field(..., description="Token for reference")
    expires_in_seconds: int = Field(..., description="Link expiration time in seconds")


class LinkBrowserResponse(BaseModel):
    """Response for generating browser linking URL."""
    link_url: str = Field(..., description="URL to open in browser to link account")
    link_token: str = Field(..., description="Token for reference")
    expires_in_seconds: int = Field(..., description="Link expiration time in seconds")
