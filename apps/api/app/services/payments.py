from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from typing import Mapping
from uuid import UUID
from uuid import uuid4

import requests
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from yookassa import Configuration as YooKassaConfiguration
from yookassa import Payment as YooKassaPayment
from yookassa.configuration import ConfigurationError as YooKassaConfigurationError
from yookassa.domain.exceptions import ApiError as YooKassaApiError
from yookassa.domain.notification.webhook_notification import WebhookNotification

from app.core.config import settings
from app.db.models import Account, LedgerEntryType, Payment, PaymentEvent
from app.domain.payments import (
    CreatePaymentIntentCommand,
    PaymentFlowType,
    PaymentGateway,
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
    PaymentGatewaySignatureError,
    PaymentIntentSnapshot,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookEvent,
)
from app.services.ledger import apply_credit_in_transaction, clear_account_cache


def _parse_iso_datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise PaymentGatewayError(f"Unsupported datetime payload: {value!r}")


def _require_whole_rubles(raw_value: object, *, currency: str) -> int:
    if not isinstance(currency, str) or not currency:
        raise PaymentGatewayError("Payment currency is missing")

    try:
        decimal_value = Decimal(str(raw_value))
    except (InvalidOperation, TypeError) as exc:
        raise PaymentGatewayError(f"Invalid payment amount: {raw_value!r}") from exc

    if decimal_value != decimal_value.quantize(Decimal("1.00")):
        raise PaymentGatewayError(
            f"Fractional amounts are not supported by current money contract: {raw_value!r} {currency}"
        )

    return int(decimal_value)


def _format_rub_amount(amount_rub: int) -> str:
    if amount_rub <= 0:
        raise PaymentGatewayError("Payment amount must be positive")
    return f"{amount_rub}.00"


def _map_yookassa_status(raw_status: str) -> PaymentStatus:
    status_map = {
        "pending": PaymentStatus.PENDING,
        "waiting_for_capture": PaymentStatus.REQUIRES_ACTION,
        "succeeded": PaymentStatus.SUCCEEDED,
        "canceled": PaymentStatus.CANCELLED,
    }
    try:
        return status_map[raw_status]
    except KeyError as exc:
        raise PaymentGatewayError(f"Unsupported YooKassa status: {raw_status!r}") from exc


