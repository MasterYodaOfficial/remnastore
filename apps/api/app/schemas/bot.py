from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.payments import PaymentProvider
from app.schemas.payment import SubscriptionPlanResponse
from app.schemas.subscription import SubscriptionStateResponse, TrialEligibilityResponse


class BotDashboardAccountSummary(BaseModel):
    telegram_id: int
    display_name: str | None = None
    locale: str | None = None
    balance: int = 0


class BotDashboardReferralSummary(BaseModel):
    referral_code: str = ""
    referrals_count: int = 0
    referral_earnings: int = 0
    available_for_withdraw: int = 0
    effective_reward_rate: float = 0.0


class BotDashboardResponse(BaseModel):
    telegram_id: int
    exists: bool
    account: BotDashboardAccountSummary | None = None
    subscription: SubscriptionStateResponse | None = None
    trial_eligibility: TrialEligibilityResponse | None = None
    referral: BotDashboardReferralSummary | None = None


class BotPlanListResponse(BaseModel):
    items: list[SubscriptionPlanResponse]


class BotPlanActionRequest(BaseModel):
    telegram_id: int
    idempotency_key: str | None = Field(default=None, min_length=1)


class BotPlanPaymentResponse(BaseModel):
    provider: PaymentProvider
    plan_code: str
    provider_payment_id: str
    confirmation_url: str
    amount: int
    currency: str
    created_at: datetime
