import json
import tempfile
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_account
from app.db.base import Base
from app.db.models import (
    Account,
    AccountStatus,
    LedgerEntry,
    LedgerEntryType,
    Notification,
    NotificationType,
    Payment,
    PaymentEvent,
    SubscriptionGrant,
)
from app.db.session import get_session
from app.main import create_app
from app.services.payments import (
    CreatePaymentIntentCommand,
    PaymentIntentSnapshot,
    PaymentFlowType,
    PaymentGatewayError,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookEvent,
    TelegramStarsGateway,
    YooKassaGateway,
    _build_telegram_stars_invoice_payload,
    expire_stale_payments,
    get_telegram_stars_gateway,
    get_yookassa_gateway,
    reconcile_pending_yookassa_payments,
)


class DummyYooKassaResponse:
    def __init__(
        self,
        *,
        payment_id: str,
        status: str,
        amount_value: str,
        currency: str = "RUB",
        confirmation_url: str | None = "https://yookassa.test/confirm",
        expires_at: str | None = "2026-03-10T10:00:00Z",
    ) -> None:
        self.id = payment_id
        self.status = status
        self.amount = SimpleNamespace(value=amount_value, currency=currency)
        self.confirmation = (
            SimpleNamespace(confirmation_url=confirmation_url) if confirmation_url else None
        )
        self.expires_at = expires_at

    def json(self) -> str:
        return json.dumps({
            "id": self.id,
            "status": self.status,
            "amount": {
                "value": self.amount.value,
                "currency": self.amount.currency,
            },
        })


class YooKassaGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_payment_intent_maps_sdk_response(self) -> None:
        account_id = uuid.uuid4()
        gateway = YooKassaGateway(
            shop_id="shop-id",
            secret_key="secret-key",
            api_url="https://api.yookassa.ru/v3",
        )
        command = CreatePaymentIntentCommand(
            account_id=account_id,
            flow_type=PaymentFlowType.WALLET_TOPUP,
            amount=499,
            success_url="https://app.example.com/payments/return",
            description="Пополнение баланса",
            idempotency_key="pay-123",
        )

        with patch("app.services.payments.YooKassaPayment.create") as create_payment:
            create_payment.return_value = DummyYooKassaResponse(
                payment_id="2d10f42f-000f-5000-9000-1a2b3c4d5e6f",
                status="pending",
                amount_value="499.00",
            )

            snapshot = await gateway.create_payment_intent(command)

        self.assertEqual(snapshot.provider, PaymentProvider.YOOKASSA)
        self.assertEqual(snapshot.flow_type, PaymentFlowType.WALLET_TOPUP)
        self.assertEqual(snapshot.account_id, account_id)
        self.assertEqual(snapshot.status, PaymentStatus.PENDING)
        self.assertEqual(snapshot.amount, 499)
        self.assertEqual(snapshot.currency, "RUB")
        self.assertEqual(snapshot.provider_payment_id, "2d10f42f-000f-5000-9000-1a2b3c4d5e6f")
        self.assertEqual(snapshot.external_reference, "pay-123")
        self.assertEqual(snapshot.confirmation_url, "https://yookassa.test/confirm")
        self.assertIsInstance(snapshot.raw_payload, dict)
        self.assertEqual(snapshot.raw_payload["id"], "2d10f42f-000f-5000-9000-1a2b3c4d5e6f")

        create_payment.assert_called_once()
        params, idempotency_key = create_payment.call_args.args
        self.assertEqual(idempotency_key, "pay-123")
        self.assertEqual(params["amount"]["value"], "499.00")
        self.assertEqual(params["amount"]["currency"], "RUB")
        self.assertEqual(params["capture"], True)
        self.assertEqual(params["confirmation"]["type"], "redirect")
        self.assertEqual(
            params["confirmation"]["return_url"],
            "https://app.example.com/payments/return",
        )
        self.assertEqual(params["metadata"]["rm_account_id"], str(account_id))
        self.assertEqual(params["metadata"]["rm_flow_type"], "wallet_topup")
        self.assertEqual(params["metadata"]["rm_external_reference"], "pay-123")

    async def test_parse_webhook_maps_payment_succeeded(self) -> None:
        account_id = uuid.uuid4()
        gateway = YooKassaGateway(
            shop_id="shop-id",
            secret_key="secret-key",
        )
        payload = {
            "type": "notification",
            "event": "payment.succeeded",
            "object": {
                "id": "2419a771-000f-5000-9000-1edaf29243f2",
                "status": "succeeded",
                "paid": True,
                "amount": {
                    "value": "1000.00",
                    "currency": "RUB",
                },
                "metadata": {
                    "rm_account_id": str(account_id),
                    "rm_flow_type": "direct_plan_purchase",
                    "rm_external_reference": "purchase-1",
                },
            },
        }

        with patch("app.services.payments.YooKassaPayment.find_one") as find_payment:
            find_payment.return_value = DummyYooKassaResponse(
                payment_id="2419a771-000f-5000-9000-1edaf29243f2",
                status="succeeded",
                amount_value="1000.00",
            )
            find_payment.return_value.metadata = payload["object"]["metadata"]

            event = await gateway.parse_webhook(
                raw_body=json.dumps(payload).encode("utf-8"),
                headers={},
            )

        self.assertEqual(event.provider, PaymentProvider.YOOKASSA)
        self.assertEqual(event.provider_event_id, "payment.succeeded:2419a771-000f-5000-9000-1edaf29243f2")
        self.assertEqual(event.provider_payment_id, "2419a771-000f-5000-9000-1edaf29243f2")
        self.assertEqual(event.status, PaymentStatus.SUCCEEDED)
        self.assertEqual(event.amount, 1000)
        self.assertEqual(event.currency, "RUB")
        self.assertEqual(event.flow_type, PaymentFlowType.DIRECT_PLAN_PURCHASE)
        self.assertEqual(event.account_id, account_id)
        self.assertEqual(event.external_reference, "purchase-1")
        self.assertIsInstance(event.raw_payload, dict)
        self.assertEqual(event.raw_payload["id"], "2419a771-000f-5000-9000-1edaf29243f2")

    async def test_parse_webhook_rejects_missing_metadata(self) -> None:
        gateway = YooKassaGateway(
            shop_id="shop-id",
            secret_key="secret-key",
        )
        payload = {
            "type": "notification",
            "event": "payment.canceled",
            "object": {
                "id": "payment-1",
                "status": "canceled",
                "amount": {
                    "value": "100.00",
                    "currency": "RUB",
                },
                "metadata": {},
            },
        }

        with patch("app.services.payments.YooKassaPayment.find_one") as find_payment:
            find_payment.return_value = DummyYooKassaResponse(
                payment_id="payment-1",
                status="canceled",
                amount_value="100.00",
            )
            find_payment.return_value.metadata = {}

            with self.assertRaises(PaymentGatewayError):
                await gateway.parse_webhook(
                    raw_body=json.dumps(payload).encode("utf-8"),
                    headers={},
                )


class TelegramStarsGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_payment_intent_returns_invoice_link(self) -> None:
        account_id = uuid.uuid4()
        gateway = TelegramStarsGateway(bot_token="telegram-token", api_base_url="https://api.telegram.org")
        command = CreatePaymentIntentCommand(
            account_id=account_id,
            flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
            amount=85,
            currency="XTR",
            plan_code="plan_1m",
            idempotency_key="stars-85",
            description="Оплата тарифа 1 месяц",
            metadata={"rm_plan_name": "1 месяц"},
        )

        with patch.object(gateway, "_call_bot_api", return_value={"result": "https://t.me/invoice/test"}) as bot_api:
            with patch("app.services.payments.settings.api_token", "internal-token"):
                snapshot = await gateway.create_payment_intent(command)

        self.assertEqual(snapshot.provider, PaymentProvider.TELEGRAM_STARS)
        self.assertEqual(snapshot.amount, 85)
        self.assertEqual(snapshot.currency, "XTR")
        self.assertEqual(snapshot.confirmation_url, "https://t.me/invoice/test")
        self.assertTrue(snapshot.provider_payment_id.startswith("rmstars:dp:"))
        bot_api.assert_called_once()

    async def test_parse_webhook_maps_successful_payment(self) -> None:
        account_id = uuid.uuid4()
        invoice_payload = _build_telegram_stars_invoice_payload(
            account_id=account_id,
            flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
            payment_reference="stars-85",
        )
        gateway = TelegramStarsGateway(bot_token="telegram-token")

        event = await gateway.parse_webhook(
            raw_body=json.dumps(
                {
                    "event_type": "successful_payment",
                    "telegram_id": 758107031,
                    "currency": "XTR",
                    "total_amount": 85,
                    "invoice_payload": invoice_payload,
                    "telegram_payment_charge_id": "tg-charge-1",
                    "provider_payment_charge_id": "provider-charge-1",
                }
            ).encode("utf-8"),
            headers={},
        )

        self.assertEqual(event.provider, PaymentProvider.TELEGRAM_STARS)
        self.assertEqual(event.provider_event_id, "successful_payment:tg-charge-1")
        self.assertEqual(event.provider_payment_id, invoice_payload)
        self.assertEqual(event.status, PaymentStatus.SUCCEEDED)
        self.assertEqual(event.amount, 85)
        self.assertEqual(event.currency, "XTR")
        self.assertEqual(event.flow_type, PaymentFlowType.DIRECT_PLAN_PURCHASE)
        self.assertEqual(event.account_id, account_id)


class DummyCache:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def account_response_key(self, account_id: str) -> str:
        return f"account:{account_id}"

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._values.pop(key, None)


class FakeYooKassaGateway:
    provider = PaymentProvider.YOOKASSA

    def __init__(self) -> None:
        self._events: dict[str, PaymentWebhookEvent] = {}
        self._status_snapshots: dict[str, PaymentIntentSnapshot] = {}

    async def create_payment_intent(self, command: CreatePaymentIntentCommand):
        return SimpleNamespace(
            provider=PaymentProvider.YOOKASSA,
            flow_type=command.flow_type,
            account_id=command.account_id,
            status=PaymentStatus.PENDING,
            amount=command.amount,
            currency="RUB",
            provider_payment_id=f"yoopay-{command.idempotency_key or 'generated'}",
            external_reference=command.idempotency_key,
            confirmation_url="https://yookassa.test/confirm",
            expires_at=None,
            raw_payload={"provider_payment_id": f"yoopay-{command.idempotency_key or 'generated'}"},
        )

    async def parse_webhook(self, *, raw_body: bytes, headers):
        del headers
        payload = json.loads(raw_body)
        event_id = payload["event_id"]
        return self._events[event_id]

    def put_event(self, event_id: str, event: PaymentWebhookEvent) -> None:
        self._events[event_id] = event

    async def fetch_payment_snapshot(self, provider_payment_id: str) -> PaymentIntentSnapshot:
        return self._status_snapshots[provider_payment_id]

    def put_status_snapshot(self, snapshot: PaymentIntentSnapshot) -> None:
        self._status_snapshots[snapshot.provider_payment_id] = snapshot


class FakeTelegramStarsGateway:
    provider = PaymentProvider.TELEGRAM_STARS

    def __init__(self) -> None:
        self._events: dict[str, PaymentWebhookEvent] = {}

    async def create_payment_intent(self, command: CreatePaymentIntentCommand):
        provider_payment_id = _build_telegram_stars_invoice_payload(
            account_id=command.account_id,
            flow_type=command.flow_type,
            payment_reference=command.idempotency_key or "generated",
        )
        return SimpleNamespace(
            provider=PaymentProvider.TELEGRAM_STARS,
            flow_type=command.flow_type,
            account_id=command.account_id,
            status=PaymentStatus.PENDING,
            amount=command.amount,
            currency="XTR",
            provider_payment_id=provider_payment_id,
            external_reference=command.idempotency_key,
            confirmation_url=f"https://t.me/invoice/{command.idempotency_key or 'generated'}",
            expires_at=None,
            raw_payload={"provider_payment_id": provider_payment_id},
        )

    async def parse_webhook(self, *, raw_body: bytes, headers):
        del headers
        payload = json.loads(raw_body)
        event_id = payload["event_id"]
        return self._events[event_id]

    def put_event(self, event_id: str, event: PaymentWebhookEvent) -> None:
        self._events[event_id] = event


class PaymentFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "payments.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._current_account_id: uuid.UUID | None = None
        self._fake_gateway = FakeYooKassaGateway()
        self._fake_stars_gateway = FakeTelegramStarsGateway()

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module
        import app.services.payments as payments_service

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()

        self._payments_service = payments_service
        self._original_gateway_factory = payments_service.get_yookassa_gateway
        self._original_stars_gateway_factory = payments_service.get_telegram_stars_gateway
        self._original_api_token = payments_service.settings.api_token
        self._original_yookassa_pending_ttl_seconds = payments_service.settings.payment_pending_ttl_seconds_yookassa
        self._original_telegram_stars_pending_ttl_seconds = (
            payments_service.settings.payment_pending_ttl_seconds_telegram_stars
        )
        self._original_reconcile_yookassa_min_age_seconds = (
            payments_service.settings.payment_reconcile_yookassa_min_age_seconds
        )
        payments_service.get_yookassa_gateway = lambda: self._fake_gateway
        payments_service.get_telegram_stars_gateway = lambda: self._fake_stars_gateway
        payments_service.settings.api_token = "internal-token"
        payments_service.settings.payment_pending_ttl_seconds_yookassa = 1800
        payments_service.settings.payment_pending_ttl_seconds_telegram_stars = 600
        payments_service.settings.payment_reconcile_yookassa_min_age_seconds = 0

        self.app = create_app()

        async def override_get_session():
            async with self._session_factory() as session:
                yield session

        async def override_get_current_account():
            if self._current_account_id is None:
                raise AssertionError("current account is not configured for test request")

            async with self._session_factory() as session:
                account = await session.get(Account, self._current_account_id)
                if account is None:
                    raise AssertionError(f"account not found: {self._current_account_id}")
                return account

        self.app.dependency_overrides[get_session] = override_get_session
        self.app.dependency_overrides[get_current_account] = override_get_current_account
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        self._payments_service.get_yookassa_gateway = self._original_gateway_factory
        self._payments_service.get_telegram_stars_gateway = self._original_stars_gateway_factory
        self._payments_service.settings.api_token = self._original_api_token
        self._payments_service.settings.payment_pending_ttl_seconds_yookassa = (
            self._original_yookassa_pending_ttl_seconds
        )
        self._payments_service.settings.payment_pending_ttl_seconds_telegram_stars = (
            self._original_telegram_stars_pending_ttl_seconds
        )
        self._payments_service.settings.payment_reconcile_yookassa_min_age_seconds = (
            self._original_reconcile_yookassa_min_age_seconds
        )
        self._cache_module._cache = self._original_cache
        await self._engine.dispose()
        self._tmpdir.cleanup()

    async def _create_account(self, **values) -> Account:
        async with self._session_factory() as session:
            account = Account(**values)
            session.add(account)
            await session.commit()
            await session.refresh(account)
            return account

    async def _get_account(self, account_id: uuid.UUID) -> Account | None:
        async with self._session_factory() as session:
            return await session.get(Account, account_id)

    async def _get_payment(self, provider_payment_id: str) -> Payment | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Payment).where(Payment.provider_payment_id == provider_payment_id)
            )
            return result.scalar_one_or_none()

    async def _get_ledger_entries(self, account_id: uuid.UUID) -> list[LedgerEntry]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(LedgerEntry)
                .where(LedgerEntry.account_id == account_id)
                .order_by(LedgerEntry.id.asc())
            )
            return list(result.scalars().all())

    async def _get_subscription_grants(self, account_id: uuid.UUID) -> list[SubscriptionGrant]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SubscriptionGrant)
                .where(SubscriptionGrant.account_id == account_id)
                .order_by(SubscriptionGrant.id.asc())
            )
            return list(result.scalars().all())

    async def _get_notifications(self, account_id: uuid.UUID) -> list[Notification]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Notification)
                .where(Notification.account_id == account_id)
                .order_by(Notification.id.asc())
            )
            return list(result.scalars().all())

    async def _create_direct_plan_payment(self, account: Account) -> None:
        response = await self.client.post(
            "/api/v1/payments/yookassa/plans/plan_1m",
            json={
                "success_url": "https://app.example.com/payments/return",
                "idempotency_key": "plan-1m",
            },
        )
        self.assertEqual(response.status_code, 200)

    async def test_create_yookassa_topup_endpoint_persists_pending_payment(self) -> None:
        account = await self._create_account(balance=0, email="payer@example.com")
        self._current_account_id = account.id

        response = await self.client.post(
            "/api/v1/payments/yookassa/topup",
            json={
                "amount_rub": 500,
                "success_url": "https://app.example.com/payments/return",
                "idempotency_key": "topup-500",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["amount"], 500)
        self.assertEqual(body["provider_payment_id"], "yoopay-topup-500")
        self.assertEqual(body["external_reference"], "topup-500")

        stored_payment = await self._get_payment("yoopay-topup-500")
        self.assertIsNotNone(stored_payment)
        assert stored_payment is not None
        self.assertEqual(stored_payment.account_id, account.id)
        self.assertEqual(stored_payment.status, PaymentStatus.PENDING)
        self.assertEqual(stored_payment.amount, 500)
        self.assertIsNotNone(stored_payment.expires_at)

    async def test_create_yookassa_topup_rejects_blocked_account(self) -> None:
        account = await self._create_account(
            balance=0,
            email="blocked-payer@example.com",
            status=AccountStatus.BLOCKED,
        )
        self._current_account_id = account.id

        response = await self.client.post(
            "/api/v1/payments/yookassa/topup",
            json={
                "amount_rub": 500,
                "success_url": "https://app.example.com/payments/return",
                "idempotency_key": "blocked-topup-500",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "blocked accounts cannot create payments")
        self.assertIsNone(await self._get_payment("yoopay-blocked-topup-500"))

    async def test_list_subscription_plans_returns_backend_catalog(self) -> None:
        account = await self._create_account(email="plans@example.com")
        self._current_account_id = account.id

        response = await self.client.get("/api/v1/payments/plans")
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertGreaterEqual(len(body), 3)
        self.assertEqual(body[0]["code"], "plan_1m")
        self.assertEqual(body[0]["price_rub"], 299)
        self.assertIsInstance(body[0]["price_stars"], int)
        self.assertGreater(body[0]["price_stars"], 0)
        self.assertEqual(body[0]["duration_days"], 30)
        self.assertTrue(body[0]["popular"])

    async def test_get_payment_status_returns_current_state_for_account(self) -> None:
        account = await self._create_account(balance=0, email="status@example.com")
        self._current_account_id = account.id

        create_response = await self.client.post(
            "/api/v1/payments/yookassa/topup",
            json={
                "amount_rub": 500,
                "success_url": "https://app.example.com/payments/return",
                "idempotency_key": "topup-status-500",
            },
        )
        self.assertEqual(create_response.status_code, 200)

        response = await self.client.get(
            "/api/v1/payments/status",
            params={
                "provider": "yookassa",
                "provider_payment_id": "yoopay-topup-status-500",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["provider"], "yookassa")
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["amount"], 500)
        self.assertIsNotNone(body["expires_at"])
        self.assertIsNone(body["finalized_at"])

    async def test_list_payments_can_return_only_active_items_for_current_account(self) -> None:
        account = await self._create_account(balance=0, email="list@example.com")
        other_account = await self._create_account(balance=0, email="other@example.com")
        self._current_account_id = account.id

        async with self._session_factory() as session:
            session.add_all(
                [
                    Payment(
                        account_id=account.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.WALLET_TOPUP,
                        status=PaymentStatus.PENDING,
                        amount=500,
                        currency="RUB",
                        provider_payment_id="yoopay-active-500",
                        confirmation_url="https://pay.example/1",
                    ),
                    Payment(
                        account_id=account.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                        status=PaymentStatus.SUCCEEDED,
                        amount=299,
                        currency="RUB",
                        provider_payment_id="yoopay-done-299",
                    ),
                    Payment(
                        account_id=other_account.id,
                        provider=PaymentProvider.YOOKASSA,
                        flow_type=PaymentFlowType.WALLET_TOPUP,
                        status=PaymentStatus.PENDING,
                        amount=900,
                        currency="RUB",
                        provider_payment_id="yoopay-foreign-900",
                        confirmation_url="https://pay.example/2",
                    ),
                ]
            )
            await session.commit()

        response = await self.client.get(
            "/api/v1/payments",
            params={"active_only": "true"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["total"], 1)
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["provider_payment_id"], "yoopay-active-500")
        self.assertEqual(body["items"][0]["status"], "pending")

    async def test_yookassa_webhook_succeeded_credits_balance_once(self) -> None:
        account = await self._create_account(balance=100, email="payer@example.com")
        self._current_account_id = account.id

        create_response = await self.client.post(
            "/api/v1/payments/yookassa/topup",
            json={
                "amount_rub": 500,
                "success_url": "https://app.example.com/payments/return",
                "idempotency_key": "topup-500",
            },
        )
        self.assertEqual(create_response.status_code, 200)

        self._fake_gateway.put_event(
            "event-1",
            PaymentWebhookEvent(
                provider=PaymentProvider.YOOKASSA,
                provider_event_id="payment.succeeded:yoopay-topup-500",
                provider_payment_id="yoopay-topup-500",
                status=PaymentStatus.SUCCEEDED,
                amount=500,
                currency="RUB",
                flow_type=PaymentFlowType.WALLET_TOPUP,
                account_id=account.id,
                external_reference="topup-500",
                raw_payload={"status": "succeeded"},
            ),
        )

        response = await self.client.post(
            "/api/v1/webhooks/payments/yookassa",
            content=json.dumps({"event_id": "event-1"}),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["duplicate"], False)
        self.assertEqual(body["ledger_applied"], True)
        self.assertEqual(body["status"], "succeeded")

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 600)

        stored_payment = await self._get_payment("yoopay-topup-500")
        self.assertIsNotNone(stored_payment)
        assert stored_payment is not None
        self.assertEqual(stored_payment.status, PaymentStatus.SUCCEEDED)
        self.assertIsNotNone(stored_payment.finalized_at)

        entries = await self._get_ledger_entries(account.id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].entry_type, LedgerEntryType.TOPUP_PAYMENT)
        self.assertEqual(entries[0].amount, 500)

        notifications = await self._get_notifications(account.id)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].type, NotificationType.PAYMENT_SUCCEEDED)
        self.assertEqual(notifications[0].payload["payment_id"], stored_payment.id)

        duplicate_response = await self.client.post(
            "/api/v1/webhooks/payments/yookassa",
            content=json.dumps({"event_id": "event-1"}),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(duplicate_response.status_code, 200)
        duplicate_body = duplicate_response.json()
        self.assertEqual(duplicate_body["duplicate"], True)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 600)
        self.assertEqual(len(await self._get_notifications(account.id)), 1)

    async def test_yookassa_webhook_cancelled_creates_failure_notification(self) -> None:
        account = await self._create_account(balance=100, email="payer-cancel@example.com")
        self._current_account_id = account.id

        create_response = await self.client.post(
            "/api/v1/payments/yookassa/topup",
            json={
                "amount_rub": 500,
                "success_url": "https://app.example.com/payments/return",
                "idempotency_key": "topup-cancelled-500",
            },
        )
        self.assertEqual(create_response.status_code, 200)

        self._fake_gateway.put_event(
            "event-cancelled-1",
            PaymentWebhookEvent(
                provider=PaymentProvider.YOOKASSA,
                provider_event_id="payment.canceled:yoopay-topup-cancelled-500",
                provider_payment_id="yoopay-topup-cancelled-500",
                status=PaymentStatus.CANCELLED,
                amount=500,
                currency="RUB",
                flow_type=PaymentFlowType.WALLET_TOPUP,
                account_id=account.id,
                external_reference="topup-cancelled-500",
                raw_payload={"status": "canceled"},
            ),
        )

        response = await self.client.post(
            "/api/v1/webhooks/payments/yookassa",
            content=json.dumps({"event_id": "event-cancelled-1"}),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")
        self.assertFalse(response.json()["ledger_applied"])

        stored_payment = await self._get_payment("yoopay-topup-cancelled-500")
        self.assertIsNotNone(stored_payment)
        assert stored_payment is not None
        self.assertEqual(stored_payment.status, PaymentStatus.CANCELLED)
        self.assertIsNotNone(stored_payment.finalized_at)

        self.assertEqual(len(await self._get_ledger_entries(account.id)), 0)

        notifications = await self._get_notifications(account.id)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].type, NotificationType.PAYMENT_FAILED)
        self.assertEqual(notifications[0].payload["status"], "cancelled")

    async def test_yookassa_webhook_cancelled_orphan_payment_does_not_fail(self) -> None:
        account = await self._create_account(balance=100, email="payer-orphan@example.com")
        self._current_account_id = account.id

        create_response = await self.client.post(
            "/api/v1/payments/yookassa/topup",
            json={
                "amount_rub": 1000,
                "success_url": "https://app.example.com/payments/return",
                "idempotency_key": "topup-orphan-1000",
            },
        )
        self.assertEqual(create_response.status_code, 200)

        async with self._session_factory() as session:
            stored_account = await session.get(Account, account.id)
            self.assertIsNotNone(stored_account)
            assert stored_account is not None
            await session.delete(stored_account)
            await session.commit()

        self._fake_gateway.put_event(
            "event-cancelled-orphan-1",
            PaymentWebhookEvent(
                provider=PaymentProvider.YOOKASSA,
                provider_event_id="payment.canceled:yoopay-topup-orphan-1000",
                provider_payment_id="yoopay-topup-orphan-1000",
                status=PaymentStatus.CANCELLED,
                amount=1000,
                currency="RUB",
                flow_type=PaymentFlowType.WALLET_TOPUP,
                account_id=account.id,
                external_reference="topup-orphan-1000",
                raw_payload={"status": "canceled"},
            ),
        )

        response = await self.client.post(
            "/api/v1/webhooks/payments/yookassa",
            content=json.dumps({"event_id": "event-cancelled-orphan-1"}),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")

        stored_payment = await self._get_payment("yoopay-topup-orphan-1000")
        self.assertIsNotNone(stored_payment)
        assert stored_payment is not None
        self.assertEqual(stored_payment.status, PaymentStatus.CANCELLED)
        self.assertIsNotNone(stored_payment.finalized_at)

        async with self._session_factory() as session:
            result = await session.execute(select(Notification).order_by(Notification.id.asc()))
            self.assertEqual(list(result.scalars().all()), [])

    async def test_expire_stale_payments_marks_unpaid_stars_payment_as_expired(self) -> None:
        account = await self._create_account(
            balance=0,
            email="stars-stale@example.com",
            telegram_id=758107031,
        )
        self._current_account_id = account.id

        with patch(
            "app.services.payments.get_subscription_plan",
            return_value=SimpleNamespace(
                code="plan_1m",
                name="1 месяц",
                price_rub=299,
                price_stars=85,
                duration_days=30,
            ),
        ):
            create_response = await self.client.post(
                "/api/v1/payments/telegram-stars/plans/plan_1m",
                json={"idempotency_key": "stars-stale-1m"},
            )
        self.assertEqual(create_response.status_code, 200)
        provider_payment_id = create_response.json()["provider_payment_id"]

        async with self._session_factory() as session:
            result = await session.execute(
                select(Payment).where(Payment.provider_payment_id == provider_payment_id)
            )
            payment = result.scalar_one()
            payment.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            await session.commit()

        async with self._session_factory() as session:
            summary = await expire_stale_payments(session, limit=10)

        self.assertEqual(summary.expired, 1)

        stored_payment = await self._get_payment(provider_payment_id)
        self.assertIsNotNone(stored_payment)
        assert stored_payment is not None
        self.assertEqual(stored_payment.status, PaymentStatus.EXPIRED)
        self.assertIsNotNone(stored_payment.finalized_at)

        notifications = await self._get_notifications(account.id)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].type, NotificationType.PAYMENT_FAILED)
        self.assertEqual(notifications[0].payload["status"], "expired")

    async def test_reconcile_pending_yookassa_payment_applies_success_without_webhook(self) -> None:
        account = await self._create_account(balance=100, email="reconcile@example.com")
        self._current_account_id = account.id

        create_response = await self.client.post(
            "/api/v1/payments/yookassa/topup",
            json={
                "amount_rub": 500,
                "success_url": "https://app.example.com/payments/return",
                "idempotency_key": "topup-reconcile-500",
            },
        )
        self.assertEqual(create_response.status_code, 200)

        async with self._session_factory() as session:
            result = await session.execute(
                select(Payment).where(Payment.provider_payment_id == "yoopay-topup-reconcile-500")
            )
            payment = result.scalar_one()
            payment.created_at = datetime.now(UTC) - timedelta(minutes=10)
            await session.commit()

        self._fake_gateway.put_status_snapshot(
            PaymentIntentSnapshot(
                provider=PaymentProvider.YOOKASSA,
                flow_type=PaymentFlowType.WALLET_TOPUP,
                account_id=account.id,
                status=PaymentStatus.SUCCEEDED,
                amount=500,
                currency="RUB",
                provider_payment_id="yoopay-topup-reconcile-500",
                external_reference="topup-reconcile-500",
                confirmation_url="https://yookassa.test/confirm",
                expires_at=datetime.now(UTC) + timedelta(minutes=20),
                raw_payload={"status": "succeeded"},
            )
        )

        async with self._session_factory() as session:
            summary = await reconcile_pending_yookassa_payments(session, limit=10, min_age_seconds=0)

        self.assertEqual(summary.succeeded, 1)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 600)

        stored_payment = await self._get_payment("yoopay-topup-reconcile-500")
        self.assertIsNotNone(stored_payment)
        assert stored_payment is not None
        self.assertEqual(stored_payment.status, PaymentStatus.SUCCEEDED)
        self.assertIsNotNone(stored_payment.finalized_at)

        ledger_entries = await self._get_ledger_entries(account.id)
        self.assertEqual(len(ledger_entries), 1)
        self.assertEqual(ledger_entries[0].entry_type, LedgerEntryType.TOPUP_PAYMENT)

        notifications = await self._get_notifications(account.id)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].type, NotificationType.PAYMENT_SUCCEEDED)

    async def test_yookassa_webhook_root_alias_is_supported(self) -> None:
        account = await self._create_account(balance=100)
        self._current_account_id = account.id

        create_response = await self.client.post(
            "/api/v1/payments/yookassa/topup",
            json={
                "amount_rub": 500,
                "success_url": "https://app.example.com/payments/return",
                "idempotency_key": "topup-root-alias",
            },
        )
        self.assertEqual(create_response.status_code, 200)

        self._fake_gateway.put_event(
            "event-root-alias",
            PaymentWebhookEvent(
                provider=PaymentProvider.YOOKASSA,
                provider_event_id="payment.succeeded:yoopay-topup-root-alias",
                provider_payment_id="yoopay-topup-root-alias",
                status=PaymentStatus.SUCCEEDED,
                amount=500,
                currency="RUB",
                flow_type=PaymentFlowType.WALLET_TOPUP,
                account_id=account.id,
                external_reference="topup-root-alias",
                raw_payload={"status": "succeeded"},
            ),
        )

        response = await self.client.post(
            "/webhooks/payments/yookassa",
            content=json.dumps({"event_id": "event-root-alias"}),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["ledger_applied"], True)
        self.assertEqual(len(await self._get_ledger_entries(account.id)), 1)

    async def test_plan_purchase_webhook_applies_subscription_once(self) -> None:
        account = await self._create_account(balance=0, email="paid@example.com")
        self._current_account_id = account.id

        async def fake_apply_paid_purchase(
            account_obj: Account,
            *,
            source,
            target_expires_at: datetime,
        ):
            self.assertEqual(source.value, "direct_payment")
            account_obj.remnawave_user_uuid = account_obj.id
            account_obj.subscription_status = "ACTIVE"
            account_obj.subscription_expires_at = target_expires_at
            account_obj.subscription_url = f"https://panel.test/sub/{account_obj.id.hex[:8]}"
            account_obj.subscription_is_trial = False
            return SimpleNamespace(uuid=account_obj.id, expire_at=target_expires_at)

        with patch(
            "app.services.payments.apply_paid_purchase",
            side_effect=fake_apply_paid_purchase,
        ):
            await self._create_direct_plan_payment(account)

            self._fake_gateway.put_event(
                "plan-event-1",
                PaymentWebhookEvent(
                    provider=PaymentProvider.YOOKASSA,
                    provider_event_id="payment.succeeded:yoopay-plan-1m",
                    provider_payment_id="yoopay-plan-1m",
                    status=PaymentStatus.SUCCEEDED,
                    amount=299,
                    currency="RUB",
                    flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                    account_id=account.id,
                    external_reference="plan-1m",
                    raw_payload={"status": "succeeded"},
                ),
            )

            response = await self.client.post(
                "/api/v1/webhooks/payments/yookassa",
                content=json.dumps({"event_id": "plan-event-1"}),
                headers={"content-type": "application/json"},
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["duplicate"], False)
            self.assertEqual(body["ledger_applied"], False)
            self.assertEqual(body["subscription_applied"], True)
            self.assertEqual(body["status"], "succeeded")

            stored_account = await self._get_account(account.id)
            self.assertIsNotNone(stored_account)
            assert stored_account is not None
            self.assertEqual(stored_account.subscription_status, "ACTIVE")
            self.assertFalse(stored_account.subscription_is_trial)
            first_expires_at = stored_account.subscription_expires_at
            self.assertIsNotNone(first_expires_at)

            stored_payment = await self._get_payment("yoopay-plan-1m")
            self.assertIsNotNone(stored_payment)
            assert stored_payment is not None
            self.assertEqual(stored_payment.plan_code, "plan_1m")
            self.assertEqual(stored_payment.status, PaymentStatus.SUCCEEDED)
            self.assertIsNotNone(stored_payment.finalized_at)

            notifications = await self._get_notifications(account.id)
            self.assertEqual(len(notifications), 1)
            self.assertEqual(notifications[0].type, NotificationType.PAYMENT_SUCCEEDED)
            self.assertEqual(notifications[0].payload["plan_code"], "plan_1m")

            grants = await self._get_subscription_grants(account.id)
            self.assertEqual(len(grants), 1)
            self.assertEqual(grants[0].plan_code, "plan_1m")
            self.assertEqual(grants[0].duration_days, 30)
            self.assertIsNotNone(grants[0].applied_at)

            duplicate_response = await self.client.post(
                "/api/v1/webhooks/payments/yookassa",
                content=json.dumps({"event_id": "plan-event-1"}),
                headers={"content-type": "application/json"},
            )
            self.assertEqual(duplicate_response.status_code, 200)
            duplicate_body = duplicate_response.json()
            self.assertEqual(duplicate_body["duplicate"], True)
            self.assertEqual(duplicate_body["subscription_applied"], False)

            stored_account = await self._get_account(account.id)
            self.assertIsNotNone(stored_account)
            assert stored_account is not None
            self.assertEqual(stored_account.subscription_expires_at, first_expires_at)

    async def test_plan_purchase_webhook_applies_first_referral_reward(self) -> None:
        referrer = await self._create_account(
            balance=0,
            email="referrer@example.com",
            referral_code="ref-direct",
        )
        account = await self._create_account(
            balance=0,
            email="paid-ref@example.com",
            referral_code="ref-direct-user",
        )
        self._current_account_id = account.id

        claim_response = await self.client.post(
            "/api/v1/referrals/claim",
            json={"referral_code": "ref-direct"},
        )
        self.assertEqual(claim_response.status_code, 200)

        async def fake_apply_paid_purchase(
            account_obj: Account,
            *,
            source,
            target_expires_at: datetime,
        ):
            self.assertEqual(source.value, "direct_payment")
            account_obj.remnawave_user_uuid = account_obj.id
            account_obj.subscription_status = "ACTIVE"
            account_obj.subscription_expires_at = target_expires_at
            account_obj.subscription_url = f"https://panel.test/sub/{account_obj.id.hex[:8]}"
            account_obj.subscription_is_trial = False
            return SimpleNamespace(uuid=account_obj.id, expire_at=target_expires_at)

        with patch(
            "app.services.payments.apply_paid_purchase",
            side_effect=fake_apply_paid_purchase,
        ):
            await self._create_direct_plan_payment(account)

            self._fake_gateway.put_event(
                "plan-event-referral",
                PaymentWebhookEvent(
                    provider=PaymentProvider.YOOKASSA,
                    provider_event_id="payment.succeeded:yoopay-plan-1m",
                    provider_payment_id="yoopay-plan-1m",
                    status=PaymentStatus.SUCCEEDED,
                    amount=299,
                    currency="RUB",
                    flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                    account_id=account.id,
                    external_reference="plan-1m",
                    raw_payload={"status": "succeeded"},
                ),
            )

            response = await self.client.post(
                "/api/v1/webhooks/payments/yookassa",
                content=json.dumps({"event_id": "plan-event-referral"}),
                headers={"content-type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["subscription_applied"], True)

        stored_referrer = await self._get_account(referrer.id)
        self.assertIsNotNone(stored_referrer)
        assert stored_referrer is not None
        self.assertEqual(stored_referrer.referrals_count, 1)
        self.assertEqual(stored_referrer.referral_earnings, 59)

        ledger_entries = await self._get_ledger_entries(referrer.id)
        self.assertEqual(len(ledger_entries), 1)
        self.assertEqual(ledger_entries[0].entry_type, LedgerEntryType.REFERRAL_REWARD)
        self.assertEqual(ledger_entries[0].amount, 59)

        referrer_notifications = await self._get_notifications(referrer.id)
        self.assertEqual(len(referrer_notifications), 1)
        self.assertEqual(referrer_notifications[0].type, NotificationType.REFERRAL_REWARD_RECEIVED)

    async def test_duplicate_event_can_resume_pending_plan_finalization(self) -> None:
        account = await self._create_account(balance=0, email="resume@example.com")
        self._current_account_id = account.id

        async def fake_apply_paid_purchase(
            account_obj: Account,
            *,
            source,
            target_expires_at: datetime,
        ):
            self.assertEqual(source.value, "direct_payment")
            account_obj.remnawave_user_uuid = account_obj.id
            account_obj.subscription_status = "ACTIVE"
            account_obj.subscription_expires_at = target_expires_at
            account_obj.subscription_url = f"https://panel.test/sub/{account_obj.id.hex[:8]}"
            account_obj.subscription_is_trial = False
            return SimpleNamespace(uuid=account_obj.id, expire_at=target_expires_at)

        await self._create_direct_plan_payment(account)

        async with self._session_factory() as session:
            result = await session.execute(
                select(Payment).where(Payment.provider_payment_id == "yoopay-plan-1m")
            )
            payment = result.scalar_one()
            payment.status = PaymentStatus.SUCCEEDED
            payment.finalized_at = None
            session.add(
                PaymentEvent(
                    payment_id=payment.id,
                    account_id=payment.account_id,
                    provider=PaymentProvider.YOOKASSA,
                    flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                    status=PaymentStatus.SUCCEEDED,
                    provider_event_id="payment.succeeded:yoopay-plan-1m",
                    provider_payment_id=payment.provider_payment_id,
                    event_type="payment.succeeded",
                    amount=payment.amount,
                    currency=payment.currency,
                    raw_payload={"status": "succeeded"},
                    processed_at=datetime.now(UTC),
                )
            )
            session.add(
                SubscriptionGrant(
                    account_id=account.id,
                    payment_id=payment.id,
                    plan_code="plan_1m",
                    amount=payment.amount,
                    currency=payment.currency,
                    duration_days=30,
                    base_expires_at=datetime.now(UTC),
                    target_expires_at=datetime.now(UTC) + timedelta(days=30),
                )
            )
            await session.commit()

        self._fake_gateway.put_event(
            "plan-event-resume",
            PaymentWebhookEvent(
                provider=PaymentProvider.YOOKASSA,
                provider_event_id="payment.succeeded:yoopay-plan-1m",
                provider_payment_id="yoopay-plan-1m",
                status=PaymentStatus.SUCCEEDED,
                amount=299,
                currency="RUB",
                flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                account_id=account.id,
                external_reference="plan-1m",
                raw_payload={"status": "succeeded"},
            ),
        )

        with patch(
            "app.services.payments.apply_paid_purchase",
            side_effect=fake_apply_paid_purchase,
        ):
            response = await self.client.post(
                "/api/v1/webhooks/payments/yookassa",
                content=json.dumps({"event_id": "plan-event-resume"}),
                headers={"content-type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["duplicate"], True)
        self.assertEqual(body["subscription_applied"], True)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.subscription_status, "ACTIVE")

        grants = await self._get_subscription_grants(account.id)
        self.assertEqual(len(grants), 1)
        self.assertIsNotNone(grants[0].applied_at)

    async def test_create_telegram_stars_plan_purchase_persists_pending_payment(self) -> None:
        account = await self._create_account(
            balance=0,
            email="stars@example.com",
            telegram_id=758107031,
        )
        self._current_account_id = account.id

        with patch(
            "app.services.payments.get_subscription_plan",
            return_value=SimpleNamespace(
                code="plan_1m",
                name="1 месяц",
                price_rub=299,
                price_stars=85,
                duration_days=30,
            ),
        ):
            response = await self.client.post(
                "/api/v1/payments/telegram-stars/plans/plan_1m",
                json={"idempotency_key": "stars-plan-1m"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["provider"], "telegram_stars")
        self.assertEqual(body["amount"], 85)
        self.assertEqual(body["currency"], "XTR")
        self.assertTrue(body["provider_payment_id"].startswith("rmstars:dp:"))
        self.assertIn("https://t.me/invoice/", body["confirmation_url"])

        stored_payment = await self._get_payment(body["provider_payment_id"])
        self.assertIsNotNone(stored_payment)
        assert stored_payment is not None
        self.assertEqual(stored_payment.provider, PaymentProvider.TELEGRAM_STARS)
        self.assertEqual(stored_payment.amount, 85)
        self.assertEqual(stored_payment.plan_code, "plan_1m")
        self.assertIsNotNone(stored_payment.expires_at)

    async def test_telegram_stars_pre_checkout_rejects_fully_blocked_account(self) -> None:
        account = await self._create_account(
            balance=0,
            email="stars-blocked@example.com",
            telegram_id=758107031,
        )
        self._current_account_id = account.id

        with patch(
            "app.services.payments.get_subscription_plan",
            return_value=SimpleNamespace(
                code="plan_1m",
                name="1 месяц",
                price_rub=299,
                price_stars=85,
                duration_days=30,
            ),
        ):
            create_response = await self.client.post(
                "/api/v1/payments/telegram-stars/plans/plan_1m",
                json={"idempotency_key": "stars-plan-blocked"},
            )
        self.assertEqual(create_response.status_code, 200)
        provider_payment_id = create_response.json()["provider_payment_id"]

        async with self._session_factory() as session:
            stored_account = await session.get(Account, account.id)
            assert stored_account is not None
            stored_account.status = AccountStatus.BLOCKED
            await session.commit()

        pre_checkout_response = await self.client.post(
            "/api/v1/webhooks/payments/telegram-stars/pre-checkout",
            json={
                "telegram_id": 758107031,
                "invoice_payload": provider_payment_id,
                "total_amount": 85,
                "currency": "XTR",
                "pre_checkout_query_id": "pcq-blocked-1",
            },
            headers={"Authorization": "Bearer internal-token"},
        )
        self.assertEqual(pre_checkout_response.status_code, 200)
        self.assertEqual(
            pre_checkout_response.json(),
            {"ok": False, "error_message": "Аккаунт полностью заблокирован"},
        )

    async def test_telegram_stars_pre_checkout_and_successful_payment_finalize_once(self) -> None:
        account = await self._create_account(
            balance=0,
            email="stars-paid@example.com",
            telegram_id=758107031,
        )
        self._current_account_id = account.id

        async def fake_apply_paid_purchase(
            account_obj: Account,
            *,
            source,
            target_expires_at: datetime,
        ):
            self.assertEqual(source.value, "direct_payment")
            account_obj.remnawave_user_uuid = account_obj.id
            account_obj.subscription_status = "ACTIVE"
            account_obj.subscription_expires_at = target_expires_at
            account_obj.subscription_url = f"https://panel.test/sub/{account_obj.id.hex[:8]}"
            account_obj.subscription_is_trial = False
            return SimpleNamespace(uuid=account_obj.id, expire_at=target_expires_at)

        with patch(
            "app.services.payments.get_subscription_plan",
            return_value=SimpleNamespace(
                code="plan_1m",
                name="1 месяц",
                price_rub=299,
                price_stars=85,
                duration_days=30,
            ),
        ):
            create_response = await self.client.post(
                "/api/v1/payments/telegram-stars/plans/plan_1m",
                json={"idempotency_key": "stars-plan-1m"},
            )
        self.assertEqual(create_response.status_code, 200)
        payment_body = create_response.json()
        provider_payment_id = payment_body["provider_payment_id"]

        pre_checkout_response = await self.client.post(
            "/api/v1/webhooks/payments/telegram-stars/pre-checkout",
            json={
                "telegram_id": 758107031,
                "invoice_payload": provider_payment_id,
                "total_amount": 85,
                "currency": "XTR",
                "pre_checkout_query_id": "pcq-1",
            },
            headers={"Authorization": "Bearer internal-token"},
        )
        self.assertEqual(pre_checkout_response.status_code, 200)
        self.assertEqual(pre_checkout_response.json(), {"ok": True, "error_message": None})

        long_charge_id = "tg-charge-" + ("x" * 180)

        self._fake_stars_gateway.put_event(
            "stars-event-1",
            PaymentWebhookEvent(
                provider=PaymentProvider.TELEGRAM_STARS,
                provider_event_id=f"successful_payment:{long_charge_id}",
                provider_payment_id=provider_payment_id,
                status=PaymentStatus.SUCCEEDED,
                amount=85,
                currency="XTR",
                flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                account_id=account.id,
                external_reference="provider-charge-1",
                raw_payload={
                    "event_type": "successful_payment",
                    "telegram_id": 758107031,
                    "currency": "XTR",
                    "total_amount": 85,
                    "invoice_payload": provider_payment_id,
                    "telegram_payment_charge_id": long_charge_id,
                    "provider_payment_charge_id": "provider-charge-1",
                },
            ),
        )

        with patch(
            "app.services.payments.apply_paid_purchase",
            side_effect=fake_apply_paid_purchase,
        ):
            response = await self.client.post(
                "/api/v1/webhooks/payments/telegram-stars",
                content=json.dumps({"event_id": "stars-event-1"}),
                headers={
                    "Authorization": "Bearer internal-token",
                    "content-type": "application/json",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["duplicate"], False)
        self.assertEqual(body["subscription_applied"], True)
        self.assertEqual(body["status"], "succeeded")

        stored_payment = await self._get_payment(provider_payment_id)
        self.assertIsNotNone(stored_payment)
        assert stored_payment is not None
        self.assertEqual(stored_payment.status, PaymentStatus.SUCCEEDED)
        self.assertIsNotNone(stored_payment.finalized_at)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.subscription_status, "ACTIVE")

        duplicate_response = await self.client.post(
            "/api/v1/webhooks/payments/telegram-stars",
            content=json.dumps({"event_id": "stars-event-1"}),
            headers={
                "Authorization": "Bearer internal-token",
                "content-type": "application/json",
            },
        )
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertTrue(duplicate_response.json()["duplicate"])