def _extract_confirmation_url(response: object) -> str | None:
    confirmation = getattr(response, "confirmation", None)
    if confirmation is None:
        return None
    return getattr(confirmation, "confirmation_url", None)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class YooKassaGateway:
    provider = PaymentProvider.YOOKASSA

    def __init__(
        self,
        *,
        shop_id: str,
        secret_key: str,
        api_url: str = "https://api.yookassa.ru/v3",
        verify_tls: bool = True,
    ) -> None:
        self._shop_id = shop_id
        self._secret_key = secret_key
        self._api_url = api_url
        self._verify_tls = verify_tls

    def _assert_configured(self) -> None:
        if not self._shop_id or not self._secret_key:
            raise PaymentGatewayConfigurationError("YooKassa credentials are not configured")

    def _configure_sdk(self) -> None:
        self._assert_configured()
        YooKassaConfiguration.configure(
            self._shop_id,
            self._secret_key,
            api_url=self._api_url,
            verify=self._verify_tls,
        )

    def _build_metadata(self, command: CreatePaymentIntentCommand) -> dict[str, str]:
        metadata = dict(command.metadata)
        metadata["rm_account_id"] = str(command.account_id)
        metadata["rm_flow_type"] = command.flow_type.value
        if command.plan_code:
            metadata["rm_plan_code"] = command.plan_code
        if command.idempotency_key:
            metadata["rm_external_reference"] = command.idempotency_key
        return metadata

    def _resolve_return_url(self, command: CreatePaymentIntentCommand) -> str:
        return_url = command.success_url or settings.webapp_url
        if not return_url:
            raise PaymentGatewayError("success_url or WEBAPP_URL is required for YooKassa redirect flow")
        return return_url

    def _create_payment_intent_sync(
        self,
        command: CreatePaymentIntentCommand,
        idempotency_key: str,
    ) -> PaymentIntentSnapshot:
        self._configure_sdk()
        if command.currency != "RUB":
            raise PaymentGatewayError(f"YooKassa gateway expects RUB currency, got {command.currency!r}")

        params: dict[str, object] = {
            "amount": {
                "value": _format_rub_amount(command.amount_rub),
                "currency": command.currency,
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": self._resolve_return_url(command),
            },
            "metadata": self._build_metadata(command),
        }
        if command.description:
            params["description"] = command.description

        try:
            response = YooKassaPayment.create(params, idempotency_key)
        except YooKassaConfigurationError as exc:
            raise PaymentGatewayConfigurationError(str(exc)) from exc
        except YooKassaApiError as exc:
            raise PaymentGatewayError(f"YooKassa API error: {exc}") from exc
        except requests.RequestException as exc:
            raise PaymentGatewayError(f"YooKassa transport error: {exc}") from exc

        return PaymentIntentSnapshot(
            provider=self.provider,
            flow_type=command.flow_type,
            account_id=command.account_id,
            status=_map_yookassa_status(response.status),
            amount_rub=_require_whole_rubles(response.amount.value, currency=response.amount.currency),
            currency=response.amount.currency,
            provider_payment_id=response.id,
            external_reference=command.idempotency_key,
            confirmation_url=_extract_confirmation_url(response),
            expires_at=_parse_iso_datetime(getattr(response, "expires_at", None)),
            raw_payload=response.json(),
        )

    def _fetch_payment_sync(self, provider_payment_id: str) -> object:
        self._configure_sdk()
        try:
            return YooKassaPayment.find_one(provider_payment_id)
        except YooKassaConfigurationError as exc:
            raise PaymentGatewayConfigurationError(str(exc)) from exc
        except YooKassaApiError as exc:
            raise PaymentGatewayError(f"YooKassa API error: {exc}") from exc
        except requests.RequestException as exc:
            raise PaymentGatewayError(f"YooKassa transport error: {exc}") from exc

    async def create_payment_intent(
        self,
        command: CreatePaymentIntentCommand,
    ) -> PaymentIntentSnapshot:
        idempotency_key = command.idempotency_key or str(uuid4())
        return await asyncio.to_thread(self._create_payment_intent_sync, command, idempotency_key)

    async def parse_webhook(
        self,
        *,
        raw_body: bytes,
        headers: Mapping[str, str],
    ) -> PaymentWebhookEvent:
        del headers
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise PaymentGatewayError("Invalid YooKassa webhook JSON payload") from exc

        try:
            notification = WebhookNotification(payload)
        except Exception as exc:
            raise PaymentGatewayError(f"Invalid YooKassa webhook payload: {exc}") from exc

        if notification.type != "notification":
            raise PaymentGatewayError(f"Unsupported YooKassa webhook type: {notification.type!r}")

        event = notification.event
        payment = notification.object
        verified_payment = await asyncio.to_thread(self._fetch_payment_sync, payment.id)
        metadata = getattr(verified_payment, "metadata", None) or {}

        account_id_raw = metadata.get("rm_account_id") or metadata.get("account_id")
        flow_type_raw = metadata.get("rm_flow_type") or metadata.get("flow_type")
        if not account_id_raw or not flow_type_raw:
            raise PaymentGatewayError(
                "YooKassa webhook payload does not contain account_id/flow_type metadata"
            )

        try:
            account_id = UUID(account_id_raw)
        except ValueError as exc:
            raise PaymentGatewayError(f"Invalid account_id in YooKassa metadata: {account_id_raw!r}") from exc

        try:
            flow_type = PaymentFlowType(flow_type_raw)
        except ValueError as exc:
            raise PaymentGatewayError(f"Unsupported flow_type in YooKassa metadata: {flow_type_raw!r}") from exc

        provider_event_id = f"{event}:{verified_payment.id}"
        external_reference = metadata.get("rm_external_reference") or metadata.get("external_reference")
        currency = verified_payment.amount.currency

        return PaymentWebhookEvent(
            provider=self.provider,
            provider_event_id=provider_event_id,
            provider_payment_id=verified_payment.id,
            status=_map_yookassa_status(verified_payment.status),
            amount_rub=_require_whole_rubles(verified_payment.amount.value, currency=currency),
            currency=currency,
            flow_type=flow_type,
            account_id=account_id,
            external_reference=external_reference,
            raw_payload=verified_payment.json(),
        )


