from datetime import UTC, datetime
import httpx
import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import settings
from app.domain.payments import (
    CreatePaymentIntentCommand,
    PaymentFlowType,
    PaymentProvider,
    PaymentStatus,
)
from app.services.payments import (
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
    TelegramStarsGateway,
    YooKassaGateway,
    _as_db_naive_utc,
    _build_telegram_stars_invoice_payload,
    _extract_confirmation_url,
    _format_integer_amount,
    _format_rub_amount,
    _get_pending_ttl_seconds,
    _map_yookassa_status,
    _normalize_datetime,
    _normalize_json_payload,
    _parse_iso_datetime,
    _parse_telegram_stars_invoice_payload,
    _require_integer_amount,
    _resolve_pending_payment_expires_at,
)


class PaymentHelpersTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_webapp_url = settings.webapp_url
        self._original_api_token = settings.api_token
        self._original_yookassa_ttl = settings.payment_pending_ttl_seconds_yookassa
        self._original_stars_ttl = settings.payment_pending_ttl_seconds_telegram_stars
        settings.webapp_url = "https://webapp.test"
        settings.api_token = "internal-token"
        settings.payment_pending_ttl_seconds_yookassa = 90
        settings.payment_pending_ttl_seconds_telegram_stars = 120

    def tearDown(self) -> None:
        settings.webapp_url = self._original_webapp_url
        settings.api_token = self._original_api_token
        settings.payment_pending_ttl_seconds_yookassa = self._original_yookassa_ttl
        settings.payment_pending_ttl_seconds_telegram_stars = self._original_stars_ttl

    def test_parse_iso_datetime_supports_none_datetime_and_string(self) -> None:
        now = datetime.now(UTC)
        self.assertIsNone(_parse_iso_datetime(None))
        self.assertEqual(_parse_iso_datetime(""), None)
        self.assertIs(_parse_iso_datetime(now), now)
        self.assertEqual(
            _parse_iso_datetime("2026-05-11T10:15:00Z"),
            datetime(2026, 5, 11, 10, 15, tzinfo=UTC),
        )

        with self.assertRaises(PaymentGatewayError):
            _parse_iso_datetime(123)

    def test_normalize_json_payload_validates_shape(self) -> None:
        self.assertEqual(_normalize_json_payload(None, field_name="payload"), None)
        self.assertEqual(
            _normalize_json_payload({"ok": True}, field_name="payload"),
            {"ok": True},
        )
        self.assertEqual(
            _normalize_json_payload('{"ok": true}', field_name="payload"),
            {"ok": True},
        )

        with self.assertRaises(PaymentGatewayError):
            _normalize_json_payload("[1,2,3]", field_name="payload")
        with self.assertRaises(PaymentGatewayError):
            _normalize_json_payload("{bad", field_name="payload")
        with self.assertRaises(PaymentGatewayError):
            _normalize_json_payload(42, field_name="payload")

    def test_amount_helpers_validate_positive_integer_values(self) -> None:
        self.assertEqual(_require_integer_amount("100", currency="RUB"), 100)
        self.assertEqual(_format_rub_amount(1200), "1200.00")
        self.assertEqual(_format_integer_amount(10), 10)

        with self.assertRaises(PaymentGatewayError):
            _require_integer_amount("10.5", currency="RUB")
        with self.assertRaises(PaymentGatewayError):
            _require_integer_amount("abc", currency="RUB")
        with self.assertRaises(PaymentGatewayError):
            _require_integer_amount(100, currency="")
        with self.assertRaises(PaymentGatewayError):
            _format_rub_amount(0)
        with self.assertRaises(PaymentGatewayError):
            _format_integer_amount(0)

    def test_yookassa_status_and_confirmation_helpers(self) -> None:
        self.assertEqual(_map_yookassa_status("pending"), PaymentStatus.PENDING)
        self.assertEqual(
            _map_yookassa_status("waiting_for_capture"),
            PaymentStatus.REQUIRES_ACTION,
        )
        self.assertEqual(_map_yookassa_status("succeeded"), PaymentStatus.SUCCEEDED)
        self.assertEqual(_map_yookassa_status("canceled"), PaymentStatus.CANCELLED)
        self.assertEqual(
            _extract_confirmation_url(
                SimpleNamespace(
                    confirmation=SimpleNamespace(
                        confirmation_url="https://pay.test/confirm"
                    )
                )
            ),
            "https://pay.test/confirm",
        )
        self.assertIsNone(_extract_confirmation_url(SimpleNamespace(confirmation=None)))

        with self.assertRaises(PaymentGatewayError):
            _map_yookassa_status("unknown")

    def test_datetime_and_pending_expiry_helpers(self) -> None:
        naive = datetime(2026, 5, 11, 12, 0, 0)
        aware = datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC)
        self.assertEqual(_normalize_datetime(naive), aware)
        self.assertEqual(_normalize_datetime(aware), aware)
        self.assertEqual(_as_db_naive_utc(aware).tzinfo, None)
        self.assertEqual(
            _get_pending_ttl_seconds(PaymentProvider.YOOKASSA),
            90,
        )
        self.assertEqual(
            _get_pending_ttl_seconds(PaymentProvider.TELEGRAM_STARS),
            120,
        )
        expires_at = _resolve_pending_payment_expires_at(
            provider=PaymentProvider.YOOKASSA,
            snapshot_expires_at=aware,
        )
        self.assertEqual(expires_at, aware)
        self.assertEqual(
            _resolve_pending_payment_expires_at(
                provider=PaymentProvider.YOOKASSA,
                snapshot_expires_at=None,
                existing_expires_at=aware,
            ),
            aware,
        )
        generated = _resolve_pending_payment_expires_at(
            provider=PaymentProvider.YOOKASSA,
            snapshot_expires_at=None,
            existing_expires_at=None,
        )
        self.assertIsNotNone(generated)

    def test_yookassa_gateway_validates_configuration_and_metadata(self) -> None:
        command = CreatePaymentIntentCommand(
            account_id=uuid.uuid4(),
            flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
            amount=1000,
            currency="RUB",
            plan_code="plan_1m",
            idempotency_key="idem-1",
            metadata={"custom": "value"},
        )
        gateway = YooKassaGateway(shop_id="shop", secret_key="secret")

        metadata = gateway._build_metadata(command)
        self.assertEqual(metadata["rm_plan_code"], "plan_1m")
        self.assertEqual(metadata["rm_external_reference"], "idem-1")
        self.assertEqual(metadata["custom"], "value")
        self.assertEqual(gateway._resolve_return_url(command), "https://webapp.test")

        no_secret_gateway = YooKassaGateway(shop_id="", secret_key="")
        with self.assertRaises(PaymentGatewayConfigurationError):
            no_secret_gateway._assert_configured()

        no_url_command = CreatePaymentIntentCommand(
            account_id=uuid.uuid4(),
            flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
            amount=1000,
            currency="RUB",
        )
        settings.webapp_url = ""
        with self.assertRaises(PaymentGatewayError):
            gateway._resolve_return_url(no_url_command)

    def test_yookassa_gateway_validates_snapshot_metadata(self) -> None:
        gateway = YooKassaGateway(shop_id="shop", secret_key="secret")
        account_id = uuid.uuid4()
        response = SimpleNamespace(
            status="pending",
            id="payment-1",
            metadata={
                "rm_account_id": str(account_id),
                "rm_flow_type": PaymentFlowType.DIRECT_PLAN_PURCHASE.value,
                "rm_external_reference": "idem-1",
            },
            amount=SimpleNamespace(value="1000", currency="RUB"),
            confirmation=SimpleNamespace(confirmation_url="https://pay.test/confirm"),
            expires_at="2026-05-11T10:15:00Z",
            json=lambda: {"id": "payment-1"},
        )

        snapshot = gateway._snapshot_from_payment_response(response)
        self.assertEqual(snapshot.account_id, account_id)
        self.assertEqual(snapshot.provider_payment_id, "payment-1")

        bad_response = SimpleNamespace(
            status="pending",
            id="payment-1",
            metadata={},
            amount=SimpleNamespace(value="1000", currency="RUB"),
            confirmation=None,
            expires_at=None,
            json=lambda: {"id": "payment-1"},
        )
        with self.assertRaises(PaymentGatewayError):
            gateway._snapshot_from_payment_response(bad_response)

    def test_yookassa_create_payment_intent_sync_rejects_non_rub(self) -> None:
        gateway = YooKassaGateway(shop_id="shop", secret_key="secret")
        command = CreatePaymentIntentCommand(
            account_id=uuid.uuid4(),
            flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
            amount=1000,
            currency="XTR",
        )

        with self.assertRaises(PaymentGatewayError):
            gateway._create_payment_intent_sync(command, "idem-1")

    def test_telegram_stars_payload_helpers_round_trip(self) -> None:
        account_id = uuid.uuid4()
        payload = _build_telegram_stars_invoice_payload(
            account_id=account_id,
            flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
            payment_reference="idem-1",
        )
        flow_type, parsed_account_id = _parse_telegram_stars_invoice_payload(payload)
        self.assertEqual(flow_type, PaymentFlowType.DIRECT_PLAN_PURCHASE)
        self.assertEqual(parsed_account_id, account_id)

        with self.assertRaises(PaymentGatewayError):
            _parse_telegram_stars_invoice_payload("bad-payload")

    def test_telegram_stars_gateway_validates_configuration_and_payload(self) -> None:
        gateway = TelegramStarsGateway(bot_token="")
        with self.assertRaises(PaymentGatewayConfigurationError):
            gateway._assert_configured()

        settings.api_token = ""
        gateway = TelegramStarsGateway(bot_token="bot-token")
        with self.assertRaises(PaymentGatewayConfigurationError):
            gateway._assert_configured()

        settings.api_token = "internal-token"
        command = CreatePaymentIntentCommand(
            account_id=uuid.uuid4(),
            flow_type=PaymentFlowType.WALLET_TOPUP,
            amount=1000,
            currency="RUB",
        )
        gateway = TelegramStarsGateway(bot_token="bot-token")
        with self.assertRaises(PaymentGatewayError):
            self._run_async(gateway.create_payment_intent(command))

    def test_telegram_stars_parse_webhook_validates_payload(self) -> None:
        gateway = TelegramStarsGateway(bot_token="bot-token")
        with self.assertRaises(PaymentGatewayError):
            self._run_async(gateway.parse_webhook(raw_body=b"{bad", headers={}))

        with self.assertRaises(PaymentGatewayError):
            self._run_async(
                gateway.parse_webhook(
                    raw_body=json.dumps({"event_type": "unknown"}).encode(),
                    headers={},
                )
            )

    def test_telegram_stars_call_bot_api_maps_transport_and_payload_errors(
        self,
    ) -> None:
        gateway = TelegramStarsGateway(bot_token="bot-token")

        class TransportClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                del exc_type, exc, tb
                return None

            async def post(self, url, json):
                del url, json
                raise httpx.ReadTimeout("timeout")

        with patch(
            "app.services.payments.httpx.AsyncClient",
            return_value=TransportClient(),
        ):
            with self.assertRaises(PaymentGatewayError):
                self._run_async(gateway._call_bot_api("createInvoiceLink", {}))

        class InvalidJsonResponse:
            status_code = 200

            def json(self):
                raise json.JSONDecodeError("bad", "", 0)

        class InvalidJsonClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                del exc_type, exc, tb
                return None

            async def post(self, url, json):
                del url, json
                return InvalidJsonResponse()

        with patch(
            "app.services.payments.httpx.AsyncClient",
            return_value=InvalidJsonClient(),
        ):
            with self.assertRaises(PaymentGatewayError):
                self._run_async(gateway._call_bot_api("createInvoiceLink", {}))

        class ErrorResponse:
            status_code = 400

            def json(self):
                return {"ok": False, "description": "bad request"}

        class ErrorClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                del exc_type, exc, tb
                return None

            async def post(self, url, json):
                del url, json
                return ErrorResponse()

        with patch(
            "app.services.payments.httpx.AsyncClient",
            return_value=ErrorClient(),
        ):
            with self.assertRaises(PaymentGatewayError):
                self._run_async(gateway._call_bot_api("createInvoiceLink", {}))

        class UnexpectedResultResponse:
            status_code = 200

            def json(self):
                return {"ok": True, "result": 123}

        class UnexpectedResultClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                del exc_type, exc, tb
                return None

            async def post(self, url, json):
                del url, json
                return UnexpectedResultResponse()

        with patch(
            "app.services.payments.httpx.AsyncClient",
            return_value=UnexpectedResultClient(),
        ):
            with self.assertRaises(PaymentGatewayError):
                self._run_async(gateway._call_bot_api("createInvoiceLink", {}))

    def _run_async(self, awaitable):
        import asyncio

        return asyncio.run(awaitable)
