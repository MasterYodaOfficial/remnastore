from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_account
from app.core.config import settings
from app.db.base import Base
from app.db.models import Account
from app.db.session import get_session
from app.domain.payments import (
    PaymentGatewayConfigurationError,
    PaymentFlowType,
    PaymentIntentSnapshot,
    PaymentProvider,
    PaymentStatus,
)
from app.main import create_app
from app.services.ledger import InsufficientFundsError
from app.services.payments import (
    PaymentAccountBlockedError,
    PaymentConflictError,
    PaymentGatewayError,
    PaymentNotFoundError,
    PaymentWebhookProcessResult,
)
from app.services.plans import SubscriptionPlanError
from app.services.promos import (
    PromoBlockedError,
    PromoCodeNotFoundError,
    PromoConflictError,
    PromoValidationError,
)
from app.services.purchases import PurchaseConflictError, RemnawaveSyncError
from app.services.referrals import ReferralCodeNotFoundError
from app.services.remnawave_webhooks import (
    RemnawaveWebhookPayloadError,
    RemnawaveWebhookProcessResult,
)
from app.services.subscriptions import (
    SubscriptionPurchaseBlockedError,
    TrialEligibilityError,
)


class DummyCache:
    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def account_response_key(self, account_id: str) -> str:
        return f"account:{account_id}"

    async def delete(self, *keys: str) -> None:
        return None


class CriticalEndpointErrorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "critical-endpoints.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._current_account_id: uuid.UUID | None = None

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()

        self._original_api_token = settings.api_token
        self._original_remnawave_secret = settings.remnawave_webhook_secret
        settings.api_token = "internal-token"
        settings.remnawave_webhook_secret = "remnawave-secret"

        self.app = create_app()

        async def override_get_session():
            async with self._session_factory() as session:
                yield session

        async def override_get_current_account():
            if self._current_account_id is None:
                raise AssertionError("current account is not configured")
            async with self._session_factory() as session:
                account = await session.get(Account, self._current_account_id)
                if account is None:
                    raise AssertionError(
                        f"account not found: {self._current_account_id}"
                    )
                return account

        self.app.dependency_overrides[get_session] = override_get_session
        self.app.dependency_overrides[get_current_account] = (
            override_get_current_account
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://testserver",
        )
        account = await self._create_account(email="critical@example.com")
        self._current_account_id = account.id

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        settings.api_token = self._original_api_token
        settings.remnawave_webhook_secret = self._original_remnawave_secret
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

    def _payment_snapshot(self) -> PaymentIntentSnapshot:
        return PaymentIntentSnapshot(
            provider=PaymentProvider.YOOKASSA,
            flow_type=PaymentFlowType.WALLET_TOPUP,
            account_id=self._current_account_id or uuid.uuid4(),
            status=PaymentStatus.PENDING,
            amount=500,
            currency="RUB",
            provider_payment_id="pay-1",
            external_reference="idem-1",
            confirmation_url="https://pay.test/confirm",
            expires_at=datetime(2026, 5, 11, 12, 0, tzinfo=UTC),
            raw_payload={"ok": True},
        )

    async def test_payments_topup_and_status_endpoints_map_errors(self) -> None:
        with patch(
            "app.api.v1.endpoints.payments.get_subscription_plans",
            side_effect=SubscriptionPlanError("plans unavailable", code="config"),
        ):
            plans_response = await self.client.get("/api/v1/payments/plans")
        self.assertEqual(plans_response.status_code, 503)

        with patch(
            "app.api.v1.endpoints.payments.get_payment_for_account",
            new=AsyncMock(side_effect=PaymentNotFoundError("payment missing")),
        ):
            status_response = await self.client.get(
                "/api/v1/payments/status",
                params={
                    "provider": PaymentProvider.YOOKASSA.value,
                    "provider_payment_id": "missing",
                },
            )
        self.assertEqual(status_response.status_code, 404)

        error_cases = (
            (PaymentGatewayConfigurationError("gateway missing"), 503, None),
            (PaymentConflictError("payment conflict"), 409, None),
            (PaymentAccountBlockedError("account blocked"), 403, None),
            (PaymentGatewayError("provider down"), 502, "gateway_failed"),
        )
        for exc, expected_status, expected_error_code in error_cases:
            with self.subTest(error=type(exc).__name__):
                with patch(
                    "app.api.v1.endpoints.payments.create_yookassa_topup_payment",
                    new=AsyncMock(side_effect=exc),
                ):
                    response = await self.client.post(
                        "/api/v1/payments/yookassa/topup",
                        json={
                            "amount_rub": 500,
                            "success_url": "https://app.test/return",
                            "idempotency_key": "topup-1",
                        },
                    )
                self.assertEqual(response.status_code, expected_status)
                if expected_error_code is not None:
                    self.assertEqual(
                        response.json().get("error_code"), expected_error_code
                    )

    async def test_plan_payment_endpoints_map_critical_service_errors(self) -> None:
        paths = (
            (
                "/api/v1/payments/yookassa/plans/plan_1m",
                "app.api.v1.endpoints.payments.create_yookassa_plan_purchase_payment",
            ),
            (
                "/api/v1/payments/telegram-stars/plans/plan_1m",
                "app.api.v1.endpoints.payments.create_telegram_stars_plan_purchase_payment",
            ),
        )
        error_cases = (
            (SubscriptionPlanError("unknown plan", code="unknown_plan"), 404, None),
            (PromoCodeNotFoundError("promo missing", code="code_not_found"), 404, None),
            (PaymentGatewayConfigurationError("gateway missing"), 503, None),
            (PaymentConflictError("payment conflict"), 409, None),
            (PromoConflictError("promo conflict", code="promo_conflict"), 409, None),
            (PaymentAccountBlockedError("account blocked"), 403, None),
            (PromoBlockedError("promo blocked", code="account_blocked"), 403, None),
            (
                PromoValidationError(
                    "promo invalid", code="cannot_use_for_plan_purchase"
                ),
                422,
                "cannot_use_for_plan_purchase",
            ),
            (PaymentGatewayError("provider down"), 502, "gateway_failed"),
        )
        for path, patch_target in paths:
            for exc, expected_status, expected_error_code in error_cases:
                with self.subTest(path=path, error=type(exc).__name__):
                    with patch(
                        patch_target,
                        new=AsyncMock(side_effect=exc),
                    ):
                        response = await self.client.post(
                            path,
                            json={
                                "description": "Plan purchase",
                                "idempotency_key": "plan-1",
                                "promo_code": "PROMO",
                            },
                        )
                    self.assertEqual(response.status_code, expected_status)
                    if expected_error_code is not None:
                        self.assertEqual(
                            response.json().get("error_code"), expected_error_code
                        )

    async def test_promo_endpoints_map_errors(self) -> None:
        quote_cases = (
            (SubscriptionPlanError("unknown plan", code="unknown_plan"), 404),
            (PromoCodeNotFoundError("promo missing", code="code_not_found"), 404),
            (PromoBlockedError("promo blocked", code="account_blocked"), 403),
            (PromoConflictError("promo conflict", code="promo_conflict"), 409),
            (
                PromoValidationError("promo invalid", code="cannot_redeem_directly"),
                422,
            ),
        )
        for exc, expected_status in quote_cases:
            with self.subTest(quote_error=type(exc).__name__):
                with patch(
                    "app.api.v1.endpoints.promos.quote_plan_promo",
                    new=AsyncMock(side_effect=exc),
                ):
                    response = await self.client.post(
                        "/api/v1/promos/plans/plan_1m/quote",
                        json={"promo_code": "promo", "currency": "rub"},
                    )
                self.assertEqual(response.status_code, expected_status)

        redeem_cases = (
            (PromoCodeNotFoundError("promo missing", code="code_not_found"), 404),
            (PromoBlockedError("promo blocked", code="account_blocked"), 403),
            (PromoConflictError("promo conflict", code="promo_conflict"), 409),
            (PromoValidationError("promo invalid", code="idempotency_required"), 422),
            (RemnawaveSyncError("remnawave unavailable"), 502),
        )
        for exc, expected_status in redeem_cases:
            with self.subTest(redeem_error=type(exc).__name__):
                with patch(
                    "app.api.v1.endpoints.promos.redeem_promo_code",
                    new=AsyncMock(side_effect=exc),
                ):
                    response = await self.client.post(
                        "/api/v1/promos/redeem",
                        json={"code": "promo", "idempotency_key": "redeem-1"},
                    )
                self.assertEqual(response.status_code, expected_status)

    async def test_subscription_endpoints_map_errors(self) -> None:
        with patch(
            "app.api.v1.endpoints.subscriptions.sync_current_subscription",
            new=AsyncMock(side_effect=RemnawaveSyncError("gateway unavailable")),
        ):
            sync_response = await self.client.post("/api/v1/subscriptions/sync")
        self.assertEqual(sync_response.status_code, 502)

        with patch(
            "app.api.v1.endpoints.subscriptions.activate_trial",
            new=AsyncMock(
                side_effect=TrialEligibilityError("account_blocked", status_code=403)
            ),
        ):
            trial_response = await self.client.post("/api/v1/subscriptions/trial")
        self.assertEqual(trial_response.status_code, 403)
        self.assertEqual(trial_response.json()["error_code"], "account_blocked")

        error_cases = (
            (SubscriptionPlanError("unknown plan", code="unknown_plan"), 404),
            (PromoCodeNotFoundError("promo missing", code="code_not_found"), 404),
            (InsufficientFundsError("insufficient funds"), 409),
            (PurchaseConflictError("purchase conflict", code="purchase_conflict"), 409),
            (PromoConflictError("promo conflict", code="promo_conflict"), 409),
            (
                SubscriptionPurchaseBlockedError(
                    "account blocked", code="account_blocked_purchase"
                ),
                403,
            ),
            (PromoBlockedError("promo blocked", code="account_blocked"), 403),
            (
                PromoValidationError("promo invalid", code="zero_payment_use_direct"),
                422,
            ),
            (RemnawaveSyncError("gateway unavailable"), 502),
        )
        for exc, expected_status in error_cases:
            with self.subTest(error=type(exc).__name__):
                with patch(
                    "app.api.v1.endpoints.subscriptions.purchase_subscription_with_wallet",
                    new=AsyncMock(side_effect=exc),
                ):
                    response = await self.client.post(
                        "/api/v1/subscriptions/wallet/plans/plan_1m",
                        json={"idempotency_key": "wallet-1", "promo_code": "PROMO"},
                    )
                self.assertEqual(response.status_code, expected_status)

    async def test_webhook_endpoints_map_yookassa_and_telegram_errors(self) -> None:
        yookassa_cases = (
            (PaymentGatewayConfigurationError("gateway missing"), 503),
            (PaymentConflictError("payment conflict"), 409),
            (PaymentGatewayError("bad payload"), 400),
        )
        for exc, expected_status in yookassa_cases:
            with self.subTest(yookassa_error=type(exc).__name__):
                with patch(
                    "app.api.v1.endpoints.webhooks.process_yookassa_webhook",
                    new=AsyncMock(side_effect=exc),
                ):
                    response = await self.client.post(
                        "/api/v1/webhooks/payments/yookassa",
                        content=json.dumps({"event": "payment.succeeded"}),
                        headers={"content-type": "application/json"},
                    )
                self.assertEqual(response.status_code, expected_status)

        with patch(
            "app.api.v1.endpoints.webhooks.process_yookassa_webhook",
            new=AsyncMock(
                return_value=PaymentWebhookProcessResult(
                    payment_id=1,
                    provider_payment_id="yoopay-1",
                    status=PaymentStatus.SUCCEEDED,
                    duplicate=False,
                    ledger_applied=True,
                    subscription_applied=False,
                )
            ),
        ):
            success_response = await self.client.post(
                "/api/v1/webhooks/payments/yookassa",
                content=json.dumps({"event": "payment.succeeded"}),
                headers={"content-type": "application/json"},
            )
        self.assertEqual(success_response.status_code, 200)
        self.assertEqual(success_response.json()["provider_payment_id"], "yoopay-1")

        with patch(
            "app.api.v1.endpoints.webhooks.validate_telegram_stars_pre_checkout",
            new=AsyncMock(return_value=(False, "amount mismatch")),
        ):
            pre_checkout_response = await self.client.post(
                "/api/v1/webhooks/payments/telegram-stars/pre-checkout",
                json={
                    "telegram_id": 123,
                    "invoice_payload": "payload",
                    "total_amount": 100,
                    "currency": "XTR",
                    "pre_checkout_query_id": "query-1",
                },
                headers={"Authorization": "Bearer internal-token"},
            )
        self.assertEqual(pre_checkout_response.status_code, 200)
        self.assertFalse(pre_checkout_response.json()["ok"])

        telegram_cases = (
            (PaymentGatewayConfigurationError("gateway missing"), 503),
            (PaymentConflictError("payment conflict"), 409),
            (PaymentGatewayError("bad payload"), 400),
        )
        for exc, expected_status in telegram_cases:
            with self.subTest(telegram_error=type(exc).__name__):
                with patch(
                    "app.api.v1.endpoints.webhooks.process_telegram_stars_webhook",
                    new=AsyncMock(side_effect=exc),
                ):
                    response = await self.client.post(
                        "/api/v1/webhooks/payments/telegram-stars",
                        content=json.dumps({"event_type": "successful_payment"}),
                        headers={
                            "Authorization": "Bearer internal-token",
                            "content-type": "application/json",
                        },
                    )
                self.assertEqual(response.status_code, expected_status)

        with patch(
            "app.api.v1.endpoints.webhooks.process_telegram_stars_webhook",
            new=AsyncMock(
                return_value=PaymentWebhookProcessResult(
                    payment_id=2,
                    provider_payment_id="tgpay-1",
                    status=PaymentStatus.SUCCEEDED,
                    duplicate=False,
                    ledger_applied=False,
                    subscription_applied=True,
                )
            ),
        ):
            success_response = await self.client.post(
                "/api/v1/webhooks/payments/telegram-stars",
                content=json.dumps({"event_type": "successful_payment"}),
                headers={
                    "Authorization": "Bearer internal-token",
                    "content-type": "application/json",
                },
            )
        self.assertEqual(success_response.status_code, 200)
        self.assertTrue(success_response.json()["subscription_applied"])

    async def test_referral_and_remnawave_webhook_endpoints_map_errors(self) -> None:
        with patch(
            "app.api.v1.endpoints.webhooks.record_telegram_referral_intent",
            new=AsyncMock(
                side_effect=ReferralCodeNotFoundError(
                    "referral missing", code="referral_code_not_found"
                )
            ),
        ):
            referral_error = await self.client.post(
                "/api/v1/webhooks/referrals/telegram-start",
                json={"telegram_id": 42, "referral_code": "MISSING"},
                headers={"Authorization": "Bearer internal-token"},
            )
        self.assertEqual(referral_error.status_code, 400)

        with patch(
            "app.api.v1.endpoints.webhooks.record_telegram_referral_intent",
            new=AsyncMock(return_value=None),
        ):
            referral_success = await self.client.post(
                "/api/v1/webhooks/referrals/telegram-start",
                json={"telegram_id": 42, "referral_code": "OK"},
                headers={"Authorization": "Bearer internal-token"},
            )
        self.assertEqual(referral_success.status_code, 200)
        self.assertEqual(referral_success.json(), {"ok": True})

        original_secret = settings.remnawave_webhook_secret
        settings.remnawave_webhook_secret = ""
        no_secret_response = await self.client.post(
            "/api/v1/webhooks/remnawave",
            content=json.dumps({"event": "user.modified"}),
            headers={"content-type": "application/json"},
        )
        settings.remnawave_webhook_secret = original_secret
        self.assertEqual(no_secret_response.status_code, 503)

        missing_signature = await self.client.post(
            "/api/v1/webhooks/remnawave",
            content=json.dumps({"event": "user.modified"}),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(missing_signature.status_code, 401)

        invalid_signature = await self.client.post(
            "/api/v1/webhooks/remnawave",
            content=json.dumps({"event": "user.modified"}),
            headers={
                "content-type": "application/json",
                "x-remnawave-signature": "bad-signature",
            },
        )
        self.assertEqual(invalid_signature.status_code, 401)

        raw_body = json.dumps({"event": "user.modified"}).encode("utf-8")
        signature = hmac.new(
            settings.remnawave_webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        with patch(
            "app.api.v1.endpoints.webhooks.process_remnawave_webhook",
            new=AsyncMock(side_effect=RemnawaveWebhookPayloadError("invalid payload")),
        ):
            payload_error = await self.client.post(
                "/api/v1/webhooks/remnawave",
                content=raw_body,
                headers={
                    "content-type": "application/json",
                    "x-remnawave-signature": signature,
                },
            )
        self.assertEqual(payload_error.status_code, 400)

        with patch(
            "app.api.v1.endpoints.webhooks.process_remnawave_webhook",
            new=AsyncMock(
                return_value=RemnawaveWebhookProcessResult(
                    event="user.modified",
                    scope="user",
                    handled=True,
                    processed=True,
                    account_id=self._current_account_id,
                    notification_types=(),
                )
            ),
        ):
            success_response = await self.client.post(
                "/api/v1/webhooks/remnawave",
                content=raw_body,
                headers={
                    "content-type": "application/json",
                    "x-remnawave-signature": signature,
                },
            )
        self.assertEqual(success_response.status_code, 200)
        self.assertTrue(success_response.json()["ok"])
