from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from typing import Mapping
from uuid import UUID
from uuid import uuid4

import httpx
import requests
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from yookassa import Configuration as YooKassaConfiguration
from yookassa import Payment as YooKassaPayment
from yookassa.configuration import ConfigurationError as YooKassaConfigurationError
from yookassa.domain.exceptions import ApiError as YooKassaApiError
from yookassa.domain.notification.webhook_notification import WebhookNotification

from app.core.config import settings
from app.db.models import (
    Account,
    AccountStatus,
    LedgerEntryType,
    Payment,
    PaymentEvent,
    PromoCode,
    SubscriptionGrant,
)
from app.domain.payments import (
    CreatePaymentIntentCommand,
    PaymentFlowType,
    PaymentGateway,
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
    PaymentIntentSnapshot,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookEvent,
)
from app.services.account_events import append_account_event
from app.services.i18n import translate
from app.services.ledger import apply_credit_in_transaction, clear_account_cache
from app.services.notifications import (
    FINAL_FAILED_PAYMENT_STATUSES,
    notify_payment_failed,
    notify_payment_succeeded,
)
from app.services.plans import SubscriptionPlanError, get_subscription_plan
from app.services.promos import (
    PAYMENT_REFERENCE_TYPE,
    get_promo_redemption_by_reference,
    mark_promo_redemption_applied,
    normalize_promo_code,
    quote_plan_promo,
    stage_promo_redemption,
)
from app.services.purchases import (
    PurchaseSource,
    RemnawaveSyncError,
    apply_paid_purchase,
    compute_paid_plan_window,
)
from app.services.referrals import apply_first_referral_reward_for_grant


logger = logging.getLogger(__name__)


class PaymentAccountBlockedError(PaymentGatewayError):
    default_code = "account_blocked"


def _payment_error(key: str) -> str:
    return translate(f"api.payments.errors.{key}")


def _payment_exception(error_type, key: str):
    return error_type(_payment_error(key), code=key)


def _parse_iso_datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise PaymentGatewayError(f"Unsupported datetime payload: {value!r}")


def _normalize_json_payload(payload: object, *, field_name: str) -> dict | None:
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise PaymentGatewayError(f"Invalid JSON string in {field_name}") from exc
        if not isinstance(parsed, dict):
            raise PaymentGatewayError(f"{field_name} must be a JSON object")
        return parsed
    raise PaymentGatewayError(
        f"Unsupported {field_name} payload type: {type(payload).__name__}"
    )


def _require_integer_amount(raw_value: object, *, currency: str) -> int:
    if not isinstance(currency, str) or not currency:
        raise PaymentGatewayError("Payment currency is missing")

    try:
        decimal_value = Decimal(str(raw_value))
    except (InvalidOperation, TypeError) as exc:
        raise PaymentGatewayError(f"Invalid payment amount: {raw_value!r}") from exc

    if decimal_value != decimal_value.quantize(Decimal("1")):
        raise PaymentGatewayError(
            f"Fractional amounts are not supported: {raw_value!r} {currency}"
        )

    return int(decimal_value)


def _format_rub_amount(amount_rub: int) -> str:
    if amount_rub <= 0:
        raise PaymentGatewayError("Payment amount must be positive")
    return f"{amount_rub}.00"


def _format_integer_amount(amount: int) -> int:
    if amount <= 0:
        raise PaymentGatewayError("Payment amount must be positive")
    return amount


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
        raise PaymentGatewayError(
            f"Unsupported YooKassa status: {raw_status!r}"
        ) from exc


def _extract_confirmation_url(response: object) -> str | None:
    confirmation = getattr(response, "confirmation", None)
    if confirmation is None:
        return None
    return getattr(confirmation, "confirmation_url", None)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _as_db_naive_utc(value: datetime) -> datetime:
    normalized = _normalize_datetime(value)
    assert normalized is not None
    return normalized.replace(tzinfo=None)


def _get_pending_ttl_seconds(provider: PaymentProvider) -> int:
    if provider == PaymentProvider.YOOKASSA:
        return max(60, int(settings.payment_pending_ttl_seconds_yookassa))
    if provider == PaymentProvider.TELEGRAM_STARS:
        return max(60, int(settings.payment_pending_ttl_seconds_telegram_stars))
    return 3600


