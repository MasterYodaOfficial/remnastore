from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReferralClaimRequest(BaseModel):
    referral_code: str


class ReferralClaimResponse(BaseModel):
    created: bool
    referred_by_account_id: UUID


class TelegramReferralIntentRequest(BaseModel):
    telegram_id: int
    referral_code: str


class TelegramReferralIntentResponse(BaseModel):
    ok: bool = True


class ReferralSummaryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    referred_account_id: UUID
    display_name: str
    created_at: datetime
    reward_amount: int
    status: str


class ReferralSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    referral_code: str
    referrals_count: int
    referral_earnings: int
    available_for_withdraw: int
    effective_reward_rate: float


ReferralFeedStatus = Literal["all", "active", "pending"]


class ReferralFeedResponse(BaseModel):
    items: list[ReferralSummaryItemResponse]
    total: int
    limit: int
    offset: int
    status_filter: ReferralFeedStatus
