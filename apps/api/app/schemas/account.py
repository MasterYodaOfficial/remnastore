from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    model_config = ConfigDict(from_attributes=True)

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
    referral_earnings: int = 0
    referrals_count: int = 0
    referral_reward_rate: float = 0
    referred_by_account_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_referral_earnings_field(cls, value: object) -> object:
        if isinstance(value, dict) and "referral_earnings" not in value:
            legacy_value = value.get("referral_earnings_cents")
            if legacy_value is not None:
                value = dict(value)
                value["referral_earnings"] = int(legacy_value) // 100
        return value


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
