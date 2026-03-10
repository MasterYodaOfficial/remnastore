from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.payments import PaymentFlowType, PaymentProvider, PaymentStatus


class CreateYooKassaTopupRequest(BaseModel):
    amount_rub: int = Field(gt=0)
    success_url: str | None = None
    cancel_url: str | None = None
    description: str | None = None
    idempotency_key: str | None = None


class PaymentIntentResponse(BaseModel):
    provider: PaymentProvider
    flow_type: PaymentFlowType
    account_id: UUID
    status: PaymentStatus
    amount_rub: int
    currency: str
    provider_payment_id: str
    external_reference: str | None = None
    confirmation_url: str | None = None
    expires_at: datetime | None = None
    raw_payload: dict | None = None


class PaymentWebhookProcessResponse(BaseModel):
    ok: bool = True
    payment_id: int
    provider_payment_id: str
    status: PaymentStatus
    duplicate: bool = False
    ledger_applied: bool = False
