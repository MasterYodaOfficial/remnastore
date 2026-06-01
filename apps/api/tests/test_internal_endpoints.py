from datetime import UTC, datetime
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1.endpoints import internal as internal_endpoints
from app.core.config import settings
from app.db.models import Account, AccountStatus
from app.domain.payments import PaymentProvider
from app.schemas.bot import (
    BotDashboardResponse,
    BotPlanActionRequest,
    BotPlanPaymentResponse,
)
from app.services.bot_menu import BotMenuAccountNotFoundError, BotMenuServiceError
from app.services.i18n import translate
from app.services.payments import (
    PaymentAccountBlockedError,
    PaymentConflictError,
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
)
from app.services.subscriptions import TrialEligibilityError
from app.services.plans import SubscriptionPlanError


def _make_account(**overrides) -> Account:
    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "telegram_id": 700001,
        "display_name": "Tester",
        "username": "tester",
        "first_name": "Test",
        "last_name": "User",
        "status": AccountStatus.ACTIVE,
        "subscription_is_trial": False,
        "balance": 0,
        "referral_earnings": 0,
        "referrals_count": 0,
        "referral_reward_rate": 0,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return Account(**values)


def _make_request(path: str) -> Request:
    scope = {
        "type": "http",
        "scheme": "http",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def _make_payment_response() -> BotPlanPaymentResponse:
    return BotPlanPaymentResponse(
        provider=PaymentProvider.YOOKASSA,
        plan_code="plan_1m",
        provider_payment_id="payment-1",
        confirmation_url="https://pay.test/confirm",
        amount=1000,
        currency="RUB",
        created_at=datetime.now(UTC),
    )


class InternalEndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._original_admin_ids = settings.bot_admin_ids
        settings.bot_admin_ids = "777000"

    def tearDown(self) -> None:
        settings.bot_admin_ids = self._original_admin_ids

    def test_verify_bot_admin_telegram_id_rejects_non_admin(self) -> None:
        with self.assertRaises(HTTPException) as captured:
            internal_endpoints._verify_bot_admin_telegram_id(123456)

        self.assertEqual(captured.exception.status_code, 403)

    async def test_read_telegram_account_access_returns_missing_account(self) -> None:
        with (
            patch("app.api.v1.endpoints.internal.verify_internal_api_token"),
            patch(
                "app.api.v1.endpoints.internal.get_account_by_telegram_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            response = await internal_endpoints.read_telegram_account_access(
                700001,
                session=SimpleNamespace(),
                authorization="Bearer token",
            )

        self.assertEqual(response.telegram_id, 700001)
        self.assertFalse(response.exists)

    async def test_read_telegram_account_access_marks_blocking_flags(self) -> None:
        account = _make_account(
            status=AccountStatus.BLOCKED,
            telegram_bot_blocked_at=datetime.now(UTC),
        )

        with (
            patch("app.api.v1.endpoints.internal.verify_internal_api_token"),
            patch(
                "app.api.v1.endpoints.internal.get_account_by_telegram_id",
                new=AsyncMock(return_value=account),
            ),
        ):
            response = await internal_endpoints.read_telegram_account_access(
                700001,
                session=SimpleNamespace(),
                authorization="Bearer token",
            )

        self.assertTrue(response.exists)
        self.assertTrue(response.fully_blocked)
        self.assertTrue(response.telegram_bot_blocked)

    async def test_mark_telegram_account_as_reachable_handles_missing_account(
        self,
    ) -> None:
        request = _make_request("/internal/telegram-accounts/700001/reachable")
        session = SimpleNamespace(commit=AsyncMock())

        with (
            patch("app.api.v1.endpoints.internal.verify_internal_api_token"),
            patch(
                "app.api.v1.endpoints.internal.mark_telegram_account_reachable",
                new=AsyncMock(return_value=None),
            ),
            patch("app.api.v1.endpoints.internal.log_audit_event") as log_mock,
        ):
            response = await internal_endpoints.mark_telegram_account_as_reachable(
                700001,
                request,
                session=session,
                authorization="Bearer token",
            )

        self.assertFalse(response.exists)
        session.commit.assert_awaited_once()
        self.assertEqual(log_mock.call_count, 1)
        self.assertEqual(
            log_mock.call_args.args[0], "internal.telegram_account.reachable"
        )
        self.assertEqual(log_mock.call_args.kwargs["outcome"], "success")
        self.assertFalse(log_mock.call_args.kwargs["exists"])
        self.assertEqual(log_mock.call_args.kwargs["reason"], "account_not_found")

    async def test_mark_telegram_account_as_reachable_returns_updated_account(
        self,
    ) -> None:
        request = _make_request("/internal/telegram-accounts/700001/reachable")
        session = SimpleNamespace(commit=AsyncMock())
        account = _make_account()

        with (
            patch("app.api.v1.endpoints.internal.verify_internal_api_token"),
            patch(
                "app.api.v1.endpoints.internal.mark_telegram_account_reachable",
                new=AsyncMock(return_value=account),
            ),
        ):
            response = await internal_endpoints.mark_telegram_account_as_reachable(
                700001,
                request,
                session=session,
                authorization="Bearer token",
            )

        self.assertTrue(response.exists)
        self.assertEqual(response.status, AccountStatus.ACTIVE)
        session.commit.assert_awaited_once()

    async def test_mark_telegram_account_as_blocked_handles_missing_account(
        self,
    ) -> None:
        request = _make_request("/internal/telegram-accounts/700001/blocked")
        session = SimpleNamespace(commit=AsyncMock())

        with (
            patch("app.api.v1.endpoints.internal.verify_internal_api_token"),
            patch(
                "app.api.v1.endpoints.internal.mark_telegram_account_blocked",
                new=AsyncMock(return_value=None),
            ),
            patch("app.api.v1.endpoints.internal.log_audit_event") as log_mock,
        ):
            response = await internal_endpoints.mark_telegram_account_as_blocked(
                700001,
                request,
                session=session,
                authorization="Bearer token",
            )

        self.assertFalse(response.exists)
        session.commit.assert_awaited_once()
        self.assertEqual(log_mock.call_count, 1)
        self.assertEqual(
            log_mock.call_args.args[0], "internal.telegram_account.blocked"
        )
        self.assertEqual(log_mock.call_args.kwargs["outcome"], "success")
        self.assertFalse(log_mock.call_args.kwargs["exists"])
        self.assertEqual(log_mock.call_args.kwargs["reason"], "account_not_found")

    async def test_mark_telegram_account_as_blocked_returns_updated_account(
        self,
    ) -> None:
        request = _make_request("/internal/telegram-accounts/700001/blocked")
        session = SimpleNamespace(commit=AsyncMock())
        account = _make_account(telegram_bot_blocked_at=datetime.now(UTC))

        with (
            patch("app.api.v1.endpoints.internal.verify_internal_api_token"),
            patch(
                "app.api.v1.endpoints.internal.mark_telegram_account_blocked",
                new=AsyncMock(return_value=account),
            ),
        ):
            response = await internal_endpoints.mark_telegram_account_as_blocked(
                700001,
                request,
                session=session,
                authorization="Bearer token",
            )

        self.assertTrue(response.exists)
        self.assertTrue(response.telegram_bot_blocked)
        session.commit.assert_awaited_once()

    async def test_read_bot_plans_maps_subscription_plan_errors(self) -> None:
        with (
            patch("app.api.v1.endpoints.internal.verify_internal_api_token"),
            patch(
                "app.api.v1.endpoints.internal.get_bot_plans",
                side_effect=SubscriptionPlanError("missing plan", code="missing"),
            ),
            self.assertRaises(HTTPException) as captured,
        ):
            await internal_endpoints.read_bot_plans(authorization="Bearer token")

        self.assertEqual(captured.exception.status_code, 503)

    async def test_create_bot_trial_subscription_maps_known_errors(self) -> None:
        request = _make_request("/internal/bot/subscriptions/trial/700001")
        session = SimpleNamespace()

        cases = [
            (
                BotMenuAccountNotFoundError("missing"),
                404,
                "missing",
            ),
            (
                TrialEligibilityError("account_blocked", status_code=403),
                403,
                "account_blocked",
            ),
            (
                internal_endpoints.RemnawaveSyncError("gateway failed"),
                502,
                "gateway failed",
            ),
        ]

        for exc, expected_status, expected_detail in cases:
            with self.subTest(exc=type(exc).__name__):
                with (
                    patch("app.api.v1.endpoints.internal.verify_internal_api_token"),
                    patch(
                        "app.api.v1.endpoints.internal.activate_trial_for_telegram_account",
                        new=AsyncMock(side_effect=exc),
                    ),
                    patch("app.api.v1.endpoints.internal.log_audit_event"),
                    self.assertRaises(HTTPException) as captured,
                ):
                    await internal_endpoints.create_bot_trial_subscription(
                        700001,
                        request,
                        session=session,
                        authorization="Bearer token",
                    )
                self.assertEqual(captured.exception.status_code, expected_status)
                self.assertEqual(captured.exception.detail, expected_detail)

    async def test_create_bot_trial_subscription_returns_dashboard(self) -> None:
        request = _make_request("/internal/bot/subscriptions/trial/700001")
        session = SimpleNamespace()
        dashboard = BotDashboardResponse(telegram_id=700001, exists=True)

        with (
            patch("app.api.v1.endpoints.internal.verify_internal_api_token"),
            patch(
                "app.api.v1.endpoints.internal.activate_trial_for_telegram_account",
                new=AsyncMock(return_value=None),
            ) as activate_mock,
            patch(
                "app.api.v1.endpoints.internal.get_bot_dashboard",
                new=AsyncMock(return_value=dashboard),
            ) as dashboard_mock,
        ):
            response = await internal_endpoints.create_bot_trial_subscription(
                700001,
                request,
                session=session,
                authorization="Bearer token",
            )

        self.assertEqual(response.telegram_id, 700001)
        activate_mock.assert_awaited_once()
        dashboard_mock.assert_awaited_once_with(session, telegram_id=700001)

    async def test_create_bot_telegram_stars_plan_payment_maps_errors(self) -> None:
        request = _make_request("/internal/bot/payments/telegram-stars/plans/plan_1m")
        payload = BotPlanActionRequest(telegram_id=700001, idempotency_key="idem-1")
        session = SimpleNamespace()
        cases = [
            (BotMenuAccountNotFoundError("missing"), 404, "missing"),
            (
                SubscriptionPlanError("unknown plan", code="unknown"),
                404,
                "unknown plan",
            ),
            (PaymentGatewayConfigurationError("misconfigured"), 503, "misconfigured"),
            (PaymentConflictError("conflict"), 409, "conflict"),
            (PaymentAccountBlockedError("blocked"), 403, "blocked"),
            (
                PaymentGatewayError("gateway"),
                502,
                translate("api.payments.errors.gateway_failed"),
            ),
            (
                BotMenuServiceError("gateway"),
                502,
                translate("api.payments.errors.gateway_failed"),
            ),
        ]

        for exc, expected_status, expected_detail in cases:
            with self.subTest(exc=type(exc).__name__):
                with (
                    patch("app.api.v1.endpoints.internal.verify_internal_api_token"),
                    patch(
                        "app.api.v1.endpoints.internal.create_telegram_stars_plan_payment_for_telegram_account",
                        new=AsyncMock(side_effect=exc),
                    ),
                    patch("app.api.v1.endpoints.internal.log_audit_event"),
                    self.assertRaises(HTTPException) as captured,
                ):
                    await internal_endpoints.create_bot_telegram_stars_plan_payment(
                        "plan_1m",
                        payload,
                        request,
                        session=session,
                        authorization="Bearer token",
                    )
                self.assertEqual(captured.exception.status_code, expected_status)
                self.assertEqual(captured.exception.detail, expected_detail)

    async def test_create_bot_telegram_stars_plan_payment_returns_snapshot(
        self,
    ) -> None:
        request = _make_request("/internal/bot/payments/telegram-stars/plans/plan_1m")
        payload = BotPlanActionRequest(telegram_id=700001, idempotency_key="idem-1")
        session = SimpleNamespace()
        response_model = _make_payment_response()
        response_model.provider = PaymentProvider.TELEGRAM_STARS
        response_model.currency = "XTR"

        with (
            patch("app.api.v1.endpoints.internal.verify_internal_api_token"),
            patch(
                "app.api.v1.endpoints.internal.create_telegram_stars_plan_payment_for_telegram_account",
                new=AsyncMock(return_value=response_model),
            ),
        ):
            response = await internal_endpoints.create_bot_telegram_stars_plan_payment(
                "plan_1m",
                payload,
                request,
                session=session,
                authorization="Bearer token",
            )

        self.assertEqual(response.provider, PaymentProvider.TELEGRAM_STARS)
        self.assertEqual(response.provider_payment_id, "payment-1")

    async def test_create_bot_yookassa_plan_payment_maps_errors(self) -> None:
        request = _make_request("/internal/bot/payments/yookassa/plans/plan_1m")
        payload = BotPlanActionRequest(telegram_id=700001, idempotency_key="idem-1")
        session = SimpleNamespace()
        cases = [
            (BotMenuAccountNotFoundError("missing"), 404),
            (SubscriptionPlanError("unknown plan", code="unknown"), 404),
            (PaymentGatewayConfigurationError("misconfigured"), 503),
            (PaymentConflictError("conflict"), 409),
            (PaymentAccountBlockedError("blocked"), 403),
            (PaymentGatewayError("gateway"), 502),
            (BotMenuServiceError("gateway"), 502),
        ]

        for exc, expected_status in cases:
            with self.subTest(exc=type(exc).__name__):
                with (
                    patch("app.api.v1.endpoints.internal.verify_internal_api_token"),
                    patch(
                        "app.api.v1.endpoints.internal.create_yookassa_plan_payment_for_telegram_account",
                        new=AsyncMock(side_effect=exc),
                    ),
                    patch("app.api.v1.endpoints.internal.log_audit_event"),
                    self.assertRaises(HTTPException) as captured,
                ):
                    await internal_endpoints.create_bot_yookassa_plan_payment(
                        "plan_1m",
                        payload,
                        request,
                        session=session,
                        authorization="Bearer token",
                    )
                self.assertEqual(captured.exception.status_code, expected_status)

    async def test_create_bot_yookassa_plan_payment_returns_snapshot(self) -> None:
        request = _make_request("/internal/bot/payments/yookassa/plans/plan_1m")
        payload = BotPlanActionRequest(telegram_id=700001, idempotency_key="idem-1")
        session = SimpleNamespace()
        response_model = _make_payment_response()

        with (
            patch("app.api.v1.endpoints.internal.verify_internal_api_token"),
            patch(
                "app.api.v1.endpoints.internal.create_yookassa_plan_payment_for_telegram_account",
                new=AsyncMock(return_value=response_model),
            ),
        ):
            response = await internal_endpoints.create_bot_yookassa_plan_payment(
                "plan_1m",
                payload,
                request,
                session=session,
                authorization="Bearer token",
            )

        self.assertEqual(response.provider, PaymentProvider.YOOKASSA)
        self.assertEqual(response.confirmation_url, "https://pay.test/confirm")
