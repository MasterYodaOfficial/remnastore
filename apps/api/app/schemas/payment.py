from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.payments import PaymentFlowType, PaymentProvider, PaymentStatus


class CreateYooKassaTopupRequest(BaseModel):
    amount_rub: int = Field(gt=0)
    success_url: str | None = None
    cancel_url: str | None = None
    description: str | None = None
    idempotency_key: str | None = None


class CreateYooKassaPlanPurchaseRequest(BaseModel):
    success_url: str | None = None
    cancel_url: str | None = None
    description: str | None = None
    idempotency_key: str | None = None
    promo_code: str | None = None


class CreateTelegramStarsPlanPurchaseRequest(BaseModel):
    description: str | None = None
    idempotency_key: str | None = None
    promo_code: str | None = None


class SubscriptionPlanResponse(BaseModel):
    code: str
    name: str
    price_rub: int
    price_stars: int | None = None
    duration_days: int
    features: list[str]
    popular: bool = False


class PaymentIntentResponse(BaseModel):
    provider: PaymentProvider
    flow_type: PaymentFlowType
    account_id: UUID
    status: PaymentStatus
    amount: int
    currency: str
    provider_payment_id: str
    external_reference: str | None = None
    confirmation_url: str | None = None
    expires_at: datetime | None = None
    raw_payload: dict | None = None


class PaymentStatusResponse(BaseModel):
    provider: PaymentProvider
    flow_type: PaymentFlowType
    status: PaymentStatus
    amount: int
    currency: str
    provider_payment_id: str
    confirmation_url: str | None = None
    expires_at: datetime | None = None
    finalized_at: datetime | None = None


class PaymentListItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: PaymentProvider
    flow_type: PaymentFlowType
    status: PaymentStatus
    amount: int
    currency: str
    provider_payment_id: str
    plan_code: str | None = None
    description: str | None = None
    confirmation_url: str | None = None
    expires_at: datetime | None = None
    finalized_at: datetime | None = None
    created_at: datetime


class PaymentListResponse(BaseModel):
    items: list[PaymentListItemResponse]
    total: int
    limit: int
    offset: int


class TelegramStarsPreCheckoutRequest(BaseModel):
    telegram_id: int
    invoice_payload: str
    total_amount: int = Field(gt=0)
    currency: str
    pre_checkout_query_id: str


class TelegramStarsPreCheckoutResponse(BaseModel):
    ok: bool
    error_message: str | None = None


class PaymentWebhookProcessResponse(BaseModel):
    ok: bool = True
    payment_id: int
    provider_payment_id: str
    status: PaymentStatus
    duplicate: bool = False
    ledger_applied: bool = False
    subscription_applied: bool = False
