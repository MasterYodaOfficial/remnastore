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
    subscription_status: Optional[str] = None
    subscription_expires_at: Optional[datetime] = None
    subscription_last_synced_at: Optional[datetime] = None
    subscription_is_trial: bool = False
    trial_used_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    has_used_trial: bool = False
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
        if hasattr(value, "trial_used_at") and not isinstance(value, dict):
            value = {
                "id": value.id,
                "telegram_id": value.telegram_id,
                "email": value.email,
                "display_name": value.display_name,
                "username": value.username,
                "first_name": value.first_name,
                "last_name": value.last_name,
                "is_premium": value.is_premium,
                "locale": value.locale,
                "status": value.status,
                "remnawave_user_uuid": value.remnawave_user_uuid,
                "subscription_url": value.subscription_url,
                "subscription_status": value.subscription_status,
                "subscription_expires_at": value.subscription_expires_at,
                "subscription_last_synced_at": value.subscription_last_synced_at,
                "subscription_is_trial": value.subscription_is_trial,
                "trial_used_at": value.trial_used_at,
                "trial_ends_at": value.trial_ends_at,
                "has_used_trial": bool(value.trial_used_at),
                "last_login_source": value.last_login_source,
                "last_seen_at": value.last_seen_at,
                "balance": value.balance,
                "referral_code": value.referral_code,
                "referral_earnings": value.referral_earnings,
                "referrals_count": value.referrals_count,
                "referral_reward_rate": value.referral_reward_rate,
                "referred_by_account_id": value.referred_by_account_id,
                "created_at": value.created_at,
                "updated_at": value.updated_at,
            }

        if isinstance(value, dict):
            if "referral_earnings" not in value:
                legacy_value = value.get("referral_earnings_cents")
                if legacy_value is not None:
                    value = dict(value)
                    value["referral_earnings"] = int(legacy_value) // 100

            if "has_used_trial" not in value:
                value = dict(value)
                value["has_used_trial"] = value.get("trial_used_at") is not None

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