def get_yookassa_gateway() -> YooKassaGateway:
    return YooKassaGateway(
        shop_id=settings.yookassa_shop_id,
        secret_key=settings.yookassa_secret_key,
        api_url=settings.yookassa_api_url,
        verify_tls=settings.yookassa_verify_tls,
    )


FINAL_PAYMENT_STATUSES = {
    PaymentStatus.SUCCEEDED,
    PaymentStatus.FAILED,
    PaymentStatus.CANCELLED,
    PaymentStatus.EXPIRED,
}


class PaymentServiceError(Exception):
    pass


class PaymentConflictError(PaymentServiceError):
    pass


@dataclass(slots=True)
class PaymentWebhookProcessResult:
    payment_id: int
    provider_payment_id: str
    status: PaymentStatus
    duplicate: bool
    ledger_applied: bool


def _payment_to_snapshot(payment: Payment) -> PaymentIntentSnapshot:
    return PaymentIntentSnapshot(
        provider=payment.provider,
        flow_type=payment.flow_type,
        account_id=payment.account_id,
        status=payment.status,
        amount_rub=payment.amount,
        currency=payment.currency,
        provider_payment_id=payment.provider_payment_id,
        external_reference=payment.external_reference,
        confirmation_url=payment.confirmation_url,
        expires_at=payment.expires_at,
        raw_payload=payment.raw_payload,
    )


async def _get_payment_by_provider_payment_id(
    session: AsyncSession,
    *,
    provider: PaymentProvider,
    provider_payment_id: str,
) -> Payment | None:
    result = await session.execute(
        select(Payment).where(
            Payment.provider == provider,
            Payment.provider_payment_id == provider_payment_id,
        )
    )
    return result.scalar_one_or_none()


