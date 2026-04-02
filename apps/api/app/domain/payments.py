from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Mapping, Protocol
from uuid import UUID


class PaymentProvider(StrEnum):
    YOOKASSA = "yookassa"
    TELEGRAM_STARS = "telegram_stars"


class PaymentFlowType(StrEnum):
    WALLET_TOPUP = "wallet_topup"
    DIRECT_PLAN_PURCHASE = "direct_plan_purchase"


class PaymentStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"
    REQUIRES_ACTION = "requires_action"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(slots=True)
class CreatePaymentIntentCommand:
    account_id: UUID
    flow_type: PaymentFlowType
    amount: int
    currency: str = "RUB"
    plan_code: str | None = None
    success_url: str | None = None
    cancel_url: str | None = None
    description: str | None = None
    idempotency_key: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class PaymentIntentSnapshot:
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


@dataclass(slots=True)
class PaymentWebhookEvent:
    provider: PaymentProvider
    provider_event_id: str
    provider_payment_id: str
    status: PaymentStatus
    amount: int
    currency: str
    flow_type: PaymentFlowType
    account_id: UUID
    external_reference: str | None = None
    raw_payload: dict | None = None


class PaymentGatewayError(Exception):
    default_code: str | None = None

    def __init__(self, detail: str, *, code: str | None = None) -> None:
        super().__init__(detail)
        self.code = code or self.default_code


class PaymentGatewaySignatureError(PaymentGatewayError):
    pass


class PaymentGatewayConfigurationError(PaymentGatewayError):
    pass


class PaymentGateway(Protocol):
    provider: PaymentProvider

    async def create_payment_intent(
        self,
        command: CreatePaymentIntentCommand,
    ) -> PaymentIntentSnapshot:
        raise NotImplementedError

    async def parse_webhook(
        self,
        *,
        raw_body: bytes,
        headers: Mapping[str, str],
    ) -> PaymentWebhookEvent:
        raise NotImplementedError
