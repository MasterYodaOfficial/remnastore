from datetime import datetime, timezone
from math import ceil
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.db.models import Account


class TrialEligibilityResponse(BaseModel):
    eligible: bool
    reason: Optional[str] = None
    has_used_trial: bool = False
    subscription_status: Optional[str] = None
    subscription_expires_at: Optional[datetime] = None
    remnawave_user_uuid: Optional[UUID] = None


class SubscriptionStateResponse(BaseModel):
    remnawave_user_uuid: Optional[UUID] = None
    subscription_url: Optional[str] = None
    status: Optional[str] = None
    expires_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    is_active: bool = False
    is_trial: bool = False
    has_used_trial: bool = False
    trial_used_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    days_left: Optional[int] = None

    @classmethod
    def from_account(cls, account: Account) -> "SubscriptionStateResponse":
        now = datetime.now(timezone.utc)
        expires_at = account.subscription_expires_at
        is_active = False
        days_left: Optional[int] = None

        if expires_at is not None:
            comparable_expires_at = expires_at
            if comparable_expires_at.tzinfo is None:
                comparable_expires_at = comparable_expires_at.replace(tzinfo=timezone.utc)

            delta_seconds = (comparable_expires_at - now).total_seconds()
            if delta_seconds > 0 and account.subscription_status == "ACTIVE":
                is_active = True
                days_left = max(1, ceil(delta_seconds / 86400))

        return cls(
            remnawave_user_uuid=account.remnawave_user_uuid,
            subscription_url=account.subscription_url,
            status=account.subscription_status,
            expires_at=account.subscription_expires_at,
            last_synced_at=account.subscription_last_synced_at,
            is_active=is_active,
            is_trial=account.subscription_is_trial,
            has_used_trial=account.has_used_trial,
            trial_used_at=account.trial_used_at,
            trial_ends_at=account.trial_ends_at,
            days_left=days_left,
        )