async def _get_payment_by_idempotency_key(
    session: AsyncSession,
    *,
    provider: PaymentProvider,
    idempotency_key: str,
) -> Payment | None:
    result = await session.execute(
        select(Payment).where(
            Payment.provider == provider,
            Payment.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def _get_payment_event_by_provider_event_id(
    session: AsyncSession,
    *,
    provider: PaymentProvider,
    provider_event_id: str,
) -> PaymentEvent | None:
    result = await session.execute(
        select(PaymentEvent).where(
            PaymentEvent.provider == provider,
            PaymentEvent.provider_event_id == provider_event_id,
        )
    )
    return result.scalar_one_or_none()


def _apply_payment_intent_snapshot(
    payment: Payment,
    *,
    command: CreatePaymentIntentCommand,
    snapshot: PaymentIntentSnapshot,
) -> None:
    payment.account_id = snapshot.account_id
    payment.provider = snapshot.provider
    payment.flow_type = snapshot.flow_type
    payment.status = snapshot.status
    payment.amount = snapshot.amount_rub
    payment.currency = snapshot.currency
    payment.provider_payment_id = snapshot.provider_payment_id
    payment.external_reference = snapshot.external_reference
    payment.idempotency_key = command.idempotency_key
    payment.plan_code = command.plan_code
    payment.description = command.description
    payment.success_url = command.success_url
    payment.cancel_url = command.cancel_url
    payment.confirmation_url = snapshot.confirmation_url
    payment.expires_at = snapshot.expires_at
    payment.raw_payload = snapshot.raw_payload
    payment.request_metadata = dict(command.metadata)
    payment.finalized_at = _utcnow() if snapshot.status in FINAL_PAYMENT_STATUSES else None


def _apply_payment_event(payment: Payment, event: PaymentWebhookEvent) -> None:
    if payment.account_id != event.account_id:
        raise PaymentConflictError("payment account_id mismatch")
    if payment.flow_type != event.flow_type:
        raise PaymentConflictError("payment flow_type mismatch")
    if payment.amount != event.amount_rub:
        raise PaymentConflictError("payment amount mismatch")
    if payment.currency != event.currency:
        raise PaymentConflictError("payment currency mismatch")

    payment.status = event.status
    payment.raw_payload = event.raw_payload
    if event.status in FINAL_PAYMENT_STATUSES and payment.finalized_at is None:
        payment.finalized_at = _utcnow()


def _validate_existing_idempotent_payment(
    payment: Payment,
    *,
    account: Account,
    flow_type: PaymentFlowType,
    amount_rub: int,
) -> None:
    if payment.account_id != account.id:
        raise PaymentConflictError("idempotency key already belongs to another account")
    if payment.flow_type != flow_type:
        raise PaymentConflictError("idempotency key already used for another payment flow")
    if payment.amount != amount_rub:
        raise PaymentConflictError("idempotency key already used for another amount")


async def create_yookassa_payment(
    session: AsyncSession,
    *,
    account: Account,
    flow_type: PaymentFlowType,
    amount_rub: int,
    success_url: str | None = None,
    cancel_url: str | None = None,
    description: str | None = None,
    plan_code: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, str] | None = None,
) -> PaymentIntentSnapshot:
    gateway = get_yookassa_gateway()
    if idempotency_key:
        existing_payment = await _get_payment_by_idempotency_key(
            session,
            provider=PaymentProvider.YOOKASSA,
            idempotency_key=idempotency_key,
        )
        if existing_payment is not None:
            _validate_existing_idempotent_payment(
                existing_payment,
                account=account,
                flow_type=flow_type,
                amount_rub=amount_rub,
            )
            return _payment_to_snapshot(existing_payment)

    command = CreatePaymentIntentCommand(
        account_id=account.id,
        flow_type=flow_type,
        amount_rub=amount_rub,
        currency="RUB",
        plan_code=plan_code,
        success_url=success_url,
        cancel_url=cancel_url,
        description=description,
        idempotency_key=idempotency_key,
        metadata=metadata or {},
    )
    snapshot = await gateway.create_payment_intent(command)

    payment = await _get_payment_by_provider_payment_id(
        session,
        provider=PaymentProvider.YOOKASSA,
        provider_payment_id=snapshot.provider_payment_id,
    )
    if payment is None:
        payment = Payment(
            account_id=account.id,
            provider=snapshot.provider,
            flow_type=snapshot.flow_type,
            status=snapshot.status,
            amount=snapshot.amount_rub,
            currency=snapshot.currency,
            provider_payment_id=snapshot.provider_payment_id,
        )
        session.add(payment)

    _apply_payment_intent_snapshot(payment, command=command, snapshot=snapshot)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if idempotency_key and "uq_payments_provider_idempotency" in str(exc):
            existing_payment = await _get_payment_by_idempotency_key(
                session,
                provider=PaymentProvider.YOOKASSA,
                idempotency_key=idempotency_key,
            )
            if existing_payment is not None:
                _validate_existing_idempotent_payment(
                    existing_payment,
                    account=account,
                    flow_type=flow_type,
                    amount_rub=amount_rub,
                )
                return _payment_to_snapshot(existing_payment)
        if "uq_payments_provider_payment_id" in str(exc):
            existing_payment = await _get_payment_by_provider_payment_id(
                session,
                provider=PaymentProvider.YOOKASSA,
                provider_payment_id=snapshot.provider_payment_id,
            )
            if existing_payment is not None:
                return _payment_to_snapshot(existing_payment)
        raise

    await session.refresh(payment)
    return _payment_to_snapshot(payment)


async def create_yookassa_topup_payment(
    session: AsyncSession,
    *,
    account: Account,
    amount_rub: int,
    success_url: str | None = None,
    cancel_url: str | None = None,
    description: str | None = None,
    idempotency_key: str | None = None,
) -> PaymentIntentSnapshot:
    return await create_yookassa_payment(
        session,
        account=account,
        flow_type=PaymentFlowType.WALLET_TOPUP,
        amount_rub=amount_rub,
        success_url=success_url,
        cancel_url=cancel_url,
        description=description,
        idempotency_key=idempotency_key,
    )


async def process_yookassa_webhook(
    session: AsyncSession,
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
) -> PaymentWebhookProcessResult:
    gateway = get_yookassa_gateway()
    event = await gateway.parse_webhook(raw_body=raw_body, headers=headers)

    existing_event = await _get_payment_event_by_provider_event_id(
        session,
        provider=event.provider,
        provider_event_id=event.provider_event_id,
    )
    if existing_event is not None:
        payment = await _get_payment_by_provider_payment_id(
            session,
            provider=event.provider,
            provider_payment_id=event.provider_payment_id,
        )
        if payment is None:
            raise PaymentServiceError(
                f"Payment not found for existing event {event.provider_event_id}"
            )
        return PaymentWebhookProcessResult(
            payment_id=payment.id,
            provider_payment_id=payment.provider_payment_id,
            status=payment.status,
            duplicate=True,
            ledger_applied=payment.flow_type == PaymentFlowType.WALLET_TOPUP
            and payment.status == PaymentStatus.SUCCEEDED,
        )

    payment = await _get_payment_by_provider_payment_id(
        session,
        provider=event.provider,
        provider_payment_id=event.provider_payment_id,
    )
    if payment is None:
        payment = Payment(
            account_id=event.account_id,
            provider=event.provider,
            flow_type=event.flow_type,
            status=event.status,
            amount=event.amount_rub,
            currency=event.currency,
            provider_payment_id=event.provider_payment_id,
            external_reference=event.external_reference,
            raw_payload=event.raw_payload,
            finalized_at=_utcnow() if event.status in FINAL_PAYMENT_STATUSES else None,
        )
        session.add(payment)
        await session.flush()
    else:
        _apply_payment_event(payment, event)

    payment_event = PaymentEvent(
        payment_id=payment.id,
        account_id=payment.account_id,
        provider=event.provider,
        flow_type=event.flow_type,
        status=event.status,
        provider_event_id=event.provider_event_id,
        provider_payment_id=event.provider_payment_id,
        event_type=event.provider_event_id.split(":", 1)[0],
        amount=event.amount_rub,
        currency=event.currency,
        raw_payload=event.raw_payload or {},
        processed_at=_utcnow(),
    )
    session.add(payment_event)

    ledger_applied = False
    if event.status == PaymentStatus.SUCCEEDED and payment.flow_type == PaymentFlowType.WALLET_TOPUP:
        await apply_credit_in_transaction(
            session,
            account_id=payment.account_id,
            amount=payment.amount,
            entry_type=LedgerEntryType.TOPUP_PAYMENT,
            reference_type="payment",
            reference_id=str(payment.id),
            comment=f"YooKassa payment {payment.provider_payment_id}",
            idempotency_key=f"payment:{payment.provider.value}:{payment.provider_payment_id}:credit",
        )
        ledger_applied = True

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_payment_events_provider_event_id" in str(exc):
            existing_event = await _get_payment_event_by_provider_event_id(
                session,
                provider=event.provider,
                provider_event_id=event.provider_event_id,
            )
            if existing_event is not None:
                payment = await _get_payment_by_provider_payment_id(
                    session,
                    provider=event.provider,
                    provider_payment_id=event.provider_payment_id,
                )
                if payment is None:
                    raise PaymentServiceError(
                        f"Payment not found for duplicate event {event.provider_event_id}"
                    )
                return PaymentWebhookProcessResult(
                    payment_id=payment.id,
                    provider_payment_id=payment.provider_payment_id,
                    status=payment.status,
                    duplicate=True,
                    ledger_applied=payment.flow_type == PaymentFlowType.WALLET_TOPUP
                    and payment.status == PaymentStatus.SUCCEEDED,
                )
        raise

    await session.refresh(payment)
    if ledger_applied:
        await clear_account_cache(payment.account_id)
    return PaymentWebhookProcessResult(
        payment_id=payment.id,
        provider_payment_id=payment.provider_payment_id,
        status=payment.status,
        duplicate=False,
        ledger_applied=ledger_applied,
    )
