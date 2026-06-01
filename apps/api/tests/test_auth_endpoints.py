from datetime import UTC, datetime
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app.api.errors import ApiError
from app.api.v1.endpoints import auth as auth_endpoints
from app.core.config import settings
from app.db.models import Account, AccountStatus, LoginSource
from app.schemas.auth import TelegramAuthRequest
from app.services.accounts import AccountBlockedError


def _make_account(**overrides) -> Account:
    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "telegram_id": 700001,
        "email": None,
        "display_name": "Tester",
        "username": "tester",
        "first_name": "Test",
        "last_name": "User",
        "is_premium": False,
        "locale": "ru",
        "status": AccountStatus.ACTIVE,
        "subscription_is_trial": False,
        "balance": 0,
        "referral_earnings": 0,
        "referrals_count": 0,
        "referral_reward_rate": 0,
        "last_login_source": LoginSource.TELEGRAM_WEBAPP,
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


class AuthEndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._original_jwt_secret = settings.jwt_secret
        self._original_jwt_ttl = settings.jwt_access_token_expires_seconds
        self._original_bot_token = settings.telegram_bot_token
        self._original_tg_ttl = settings.telegram_init_data_ttl_seconds
        settings.jwt_secret = "jwt-secret"
        settings.jwt_access_token_expires_seconds = 600
        settings.telegram_bot_token = "bot-secret"
        settings.telegram_init_data_ttl_seconds = 60

    def tearDown(self) -> None:
        settings.jwt_secret = self._original_jwt_secret
        settings.jwt_access_token_expires_seconds = self._original_jwt_ttl
        settings.telegram_bot_token = self._original_bot_token
        settings.telegram_init_data_ttl_seconds = self._original_tg_ttl

    def test_build_browser_auth_response_embeds_access_token_and_account(self) -> None:
        account = _make_account()

        response = auth_endpoints._build_browser_auth_response(
            account,
            avatar_url="https://example.test/avatar.png",
        )

        self.assertEqual(response.token_type, "bearer")
        self.assertEqual(response.account.id, account.id)
        self.assertEqual(response.avatar_url, "https://example.test/avatar.png")
        self.assertTrue(response.access_token)

    async def test_auth_telegram_webapp_propagates_invalid_init_data(self) -> None:
        request = _make_request("/api/v1/auth/telegram/webapp")
        payload = TelegramAuthRequest(init_data="bad")

        with (
            patch(
                "app.api.v1.endpoints.auth.verify_telegram_init_data",
                side_effect=HTTPException(status_code=401, detail="bad signature"),
            ),
            patch("app.api.v1.endpoints.auth.log_audit_event") as log_mock,
            self.assertRaises(HTTPException) as captured,
        ):
            await auth_endpoints.auth_telegram_webapp(
                payload,
                request,
                session=SimpleNamespace(),
            )

        self.assertEqual(captured.exception.status_code, 401)
        log_mock.assert_called_once()

    async def test_auth_telegram_webapp_rejects_missing_user(self) -> None:
        request = _make_request("/api/v1/auth/telegram/webapp")
        payload = TelegramAuthRequest(init_data="good")

        with (
            patch(
                "app.api.v1.endpoints.auth.verify_telegram_init_data",
                return_value={"auth_date": "1"},
            ),
            patch("app.api.v1.endpoints.auth.log_audit_event") as log_mock,
            self.assertRaises(ApiError) as captured,
        ):
            await auth_endpoints.auth_telegram_webapp(
                payload,
                request,
                session=SimpleNamespace(),
            )

        self.assertEqual(captured.exception.status_code, 400)
        self.assertEqual(captured.exception.error_code, "init_data_missing_user")
        log_mock.assert_called_once()

    async def test_auth_telegram_webapp_maps_blocked_account(self) -> None:
        request = _make_request("/api/v1/auth/telegram/webapp")
        payload = TelegramAuthRequest(init_data="good")

        with (
            patch(
                "app.api.v1.endpoints.auth.verify_telegram_init_data",
                return_value={"user": {"id": 700001}},
            ),
            patch(
                "app.api.v1.endpoints.auth.upsert_telegram_account",
                new=AsyncMock(side_effect=AccountBlockedError("blocked")),
            ),
            patch("app.api.v1.endpoints.auth.log_audit_event") as log_mock,
            self.assertRaises(ApiError) as captured,
        ):
            await auth_endpoints.auth_telegram_webapp(
                payload,
                request,
                session=SimpleNamespace(),
            )

        self.assertEqual(captured.exception.status_code, 403)
        self.assertEqual(captured.exception.error_code, "account_blocked")
        self.assertGreaterEqual(log_mock.call_count, 1)

    async def test_auth_telegram_webapp_marks_missing_referral_code(self) -> None:
        request = _make_request("/api/v1/auth/telegram/webapp")
        payload = TelegramAuthRequest(init_data="good")
        account = _make_account()
        session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

        with (
            patch(
                "app.api.v1.endpoints.auth.verify_telegram_init_data",
                return_value={
                    "user": {"id": 700001, "username": "tester"},
                    "start_param": "ref_missing",
                },
            ),
            patch(
                "app.api.v1.endpoints.auth.upsert_telegram_account",
                new=AsyncMock(return_value=account),
            ),
            patch(
                "app.api.v1.endpoints.auth.record_telegram_referral_intent",
                new=AsyncMock(
                    side_effect=auth_endpoints.ReferralCodeNotFoundError("missing")
                ),
            ),
            patch(
                "app.api.v1.endpoints.auth.apply_telegram_referral_intent",
                new=AsyncMock(return_value=None),
            ) as apply_mock,
            patch(
                "app.api.v1.endpoints.auth.append_account_event", new=AsyncMock()
            ) as event_mock,
        ):
            response = await auth_endpoints.auth_telegram_webapp(
                payload,
                request,
                session=session,
            )

        self.assertEqual(response.referral_result.reason, "referral_code_not_found")
        self.assertFalse(response.referral_result.applied)
        apply_mock.assert_not_awaited()
        event_mock.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(account)

    async def test_auth_telegram_webapp_returns_successful_auth_response(self) -> None:
        request = _make_request("/api/v1/auth/telegram/webapp")
        payload = TelegramAuthRequest(init_data="good")
        account = _make_account()
        session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
        applied_referral = SimpleNamespace(applied=True, created=True, reason=None)

        with (
            patch(
                "app.api.v1.endpoints.auth.verify_telegram_init_data",
                return_value={
                    "user": {
                        "id": 700001,
                        "username": "tester",
                        "first_name": "Test",
                        "last_name": "User",
                        "is_premium": True,
                        "language_code": "ru",
                    }
                },
            ),
            patch(
                "app.api.v1.endpoints.auth.upsert_telegram_account",
                new=AsyncMock(return_value=account),
            ) as upsert_mock,
            patch(
                "app.api.v1.endpoints.auth.apply_telegram_referral_intent",
                new=AsyncMock(return_value=applied_referral),
            ),
            patch(
                "app.api.v1.endpoints.auth.append_account_event", new=AsyncMock()
            ) as event_mock,
            patch("app.api.v1.endpoints.auth.log_audit_event") as log_mock,
        ):
            response = await auth_endpoints.auth_telegram_webapp(
                payload,
                request,
                session=session,
            )

        self.assertEqual(response.account.id, account.id)
        self.assertEqual(response.referral_result.applied, True)
        self.assertTrue(response.access_token)
        upsert_mock.assert_awaited_once()
        event_mock.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(account)
        log_mock.assert_called()