def _resolve_pending_payment_expires_at(
    *,
    provider: PaymentProvider,
    snapshot_expires_at: datetime | None,
    existing_expires_at: datetime | None = None,
) -> datetime | None:
    if snapshot_expires_at is not None:
        return snapshot_expires_at
    if existing_expires_at is not None:
        return existing_expires_at
    return _utcnow() + timedelta(seconds=_get_pending_ttl_seconds(provider))


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
            raise _payment_exception(
                PaymentGatewayConfigurationError, "yookassa_not_configured"
            )

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
            raise PaymentGatewayError(
                "success_url or WEBAPP_URL is required for YooKassa redirect flow"
            )
        return return_url

    def _create_payment_intent_sync(
        self,
        command: CreatePaymentIntentCommand,
        idempotency_key: str,
    ) -> PaymentIntentSnapshot:
        self._configure_sdk()
        if command.currency != "RUB":
            raise PaymentGatewayError(
                f"YooKassa gateway expects RUB currency, got {command.currency!r}"
            )

        params: dict[str, object] = {
            "amount": {
                "value": _format_rub_amount(command.amount),
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
            amount=_require_integer_amount(
                response.amount.value, currency=response.amount.currency
            ),
            currency=response.amount.currency,
            provider_payment_id=response.id,
            external_reference=command.idempotency_key,
            confirmation_url=_extract_confirmation_url(response),
            expires_at=_parse_iso_datetime(getattr(response, "expires_at", None)),
            raw_payload=_normalize_json_payload(
                response.json(), field_name="yookassa payment response"
            ),
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
        return await asyncio.to_thread(
            self._create_payment_intent_sync, command, idempotency_key
        )

    def _snapshot_from_payment_response(
        self, response: object
    ) -> PaymentIntentSnapshot:
        metadata = getattr(response, "metadata", None) or {}
        raw_account_id = metadata.get("rm_account_id")
        raw_flow_type = metadata.get("rm_flow_type")
        if not isinstance(raw_account_id, str) or not raw_account_id:
            raise PaymentGatewayError(
                "YooKassa payment metadata is missing rm_account_id"
            )
        if not isinstance(raw_flow_type, str) or not raw_flow_type:
            raise PaymentGatewayError(
                "YooKassa payment metadata is missing rm_flow_type"
            )

        try:
            account_id = UUID(raw_account_id)
        except ValueError as exc:
            raise PaymentGatewayError(
                "YooKassa payment metadata contains invalid rm_account_id"
            ) from exc

        try:
            flow_type = PaymentFlowType(raw_flow_type)
        except ValueError as exc:
            raise PaymentGatewayError(
                "YooKassa payment metadata contains invalid rm_flow_type"
            ) from exc

        return PaymentIntentSnapshot(
            provider=self.provider,
            flow_type=flow_type,
            account_id=account_id,
            status=_map_yookassa_status(response.status),
            amount=_require_integer_amount(
                response.amount.value, currency=response.amount.currency
            ),
            currency=response.amount.currency,
            provider_payment_id=response.id,
            external_reference=metadata.get("rm_external_reference"),
            confirmation_url=_extract_confirmation_url(response),
            expires_at=_parse_iso_datetime(getattr(response, "expires_at", None)),
            raw_payload=_normalize_json_payload(
                response.json(), field_name="yookassa payment response"
            ),
        )

    async def fetch_payment_snapshot(
        self, provider_payment_id: str
    ) -> PaymentIntentSnapshot:
        response = await asyncio.to_thread(
            self._fetch_payment_sync, provider_payment_id
        )
        return self._snapshot_from_payment_response(response)

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
            raise PaymentGatewayError(
                f"Invalid YooKassa webhook payload: {exc}"
            ) from exc

        if notification.type != "notification":
            raise PaymentGatewayError(
                f"Unsupported YooKassa webhook type: {notification.type!r}"
            )

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
            raise PaymentGatewayError(
                f"Invalid account_id in YooKassa metadata: {account_id_raw!r}"
            ) from exc

        try:
            flow_type = PaymentFlowType(flow_type_raw)
        except ValueError as exc:
            raise PaymentGatewayError(
                f"Unsupported flow_type in YooKassa metadata: {flow_type_raw!r}"
            ) from exc

        provider_event_id = f"{event}:{verified_payment.id}"
        external_reference = metadata.get("rm_external_reference") or metadata.get(
            "external_reference"
        )
        currency = verified_payment.amount.currency

        return PaymentWebhookEvent(
            provider=self.provider,
            provider_event_id=provider_event_id,
            provider_payment_id=verified_payment.id,
            status=_map_yookassa_status(verified_payment.status),
            amount=_require_integer_amount(
                verified_payment.amount.value, currency=currency
            ),
            currency=currency,
            flow_type=flow_type,
            account_id=account_id,
            external_reference=external_reference,
            raw_payload=_normalize_json_payload(
                verified_payment.json(),
                field_name="yookassa verified payment response",
            ),
        )


def get_yookassa_gateway() -> YooKassaGateway:
    return YooKassaGateway(
        shop_id=settings.yookassa_shop_id,
        secret_key=settings.yookassa_secret_key,
        api_url=settings.yookassa_api_url,
        verify_tls=settings.yookassa_verify_tls,
    )


FLOW_CODE_MAP = {
    PaymentFlowType.WALLET_TOPUP: "wt",
    PaymentFlowType.DIRECT_PLAN_PURCHASE: "dp",
}
FLOW_CODE_REVERSE_MAP = {value: key for key, value in FLOW_CODE_MAP.items()}


def _build_telegram_stars_invoice_payload(
    *,
    account_id: UUID,
    flow_type: PaymentFlowType,
    payment_reference: str,
) -> str:
    return f"rmstars:{FLOW_CODE_MAP[flow_type]}:{account_id}:{payment_reference}"


def _parse_telegram_stars_invoice_payload(
    invoice_payload: str,
) -> tuple[PaymentFlowType, UUID]:
    parts = invoice_payload.split(":")
    if len(parts) != 4 or parts[0] != "rmstars":
        raise PaymentGatewayError("Invalid Telegram Stars invoice payload")

    flow_code = parts[1]
    account_id_raw = parts[2]

    try:
        flow_type = FLOW_CODE_REVERSE_MAP[flow_code]
    except KeyError as exc:
        raise PaymentGatewayError(
            f"Unsupported Telegram Stars flow code: {flow_code!r}"
        ) from exc

    try:
        account_id = UUID(account_id_raw)
    except ValueError as exc:
        raise PaymentGatewayError(
            f"Invalid account_id in Telegram Stars payload: {account_id_raw!r}"
        ) from exc

    return flow_type, account_id


class TelegramStarsGateway:
    provider = PaymentProvider.TELEGRAM_STARS

    def __init__(
        self,
        *,
        bot_token: str,
        api_base_url: str = "https://api.telegram.org",
    ) -> None:
        self._bot_token = bot_token
        self._api_base_url = api_base_url.rstrip("/")

    def _assert_configured(self) -> None:
        if not self._bot_token:
            raise _payment_exception(
                PaymentGatewayConfigurationError, "stars_bot_token_required"
            )
        if not settings.api_token:
            raise _payment_exception(
                PaymentGatewayConfigurationError, "stars_callback_not_configured"
            )

    async def _call_bot_api(self, method: str, payload: dict[str, object]) -> dict:
        self._assert_configured()
        url = f"{self._api_base_url}/bot{self._bot_token}/{method}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise PaymentGatewayError(
                f"Telegram Bot API transport error: {exc}"
            ) from exc

        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise PaymentGatewayError("Telegram Bot API returned invalid JSON") from exc

        if response.status_code >= 400 or not body.get("ok", False):
            description = (
                body.get("description")
                or f"Telegram Bot API error {response.status_code}"
            )
            raise PaymentGatewayError(str(description))

        result = body.get("result")
        if not isinstance(result, (dict, str)):
            raise PaymentGatewayError(
                f"Unexpected Telegram Bot API response for {method}: {result!r}"
            )
        return {"result": result}

    async def create_payment_intent(
        self,
        command: CreatePaymentIntentCommand,
    ) -> PaymentIntentSnapshot:
        if command.flow_type != PaymentFlowType.DIRECT_PLAN_PURCHASE:
            raise PaymentGatewayError(
                "Telegram Stars supports only direct_plan_purchase"
            )
        if command.currency != "XTR":
            raise PaymentGatewayError(
                f"Telegram Stars gateway expects XTR currency, got {command.currency!r}"
            )
        if not command.plan_code:
            raise PaymentGatewayError(
                "plan_code is required for Telegram Stars purchase"
            )

        payment_reference = command.idempotency_key or uuid4().hex
        invoice_payload = _build_telegram_stars_invoice_payload(
            account_id=command.account_id,
            flow_type=command.flow_type,
            payment_reference=payment_reference,
        )
        description = command.description or translate(
            "api.payments.descriptions.plan",
            plan_name=str(command.plan_code or ""),
        )
        plan_name = command.metadata.get("rm_plan_name") or command.plan_code
        result = await self._call_bot_api(
            "createInvoiceLink",
            {
                "title": translate(
                    "api.payments.invoice_title", plan_name=str(plan_name or "")
                ),
                "description": description,
                "payload": invoice_payload,
                "currency": "XTR",
                "provider_token": "",
                "prices": [
                    {
                        "label": description,
                        "amount": _format_integer_amount(command.amount),
                    }
                ],
            },
        )
        confirmation_url = result["result"]
        if not isinstance(confirmation_url, str) or not confirmation_url:
            raise PaymentGatewayError("Telegram Bot API returned invalid invoice link")

        return PaymentIntentSnapshot(
            provider=self.provider,
            flow_type=command.flow_type,
            account_id=command.account_id,
            status=PaymentStatus.PENDING,
            amount=command.amount,
            currency="XTR",
            provider_payment_id=invoice_payload,
            external_reference=command.idempotency_key,
            confirmation_url=confirmation_url,
            expires_at=None,
            raw_payload={
                "invoice_payload": invoice_payload,
                "invoice_link": confirmation_url,
            },
        )

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
            raise PaymentGatewayError(
                "Invalid Telegram Stars webhook JSON payload"
            ) from exc

        if payload.get("event_type") != "successful_payment":
            raise PaymentGatewayError("Unsupported Telegram Stars webhook type")

        invoice_payload = payload.get("invoice_payload")
        telegram_payment_charge_id = payload.get("telegram_payment_charge_id")
        currency = payload.get("currency")
        total_amount = payload.get("total_amount")
        if not isinstance(invoice_payload, str) or not invoice_payload:
            raise PaymentGatewayError(
                "Telegram Stars webhook is missing invoice_payload"
            )
        if (
            not isinstance(telegram_payment_charge_id, str)
            or not telegram_payment_charge_id
        ):
            raise PaymentGatewayError(
                "Telegram Stars webhook is missing telegram_payment_charge_id"
            )
        if not isinstance(currency, str) or not currency:
            raise PaymentGatewayError("Telegram Stars webhook is missing currency")

        flow_type, account_id = _parse_telegram_stars_invoice_payload(invoice_payload)

        return PaymentWebhookEvent(
            provider=self.provider,
            provider_event_id=f"successful_payment:{telegram_payment_charge_id}",
            provider_payment_id=invoice_payload,
            status=PaymentStatus.SUCCEEDED,
            amount=_require_integer_amount(total_amount, currency=currency),
            currency=currency,
            flow_type=flow_type,
            account_id=account_id,
            external_reference=payload.get("provider_payment_charge_id"),
            raw_payload=payload,
        )


def get_telegram_stars_gateway() -> TelegramStarsGateway:
    return TelegramStarsGateway(bot_token=settings.telegram_bot_token)


FINAL_PAYMENT_STATUSES = {
    PaymentStatus.SUCCEEDED,
    PaymentStatus.FAILED,
    PaymentStatus.CANCELLED,
    PaymentStatus.EXPIRED,
}

SUCCESS_EFFECT_FLOWS = {
    PaymentFlowType.WALLET_TOPUP,
    PaymentFlowType.DIRECT_PLAN_PURCHASE,
}


class PaymentServiceError(Exception):
    default_code: str | None = None

    def __init__(self, detail: str, *, code: str | None = None) -> None:
        super().__init__(detail)
        self.code = code or self.default_code


class PaymentConflictError(PaymentServiceError):
    pass


class PaymentNotFoundError(PaymentServiceError):
    default_code = "payment_not_found"


@dataclass(slots=True)
class PaymentWebhookProcessResult:
    payment_id: int
    provider_payment_id: str
    status: PaymentStatus
    duplicate: bool
    ledger_applied: bool
    subscription_applied: bool = False


@dataclass(slots=True)
class PaymentMaintenanceResult:
    processed: int = 0
    expired: int = 0
    succeeded: int = 0
    cancelled: int = 0
    failed: int = 0


def _payment_event_payload(payment: Payment) -> dict[str, object]:
    return {
        "payment_id": payment.id,
        "provider": payment.provider.value,
        "flow_type": payment.flow_type.value,
        "status": payment.status.value,
        "amount": payment.amount,
        "currency": payment.currency,
        "provider_payment_id": payment.provider_payment_id,
        "plan_code": payment.plan_code,
        "external_reference": payment.external_reference,
        "idempotency_key": payment.idempotency_key,
    }


async def _append_payment_account_event(
    session: AsyncSession,
    *,
    payment: Payment,
    event_type: str,
    source: str,
    outcome: str = "success",
    actor_account_id: UUID | None = None,
    payload: dict[str, object] | None = None,
) -> None:
    event_payload = _payment_event_payload(payment)
    if payload:
        event_payload.update(payload)
    await append_account_event(
        session,
        account_id=payment.account_id,
        actor_account_id=actor_account_id,
        event_type=event_type,
        outcome=outcome,
        source=source,
        payload={
            key: value for key, value in event_payload.items() if value is not None
        },
    )


STALE_PENDING_PAYMENT_STATUSES = {
    PaymentStatus.CREATED,
    PaymentStatus.PENDING,
    PaymentStatus.REQUIRES_ACTION,
}


def _payment_to_snapshot(payment: Payment) -> PaymentIntentSnapshot:
    return PaymentIntentSnapshot(
        provider=payment.provider,
        flow_type=payment.flow_type,
        account_id=payment.account_id,
        status=payment.status,
        amount=payment.amount,
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
    for_update: bool = False,
) -> Payment | None:
    statement = select(Payment).where(
        Payment.provider == provider,
        Payment.provider_payment_id == provider_payment_id,
    )
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
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


async def get_payment_for_account(
    session: AsyncSession,
    *,
    account: Account,
    provider: PaymentProvider,
    provider_payment_id: str,
) -> Payment:
    result = await session.execute(
        select(Payment).where(
            Payment.account_id == account.id,
            Payment.provider == provider,
            Payment.provider_payment_id == provider_payment_id,
        )
    )
    payment = result.scalar_one_or_none()
    if payment is None:
        raise PaymentNotFoundError(_payment_error("payment_not_found"))
    return payment


async def list_account_payments(
    session: AsyncSession,
    *,
    account: Account,
    limit: int = 20,
    offset: int = 0,
    active_only: bool = False,
) -> tuple[list[Payment], int]:
    filters = [Payment.account_id == account.id]
    if active_only:
        filters.append(
            Payment.status.in_(
                (
                    PaymentStatus.CREATED,
                    PaymentStatus.PENDING,
                    PaymentStatus.REQUIRES_ACTION,
                )
            )
        )

    result = await session.execute(
        select(Payment)
        .where(*filters)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .offset(offset)
        .limit(limit)
    )
    items = list(result.scalars().all())
    total = await session.scalar(
        select(func.count()).select_from(Payment).where(*filters)
    )
    return items, int(total or 0)


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


async def _get_payment_by_id(
    session: AsyncSession,
    *,
    payment_id: int,
    for_update: bool = False,
) -> Payment | None:
    statement = select(Payment).where(Payment.id == payment_id)
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def _get_subscription_grant_by_payment_id(
    session: AsyncSession,
    *,
    payment_id: int,
    for_update: bool = False,
) -> SubscriptionGrant | None:
    statement = select(SubscriptionGrant).where(
        SubscriptionGrant.payment_id == payment_id
    )
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def _load_account_for_update(
    session: AsyncSession,
    *,
    account_id: UUID,
) -> Account:
    result = await session.execute(
        select(Account).where(Account.id == account_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise PaymentServiceError(_payment_error("account_not_found"))
    return account


def _should_finalize_payment(
    *, flow_type: PaymentFlowType, status: PaymentStatus
) -> bool:
    if status not in FINAL_PAYMENT_STATUSES:
        return False
    if status == PaymentStatus.SUCCEEDED and flow_type in SUCCESS_EFFECT_FLOWS:
        return False
    return True


def _extract_plan_duration_days(payment: Payment) -> int:
    metadata = payment.request_metadata or {}
    raw_value = metadata.get("rm_plan_duration_days")
    if raw_value is not None:
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise PaymentConflictError(
                "payment metadata contains invalid rm_plan_duration_days"
            ) from exc
        if value <= 0:
            raise PaymentConflictError(
                "payment metadata contains non-positive rm_plan_duration_days"
            )
        return value

    if payment.plan_code:
        try:
            return get_subscription_plan(payment.plan_code).duration_days
        except SubscriptionPlanError as exc:
            raise PaymentConflictError(str(exc)) from exc

    raise PaymentConflictError("payment does not contain plan duration metadata")


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
    payment.amount = snapshot.amount
    payment.currency = snapshot.currency
    payment.provider_payment_id = snapshot.provider_payment_id
    payment.external_reference = snapshot.external_reference
    payment.idempotency_key = command.idempotency_key
    payment.plan_code = command.plan_code
    payment.description = command.description
    payment.success_url = command.success_url
    payment.cancel_url = command.cancel_url
    payment.confirmation_url = snapshot.confirmation_url
    payment.expires_at = _resolve_pending_payment_expires_at(
        provider=snapshot.provider,
        snapshot_expires_at=snapshot.expires_at,
        existing_expires_at=payment.expires_at,
    )
    payment.raw_payload = snapshot.raw_payload
    payment.request_metadata = dict(command.metadata)
    payment.finalized_at = (
        _utcnow()
        if _should_finalize_payment(
            flow_type=snapshot.flow_type, status=snapshot.status
        )
        else None
    )


def _apply_payment_event(payment: Payment, event: PaymentWebhookEvent) -> None:
    if payment.account_id != event.account_id:
        raise PaymentConflictError("payment account_id mismatch")
    if payment.flow_type != event.flow_type:
        raise PaymentConflictError("payment flow_type mismatch")
    if payment.amount != event.amount:
        raise PaymentConflictError("payment amount mismatch")
    if payment.currency != event.currency:
        raise PaymentConflictError("payment currency mismatch")

    payment.status = event.status
    payment.raw_payload = event.raw_payload
    if (
        _should_finalize_payment(flow_type=payment.flow_type, status=event.status)
        and payment.finalized_at is None
    ):
        payment.finalized_at = _utcnow()


def _validate_existing_idempotent_payment(
    payment: Payment,
    *,
    account: Account,
    flow_type: PaymentFlowType,
    amount: int,
    plan_code: str | None = None,
) -> None:
    if payment.account_id != account.id:
        raise _payment_exception(PaymentConflictError, "idempotency_account_conflict")
    if payment.flow_type != flow_type:
        raise _payment_exception(PaymentConflictError, "idempotency_flow_conflict")
    if payment.amount != amount:
        raise _payment_exception(PaymentConflictError, "idempotency_amount_conflict")
    if payment.plan_code != plan_code:
        raise _payment_exception(PaymentConflictError, "idempotency_plan_conflict")


def _is_stale_pending_payment(payment: Payment, *, now: datetime) -> bool:
    expires_at = _normalize_datetime(payment.expires_at)
    return (
        payment.status in STALE_PENDING_PAYMENT_STATUSES
        and payment.finalized_at is None
        and expires_at is not None
        and expires_at <= now
    )


def _should_reconcile_pending_yookassa_payment(
    payment: Payment,
    *,
    now: datetime,
    min_age_seconds: int,
) -> bool:
    created_at = _normalize_datetime(payment.created_at)
    expires_at = _normalize_datetime(payment.expires_at)
    if payment.provider != PaymentProvider.YOOKASSA:
        return False
    if payment.finalized_at is not None:
        return False
    if created_at is not None and created_at > now - timedelta(
        seconds=max(1, min_age_seconds)
    ):
        return False

    if payment.status == PaymentStatus.SUCCEEDED:
        return payment.flow_type in SUCCESS_EFFECT_FLOWS

    if payment.status not in STALE_PENDING_PAYMENT_STATUSES:
        return False
    if expires_at is not None and expires_at <= now:
        return False
    return True


async def expire_stale_payments(
    session: AsyncSession,
    *,
    limit: int,
) -> PaymentMaintenanceResult:
    now = _utcnow()
    result = await session.execute(
        select(Payment.id)
        .where(
            Payment.status.in_(tuple(STALE_PENDING_PAYMENT_STATUSES)),
            Payment.finalized_at.is_(None),
            Payment.expires_at.is_not(None),
            Payment.expires_at <= now,
        )
        .order_by(Payment.expires_at.asc(), Payment.id.asc())
        .limit(limit)
    )
    payment_ids = list(result.scalars().all())

    summary = PaymentMaintenanceResult()
    for payment_id in payment_ids:
        payment = await _get_payment_by_id(
            session, payment_id=payment_id, for_update=True
        )
        if payment is None or not _is_stale_pending_payment(payment, now=now):
            continue

        payment.status = PaymentStatus.EXPIRED
        payment.finalized_at = _utcnow()
        await notify_payment_failed(
            session, payment=payment, status=PaymentStatus.EXPIRED
        )
        await _append_payment_account_event(
            session,
            payment=payment,
            event_type="payment.finalized",
            source="maintenance",
            outcome="failure",
            payload={
                "final_status": PaymentStatus.EXPIRED.value,
                "finalized_at": payment.finalized_at.isoformat(),
            },
        )
        summary.processed += 1
        summary.expired += 1

    if summary.processed > 0:
        await session.commit()
    else:
        await session.rollback()

    return summary


async def reconcile_pending_yookassa_payments(
    session: AsyncSession,
    *,
    limit: int,
    min_age_seconds: int | None = None,
) -> PaymentMaintenanceResult:
    now = _utcnow()
    created_before = _as_db_naive_utc(now)
    reconcile_min_age_seconds = (
        max(1, int(min_age_seconds))
        if min_age_seconds is not None
        else max(1, int(settings.payment_reconcile_yookassa_min_age_seconds))
    )
    result = await session.execute(
        select(Payment.id)
        .where(
            Payment.provider == PaymentProvider.YOOKASSA,
            Payment.finalized_at.is_(None),
            Payment.created_at
            <= created_before - timedelta(seconds=reconcile_min_age_seconds),
            or_(
                Payment.status.in_(tuple(STALE_PENDING_PAYMENT_STATUSES)),
                and_(
                    Payment.status == PaymentStatus.SUCCEEDED,
                    Payment.flow_type.in_(tuple(SUCCESS_EFFECT_FLOWS)),
                ),
            ),
        )
        .order_by(Payment.created_at.asc(), Payment.id.asc())
        .limit(limit)
    )
    payment_ids = list(result.scalars().all())

    gateway = get_yookassa_gateway()
    summary = PaymentMaintenanceResult()
    for payment_id in payment_ids:
        payment = await _get_payment_by_id(
            session, payment_id=payment_id, for_update=True
        )
        if payment is None or not _should_reconcile_pending_yookassa_payment(
            payment,
            now=now,
            min_age_seconds=reconcile_min_age_seconds,
        ):
            continue

        try:
            snapshot = await gateway.fetch_payment_snapshot(payment.provider_payment_id)
        except PaymentGatewayError:
            await session.rollback()
            logger.exception(
                "yookassa reconciliation failed for payment_id=%s provider_payment_id=%s",
                payment.id,
                payment.provider_payment_id,
            )
            continue

        if snapshot.account_id != payment.account_id:
            await session.rollback()
            logger.error(
                "yookassa reconciliation account mismatch for payment_id=%s provider_payment_id=%s",
                payment.id,
                payment.provider_payment_id,
            )
            continue
        if snapshot.flow_type != payment.flow_type:
            await session.rollback()
            logger.error(
                "yookassa reconciliation flow mismatch for payment_id=%s provider_payment_id=%s",
                payment.id,
                payment.provider_payment_id,
            )
            continue
        if snapshot.amount != payment.amount or snapshot.currency != payment.currency:
            await session.rollback()
            logger.error(
                "yookassa reconciliation amount mismatch for payment_id=%s provider_payment_id=%s",
                payment.id,
                payment.provider_payment_id,
            )
            continue

        payment.status = snapshot.status
        payment.raw_payload = snapshot.raw_payload
        payment.expires_at = _resolve_pending_payment_expires_at(
            provider=payment.provider,
            snapshot_expires_at=snapshot.expires_at,
            existing_expires_at=payment.expires_at,
        )

        if snapshot.status == PaymentStatus.SUCCEEDED:
            if payment.flow_type == PaymentFlowType.WALLET_TOPUP:
                if await _finalize_wallet_topup_payment(session, payment_id=payment.id):
                    summary.processed += 1
                    summary.succeeded += 1
            elif payment.flow_type == PaymentFlowType.DIRECT_PLAN_PURCHASE:
                await _stage_plan_purchase_grant(session, payment=payment)
                if await _finalize_direct_plan_purchase(session, payment_id=payment.id):
                    summary.processed += 1
                    summary.succeeded += 1
            continue

        if snapshot.status in FINAL_FAILED_PAYMENT_STATUSES:
            payment.finalized_at = _utcnow()
            await notify_payment_failed(
                session, payment=payment, status=snapshot.status
            )
            await _append_payment_account_event(
                session,
                payment=payment,
                event_type="payment.finalized",
                source="reconcile",
                outcome="failure",
                payload={
                    "final_status": snapshot.status.value,
                    "finalized_at": payment.finalized_at.isoformat(),
                },
            )
            await session.commit()
            summary.processed += 1
            if snapshot.status == PaymentStatus.CANCELLED:
                summary.cancelled += 1
            else:
                summary.failed += 1
            continue

        await session.commit()

    if summary.processed == 0:
        await session.rollback()

    return summary


async def create_payment(
    session: AsyncSession,
    *,
    gateway: PaymentGateway,
    account: Account,
    flow_type: PaymentFlowType,
    amount: int,
    currency: str,
    success_url: str | None = None,
    cancel_url: str | None = None,
    description: str | None = None,
    plan_code: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, str] | None = None,
    source: str = "api",
) -> PaymentIntentSnapshot:
    if account.status == AccountStatus.BLOCKED:
        raise PaymentAccountBlockedError(_payment_error("account_blocked"))

    if idempotency_key:
        existing_payment = await _get_payment_by_idempotency_key(
            session,
            provider=gateway.provider,
            idempotency_key=idempotency_key,
        )
        if existing_payment is not None:
            _validate_existing_idempotent_payment(
                existing_payment,
                account=account,
                flow_type=flow_type,
                amount=amount,
                plan_code=plan_code,
            )
            return _payment_to_snapshot(existing_payment)

    command = CreatePaymentIntentCommand(
        account_id=account.id,
        flow_type=flow_type,
        amount=amount,
        currency=currency,
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
        provider=gateway.provider,
        provider_payment_id=snapshot.provider_payment_id,
    )
    is_new_payment = payment is None
    if payment is None:
        payment = Payment(
            account_id=account.id,
            provider=snapshot.provider,
            flow_type=snapshot.flow_type,
            status=snapshot.status,
            amount=snapshot.amount,
            currency=snapshot.currency,
            provider_payment_id=snapshot.provider_payment_id,
        )
        session.add(payment)

    _apply_payment_intent_snapshot(payment, command=command, snapshot=snapshot)
    await session.flush()
    if is_new_payment:
        await _append_payment_account_event(
            session,
            payment=payment,
            event_type="payment.intent.created",
            source=source,
            actor_account_id=account.id,
            payload={
                "confirmation_url": payment.confirmation_url,
                "expires_at": None
                if payment.expires_at is None
                else payment.expires_at.isoformat(),
            },
        )

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if idempotency_key and "uq_payments_provider_idempotency" in str(exc):
            existing_payment = await _get_payment_by_idempotency_key(
                session,
                provider=gateway.provider,
                idempotency_key=idempotency_key,
            )
            if existing_payment is not None:
                _validate_existing_idempotent_payment(
                    existing_payment,
                    account=account,
                    flow_type=flow_type,
                    amount=amount,
                    plan_code=plan_code,
                )
                return _payment_to_snapshot(existing_payment)
        if "uq_payments_provider_payment_id" in str(exc):
            existing_payment = await _get_payment_by_provider_payment_id(
                session,
                provider=gateway.provider,
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
    source: str = "api",
) -> PaymentIntentSnapshot:
    return await create_payment(
        session,
        gateway=get_yookassa_gateway(),
        account=account,
        flow_type=PaymentFlowType.WALLET_TOPUP,
        amount=amount_rub,
        currency="RUB",
        success_url=success_url,
        cancel_url=cancel_url,
        description=description,
        idempotency_key=idempotency_key,
        source=source,
    )


async def create_yookassa_plan_purchase_payment(
    session: AsyncSession,
    *,
    account: Account,
    plan_code: str,
    success_url: str | None = None,
    cancel_url: str | None = None,
    description: str | None = None,
    idempotency_key: str | None = None,
    promo_code: str | None = None,
    source: str = "api",
) -> PaymentIntentSnapshot:
    plan = get_subscription_plan(plan_code)
    if promo_code is not None and idempotency_key:
        existing_payment = await _get_payment_by_idempotency_key(
            session,
            provider=PaymentProvider.YOOKASSA,
            idempotency_key=idempotency_key,
        )
        if existing_payment is not None and existing_payment.id is not None:
            existing_redemption = await get_promo_redemption_by_reference(
                session,
                reference_type=PAYMENT_REFERENCE_TYPE,
                reference_id=str(existing_payment.id),
            )
            if existing_redemption is not None:
                existing_promo_code = await session.get(
                    PromoCode, existing_redemption.promo_code_id
                )
                if (
                    existing_promo_code is None
                    or existing_promo_code.code != normalize_promo_code(promo_code)
                ):
                    raise _payment_exception(
                        PaymentConflictError, "idempotency_promo_conflict"
                    )
                return _payment_to_snapshot(existing_payment)

    quote = None
    amount = plan.price_rub
    duration_days = plan.duration_days
    if promo_code is not None:
        if not idempotency_key:
            raise _payment_exception(PaymentConflictError, "promo_idempotency_required")
        quote = await quote_plan_promo(
            session,
            account=account,
            plan_code=plan.code,
            base_amount=plan.price_rub,
            currency="RUB",
            code=promo_code,
        )
        amount = quote.final_amount
        duration_days = quote.final_duration_days
    plan_description = description or translate(
        "api.payments.descriptions.plan", plan_name=plan.name
    )
    snapshot = await create_payment(
        session,
        gateway=get_yookassa_gateway(),
        account=account,
        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
        amount=amount,
        currency="RUB",
        success_url=success_url,
        cancel_url=cancel_url,
        description=plan_description,
        plan_code=plan.code,
        idempotency_key=idempotency_key,
        source=source,
        metadata={
            "rm_plan_code": plan.code,
            "rm_plan_name": plan.name,
            "rm_plan_duration_days": str(duration_days),
            **(
                {}
                if quote is None
                else {
                    "rm_promo_code": quote.promo_code.code,
                    "rm_promo_effect_type": quote.campaign.effect_type.value,
                    "rm_promo_discount_amount": str(quote.discount_amount),
                    "rm_promo_original_amount": str(quote.original_amount),
                    "rm_promo_final_amount": str(quote.final_amount),
                }
            ),
        },
    )
    if quote is not None:
        payment = await _get_payment_by_provider_payment_id(
            session,
            provider=snapshot.provider,
            provider_payment_id=snapshot.provider_payment_id,
        )
        if payment is None or payment.id is None:
            raise _payment_exception(PaymentGatewayError, "promo_payment_not_found")
        await stage_promo_redemption(
            session,
            account_id=account.id,
            quote=quote,
            reference_type=PAYMENT_REFERENCE_TYPE,
            reference_id=str(payment.id),
            payment_id=payment.id,
        )
    return snapshot


async def create_telegram_stars_plan_purchase_payment(
    session: AsyncSession,
    *,
    account: Account,
    plan_code: str,
    description: str | None = None,
    idempotency_key: str | None = None,
    promo_code: str | None = None,
    source: str = "api",
) -> PaymentIntentSnapshot:
    if account.telegram_id is None:
        raise _payment_exception(PaymentConflictError, "stars_telegram_required")

    plan = get_subscription_plan(plan_code)
    if plan.price_stars is None:
        raise PaymentGatewayConfigurationError(
            translate("api.plans.errors.stars_price_not_configured"),
            code="stars_price_not_configured",
        )

    if promo_code is not None and idempotency_key:
        existing_payment = await _get_payment_by_idempotency_key(
            session,
            provider=PaymentProvider.TELEGRAM_STARS,
            idempotency_key=idempotency_key,
        )
        if existing_payment is not None and existing_payment.id is not None:
            existing_redemption = await get_promo_redemption_by_reference(
                session,
                reference_type=PAYMENT_REFERENCE_TYPE,
                reference_id=str(existing_payment.id),
            )
            if existing_redemption is not None:
                existing_promo_code = await session.get(
                    PromoCode, existing_redemption.promo_code_id
                )
                if (
                    existing_promo_code is None
                    or existing_promo_code.code != normalize_promo_code(promo_code)
                ):
                    raise _payment_exception(
                        PaymentConflictError, "idempotency_promo_conflict"
                    )
                return _payment_to_snapshot(existing_payment)

    quote = None
    amount = plan.price_stars
    duration_days = plan.duration_days
    if promo_code is not None:
        if not idempotency_key:
            raise _payment_exception(PaymentConflictError, "promo_idempotency_required")
        quote = await quote_plan_promo(
            session,
            account=account,
            plan_code=plan.code,
            base_amount=plan.price_stars,
            currency="XTR",
            code=promo_code,
        )
        amount = quote.final_amount
        duration_days = quote.final_duration_days

    plan_description = description or translate(
        "api.payments.descriptions.plan_stars",
        plan_name=plan.name,
    )
    snapshot = await create_payment(
        session,
        gateway=get_telegram_stars_gateway(),
        account=account,
        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
        amount=amount,
        currency="XTR",
        description=plan_description,
        plan_code=plan.code,
        idempotency_key=idempotency_key,
        source=source,
        metadata={
            "rm_plan_code": plan.code,
            "rm_plan_name": plan.name,
            "rm_plan_duration_days": str(duration_days),
            "rm_expected_telegram_id": str(account.telegram_id),
            **(
                {}
                if quote is None
                else {
                    "rm_promo_code": quote.promo_code.code,
                    "rm_promo_effect_type": quote.campaign.effect_type.value,
                    "rm_promo_discount_amount": str(quote.discount_amount),
                    "rm_promo_original_amount": str(quote.original_amount),
                    "rm_promo_final_amount": str(quote.final_amount),
                }
            ),
        },
    )
    if quote is not None:
        payment = await _get_payment_by_provider_payment_id(
            session,
            provider=snapshot.provider,
            provider_payment_id=snapshot.provider_payment_id,
        )
        if payment is None or payment.id is None:
            raise _payment_exception(PaymentGatewayError, "promo_payment_not_found")
        await stage_promo_redemption(
            session,
            account_id=account.id,
            quote=quote,
            reference_type=PAYMENT_REFERENCE_TYPE,
            reference_id=str(payment.id),
            payment_id=payment.id,
        )
    return snapshot


async def validate_telegram_stars_pre_checkout(
    session: AsyncSession,
    *,
    telegram_id: int,
    invoice_payload: str,
    total_amount: int,
    currency: str,
) -> tuple[bool, str | None]:
    payment = await _get_payment_by_provider_payment_id(
        session,
        provider=PaymentProvider.TELEGRAM_STARS,
        provider_payment_id=invoice_payload,
    )
    if payment is None:
        return False, translate("api.payments.pre_checkout_errors.payment_not_found")
    if payment.status in FINAL_PAYMENT_STATUSES:
        return False, translate(
            "api.payments.pre_checkout_errors.payment_already_processed"
        )
    if payment.currency != currency:
        return False, translate("api.payments.pre_checkout_errors.currency_mismatch")
    if payment.amount != total_amount:
        return False, translate("api.payments.pre_checkout_errors.amount_mismatch")

    account = await session.get(Account, payment.account_id)
    if account is None:
        return False, translate("api.payments.pre_checkout_errors.account_not_found")
    if account.status == AccountStatus.BLOCKED:
        return False, translate("api.payments.pre_checkout_errors.account_blocked")
    if account.telegram_id != telegram_id:
        return False, translate(
            "api.payments.pre_checkout_errors.telegram_account_mismatch"
        )
    if payment.flow_type != PaymentFlowType.DIRECT_PLAN_PURCHASE:
        return False, translate(
            "api.payments.pre_checkout_errors.unsupported_flow_type"
        )

    return True, None


async def _validate_telegram_stars_actor(
    session: AsyncSession,
    *,
    event: PaymentWebhookEvent,
) -> None:
    raw_telegram_id = (event.raw_payload or {}).get("telegram_id")
    if not isinstance(raw_telegram_id, int):
        raise PaymentConflictError(
            "Telegram Stars webhook does not contain telegram_id"
        )

    account = await session.get(Account, event.account_id)
    if account is None:
        raise _payment_exception(
            PaymentConflictError, "telegram_stars_account_not_found"
        )
    if account.telegram_id != raw_telegram_id:
        raise _payment_exception(
            PaymentConflictError, "telegram_stars_account_mismatch"
        )


async def _stage_plan_purchase_grant(
    session: AsyncSession,
    *,
    payment: Payment,
) -> None:
    if payment.id is None:
        raise PaymentServiceError(
            "payment must be flushed before staging subscription grant"
        )
    if payment.plan_code is None:
        raise PaymentConflictError("direct plan payment does not contain plan_code")

    grant = await _get_subscription_grant_by_payment_id(
        session,
        payment_id=payment.id,
        for_update=True,
    )
    if grant is not None:
        return

    account = await _load_account_for_update(session, account_id=payment.account_id)
    duration_days = _extract_plan_duration_days(payment)
    base_expires_at, target_expires_at = compute_paid_plan_window(
        account,
        duration_days=duration_days,
    )
    grant = SubscriptionGrant(
        account_id=payment.account_id,
        payment_id=payment.id,
        purchase_source=PurchaseSource.DIRECT_PAYMENT.value,
        reference_type="payment",
        reference_id=str(payment.id),
        plan_code=payment.plan_code,
        amount=payment.amount,
        currency=payment.currency,
        duration_days=duration_days,
        base_expires_at=base_expires_at,
        target_expires_at=target_expires_at,
    )
    session.add(grant)
    await session.flush()
    await append_account_event(
        session,
        account_id=payment.account_id,
        event_type="subscription.direct_payment.staged",
        source="system",
        payload={
            "payment_id": payment.id,
            "subscription_grant_id": grant.id,
            "provider": payment.provider.value,
            "plan_code": grant.plan_code,
            "amount": grant.amount,
            "currency": grant.currency,
            "duration_days": grant.duration_days,
            "target_expires_at": grant.target_expires_at.isoformat(),
        },
    )


async def _finalize_wallet_topup_payment(
    session: AsyncSession,
    *,
    payment_id: int,
) -> bool:
    payment = await _get_payment_by_id(session, payment_id=payment_id, for_update=True)
    if payment is None:
        raise PaymentServiceError(f"Payment not found: {payment_id}")
    if payment.finalized_at is not None:
        return False

    ledger_entry = await apply_credit_in_transaction(
        session,
        account_id=payment.account_id,
        amount=payment.amount,
        entry_type=LedgerEntryType.TOPUP_PAYMENT,
        reference_type="payment",
        reference_id=str(payment.id),
        comment=f"YooKassa payment {payment.provider_payment_id}",
        idempotency_key=f"payment:{payment.provider.value}:{payment.provider_payment_id}:credit",
    )
    payment.finalized_at = _utcnow()
    await _append_payment_account_event(
        session,
        payment=payment,
        event_type="payment.topup.applied",
        source="system",
        payload={
            "ledger_entry_id": ledger_entry.id,
            "finalized_at": payment.finalized_at.isoformat(),
        },
    )
    await notify_payment_succeeded(session, payment=payment)
    await session.commit()
    await clear_account_cache(payment.account_id)
    return True


async def _finalize_direct_plan_purchase(
    session: AsyncSession,
    *,
    payment_id: int,
) -> bool:
    payment = await _get_payment_by_id(session, payment_id=payment_id, for_update=True)
    if payment is None:
        raise PaymentServiceError(f"Payment not found: {payment_id}")
    if payment.finalized_at is not None:
        return False
    if payment.plan_code is None:
        raise PaymentConflictError("direct plan payment does not contain plan_code")

    grant = await _get_subscription_grant_by_payment_id(
        session,
        payment_id=payment.id,
        for_update=True,
    )
    if grant is None:
        raise PaymentServiceError(
            f"Subscription grant not found for payment {payment.id}"
        )

    account = await _load_account_for_update(session, account_id=payment.account_id)
    try:
        await apply_paid_purchase(
            account,
            source=PurchaseSource.DIRECT_PAYMENT,
            target_expires_at=grant.target_expires_at,
        )
        await apply_first_referral_reward_for_grant(
            session,
            grant=grant,
        )
    except RemnawaveSyncError as exc:
        await session.rollback()
        raise PaymentGatewayError(str(exc)) from exc

    grant.applied_at = _utcnow()
    await append_account_event(
        session,
        account_id=payment.account_id,
        event_type="subscription.direct_payment.applied",
        source="system",
        payload={
            "payment_id": payment.id,
            "subscription_grant_id": grant.id,
            "provider": payment.provider.value,
            "plan_code": grant.plan_code,
            "amount": grant.amount,
            "currency": grant.currency,
            "duration_days": grant.duration_days,
            "target_expires_at": grant.target_expires_at.isoformat(),
            "applied_at": grant.applied_at.isoformat(),
        },
    )
    await mark_promo_redemption_applied(
        session,
        reference_type=PAYMENT_REFERENCE_TYPE,
        reference_id=str(payment.id),
        payment_id=payment.id,
        subscription_grant_id=grant.id,
    )
    payment.finalized_at = _utcnow()
    await notify_payment_succeeded(session, payment=payment)
    await session.commit()
    await clear_account_cache(payment.account_id)
    return True


async def process_payment_webhook(
    session: AsyncSession,
    *,
    gateway: PaymentGateway,
    raw_body: bytes,
    headers: Mapping[str, str],
) -> PaymentWebhookProcessResult:
    event = await gateway.parse_webhook(raw_body=raw_body, headers=headers)
    if event.provider == PaymentProvider.TELEGRAM_STARS:
        await _validate_telegram_stars_actor(session, event=event)

    duplicate_event = False
    existing_event = await _get_payment_event_by_provider_event_id(
        session,
        provider=event.provider,
        provider_event_id=event.provider_event_id,
    )
    if existing_event is None:
        payment = await _get_payment_by_provider_payment_id(
            session,
            provider=event.provider,
            provider_payment_id=event.provider_payment_id,
            for_update=True,
        )
        if payment is None:
            payment = Payment(
                account_id=event.account_id,
                provider=event.provider,
                flow_type=event.flow_type,
                status=event.status,
                amount=event.amount,
                currency=event.currency,
                provider_payment_id=event.provider_payment_id,
                external_reference=event.external_reference,
                raw_payload=event.raw_payload,
                finalized_at=(
                    _utcnow()
                    if _should_finalize_payment(
                        flow_type=event.flow_type, status=event.status
                    )
                    else None
                ),
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
            amount=event.amount,
            currency=event.currency,
            raw_payload=event.raw_payload or {},
            processed_at=_utcnow(),
        )
        session.add(payment_event)

        if (
            event.status == PaymentStatus.SUCCEEDED
            and payment.flow_type == PaymentFlowType.DIRECT_PLAN_PURCHASE
        ):
            await _stage_plan_purchase_grant(session, payment=payment)
        elif event.status in FINAL_FAILED_PAYMENT_STATUSES:
            await notify_payment_failed(session, payment=payment, status=event.status)
            await _append_payment_account_event(
                session,
                payment=payment,
                event_type="payment.finalized",
                source="webhook",
                outcome="failure",
                payload={
                    "final_status": event.status.value,
                    "finalized_at": None
                    if payment.finalized_at is None
                    else payment.finalized_at.isoformat(),
                },
            )

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            if "uq_payment_events_provider_event_id" in str(exc):
                duplicate_event = True
            else:
                raise
    else:
        duplicate_event = True

    payment = await _get_payment_by_provider_payment_id(
        session,
        provider=event.provider,
        provider_payment_id=event.provider_payment_id,
    )
    if payment is None:
        raise PaymentServiceError(
            f"Payment not found for event {event.provider_event_id}"
        )

    ledger_applied = False
    subscription_applied = False
    if payment.status == PaymentStatus.SUCCEEDED and payment.finalized_at is None:
        if payment.flow_type == PaymentFlowType.WALLET_TOPUP:
            ledger_applied = await _finalize_wallet_topup_payment(
                session, payment_id=payment.id
            )
        elif payment.flow_type == PaymentFlowType.DIRECT_PLAN_PURCHASE:
            subscription_applied = await _finalize_direct_plan_purchase(
                session,
                payment_id=payment.id,
            )

    if duplicate_event:
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
        duplicate=duplicate_event,
        ledger_applied=ledger_applied,
        subscription_applied=subscription_applied,
    )


async def process_yookassa_webhook(
    session: AsyncSession,
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
) -> PaymentWebhookProcessResult:
    return await process_payment_webhook(
        session,
        gateway=get_yookassa_gateway(),
        raw_body=raw_body,
        headers=headers,
    )


async def process_telegram_stars_webhook(
    session: AsyncSession,
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
) -> PaymentWebhookProcessResult:
    return await process_payment_webhook(
        session,
        gateway=get_telegram_stars_gateway(),
        raw_body=raw_body,
        headers=headers,
    )
