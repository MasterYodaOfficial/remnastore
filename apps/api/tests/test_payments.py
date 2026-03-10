import json
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_account
from app.db.base import Base
from app.db.models import Account, LedgerEntry, LedgerEntryType, Payment
from app.db.session import get_session
from app.main import create_app
from app.services.payments import (
    CreatePaymentIntentCommand,
    PaymentFlowType,
    PaymentGatewayError,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookEvent,
    YooKassaGateway,
    get_yookassa_gateway,
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

    def json(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "amount": {
                "value": self.amount.value,
                "currency": self.amount.currency,
            },
        }


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
            amount_rub=499,
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
        self.assertEqual(snapshot.amount_rub, 499)
        self.assertEqual(snapshot.currency, "RUB")
        self.assertEqual(snapshot.provider_payment_id, "2d10f42f-000f-5000-9000-1a2b3c4d5e6f")
        self.assertEqual(snapshot.external_reference, "pay-123")
        self.assertEqual(snapshot.confirmation_url, "https://yookassa.test/confirm")

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
        self.assertEqual(event.amount_rub, 1000)
        self.assertEqual(event.currency, "RUB")
        self.assertEqual(event.flow_type, PaymentFlowType.DIRECT_PLAN_PURCHASE)
        self.assertEqual(event.account_id, account_id)
        self.assertEqual(event.external_reference, "purchase-1")

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

    async def create_payment_intent(self, command: CreatePaymentIntentCommand):
        return SimpleNamespace(
            provider=PaymentProvider.YOOKASSA,
            flow_type=command.flow_type,
            account_id=command.account_id,
            status=PaymentStatus.PENDING,
            amount_rub=command.amount_rub,
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


class PaymentFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "payments.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._current_account_id: uuid.UUID | None = None
        self._fake_gateway = FakeYooKassaGateway()

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module
        import app.services.payments as payments_service

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()

        self._payments_service = payments_service
        self._original_gateway_factory = payments_service.get_yookassa_gateway
        payments_service.get_yookassa_gateway = lambda: self._fake_gateway

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
        self.assertEqual(body["amount_rub"], 500)
        self.assertEqual(body["provider_payment_id"], "yoopay-topup-500")
        self.assertEqual(body["external_reference"], "topup-500")

        stored_payment = await self._get_payment("yoopay-topup-500")
        self.assertIsNotNone(stored_payment)
        assert stored_payment is not None
        self.assertEqual(stored_payment.account_id, account.id)
        self.assertEqual(stored_payment.status, PaymentStatus.PENDING)
        self.assertEqual(stored_payment.amount, 500)

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
                amount_rub=500,
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
        self.assertEqual(len(await self._get_ledger_entries(account.id)), 1)
