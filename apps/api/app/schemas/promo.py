from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.db.models import PromoEffectType, PromoRedemptionStatus
from app.schemas.subscription import SubscriptionStateResponse


class PromoPlanQuoteRequest(BaseModel):
    promo_code: str = Field(..., min_length=1, max_length=64)
    currency: str = Field(default="RUB", min_length=1, max_length=8)

    @field_validator("promo_code", "currency")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()


class PromoPlanQuoteResponse(BaseModel):
    plan_code: str
    promo_code: str
    effect_type: PromoEffectType
    original_amount: int
    final_amount: int
    discount_amount: int
    currency: str
    original_duration_days: int
    final_duration_days: int


class PromoRedeemRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    idempotency_key: str = Field(..., min_length=1, max_length=255)

    @field_validator("code", "idempotency_key")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()


class PromoRedeemResponse(BaseModel):
    promo_code: str
    effect_type: PromoEffectType
    status: PromoRedemptionStatus
    balance: int
    balance_credit_amount: int | None = None
    granted_duration_days: int | None = None
    subscription: SubscriptionStateResponse
