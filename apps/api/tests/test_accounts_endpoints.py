from datetime import UTC, datetime
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.api.errors import ApiError
from app.api.v1.endpoints import accounts as account_endpoints
from app.core.config import settings
from app.db.models import Account, AccountStatus, LinkType, LoginSource
from app.services.account_linking import (
    AccountMergeConflictError,
    LinkTokenAlreadyConsumedError,
    LinkTokenExpiredError,
    LinkTokenNotFoundError,
    LinkTokenTypeMismatchError,
)


class _DummyCache:
    def __init__(self) -> None:
        self.json_value = None
        self.deleted_keys: list[str] = []
        self.saved_json: list[tuple[str, dict[str, object], int]] = []
        self.saved_tokens: list[tuple[str, str, int]] = []

    def account_response_key(self, account_id: str) -> str:
        return f"account:{account_id}"

    def auth_token_account_key(self, token: str) -> str:
        return f"auth:{token}"

    async def get_json(self, key: str):
        del key
        return self.json_value

    async def set_json(
        self, key: str, value: dict[str, object], ttl_seconds: int
    ) -> None:
        self.saved_json.append((key, value, ttl_seconds))

    async def delete(self, *keys: str) -> None:
        self.deleted_keys.extend(keys)

    async def set_str(self, key: str, value: str, ttl_seconds: int) -> None:
        self.saved_tokens.append((key, value, ttl_seconds))


def _make_account(**overrides) -> Account:
    now = datetime.now(UTC)
    base_values = {
        "id": uuid.uuid4(),
        "telegram_id": 700001,
        "email": "user@example.com",
        "display_name": "User",
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
    base_values.update(overrides)
    return Account(**base_values)


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


class AccountsEndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._original_webapp_url = settings.webapp_url
        self._original_bot_username = settings.telegram_bot_username
        self._original_auth_ttl = settings.auth_token_cache_ttl_seconds
        settings.webapp_url = "https://webapp.test"
        settings.telegram_bot_username = "test_bot"
        settings.auth_token_cache_ttl_seconds = 321

    def tearDown(self) -> None:
        settings.webapp_url = self._original_webapp_url
        settings.telegram_bot_username = self._original_bot_username
        settings.auth_token_cache_ttl_seconds = self._original_auth_ttl

    def test_link_token_http_error_maps_expected_error_codes(self) -> None:
        cases = [
            (LinkTokenNotFoundError(), 404, "token_not_found"),
            (LinkTokenExpiredError(), 400, "token_expired"),
            (LinkTokenAlreadyConsumedError(), 400, "token_already_used"),
            (LinkTokenTypeMismatchError(), 400, "token_type_invalid"),
        ]

        for exc, status_code, error_code in cases:
            with self.subTest(error_code=error_code):
                error = account_endpoints._link_token_http_error(exc)
                self.assertEqual(error.status_code, status_code)
                self.assertEqual(error.error_code, error_code)

    def test_link_token_http_error_falls_back_to_exception_message(self) -> None:
        error = account_endpoints._link_token_http_error(ValueError("bad token"))

        self.assertEqual(error.status_code, 400)
        self.assertEqual(error.detail, "bad token")

    async def test_upsert_account_from_telegram_rejects_other_account(self) -> None:
        payload = account_endpoints.TelegramUpsertRequest(telegram_id=700002)
        current_account = _make_account(telegram_id=700001)

        with self.assertRaises(ApiError) as captured:
            await account_endpoints.upsert_account_from_telegram(
                payload,
                session=object(),
                current_account=current_account,
            )

        self.assertEqual(captured.exception.status_code, 403)
        self.assertEqual(captured.exception.error_code, "cannot_modify_another_account")

    async def test_upsert_account_from_telegram_delegates_to_service(self) -> None:
        payload = account_endpoints.TelegramUpsertRequest(
            telegram_id=700001,
            username="updated",
            first_name="Test",
            last_name="User",
            is_premium=True,
            locale="ru",
            email="updated@example.com",
            display_name="Updated User",
            last_login_source=LoginSource.TELEGRAM_WEBAPP,
        )
        current_account = _make_account(telegram_id=700001)
        updated_account = _make_account(
            id=current_account.id,
            telegram_id=700001,
            username="updated",
            email="updated@example.com",
            display_name="Updated User",
            is_premium=True,
        )

        with patch(
            "app.api.v1.endpoints.accounts.upsert_telegram_account",
            new=AsyncMock(return_value=updated_account),
        ) as upsert_mock:
            result = await account_endpoints.upsert_account_from_telegram(
                payload,
                session=object(),
                current_account=current_account,
            )

        self.assertIs(result, updated_account)
        upsert_mock.assert_awaited_once()

    async def test_get_account_me_uses_valid_cached_response(self) -> None:
        account = _make_account()
        cache = _DummyCache()
        cache.json_value = {
            "id": str(account.id),
            "telegram_id": account.telegram_id,
            "email": account.email,
            "display_name": account.display_name,
            "username": account.username,
            "first_name": account.first_name,
            "last_name": account.last_name,
            "is_premium": account.is_premium,
            "locale": account.locale,
            "status": account.status.value,
            "subscription_is_trial": account.subscription_is_trial,
            "has_used_trial": False,
            "balance": account.balance,
            "referral_earnings": account.referral_earnings,
            "referrals_count": account.referrals_count,
            "referral_reward_rate": account.referral_reward_rate,
            "created_at": account.created_at.isoformat(),
            "updated_at": account.updated_at.isoformat(),
        }

        with patch("app.api.v1.endpoints.accounts.get_cache", return_value=cache):
            result = await account_endpoints.get_account_me(current_account=account)

        self.assertEqual(result.id, account.id)
        self.assertEqual(cache.saved_json, [])

    async def test_get_account_me_rebuilds_invalid_cached_response(self) -> None:
        account = _make_account()
        cache = _DummyCache()
        cache.json_value = {"id": "broken"}

        with patch("app.api.v1.endpoints.accounts.get_cache", return_value=cache):
            result = await account_endpoints.get_account_me(current_account=account)

        self.assertEqual(result.id, account.id)
        self.assertEqual(cache.deleted_keys, [f"account:{account.id}"])
        self.assertEqual(len(cache.saved_json), 1)

    async def test_generate_telegram_link_rejects_already_linked_account(self) -> None:
        request = _make_request("/api/v1/accounts/link-telegram")
        current_account = _make_account(telegram_id=700001)

        with (
            patch("app.api.v1.endpoints.accounts.log_audit_event") as log_mock,
            self.assertRaises(ApiError) as captured,
        ):
            await account_endpoints.generate_telegram_link(
                request,
                session=object(),
                current_account=current_account,
            )

        self.assertEqual(captured.exception.error_code, "telegram_already_linked")
        log_mock.assert_called_once()

    async def test_generate_telegram_link_formats_url_and_commits(self) -> None:
        request = _make_request("/api/v1/accounts/link-telegram")
        current_account = _make_account(telegram_id=None)
        session = SimpleNamespace(commit=AsyncMock())

        with (
            patch(
                "app.api.v1.endpoints.accounts.create_telegram_link_token",
                new=AsyncMock(
                    return_value=(
                        "link-token",
                        "https://t.me/{bot_username}?start=link-token",
                    )
                ),
            ) as token_mock,
            patch("app.api.v1.endpoints.accounts.log_audit_event") as log_mock,
        ):
            result = await account_endpoints.generate_telegram_link(
                request,
                session=session,
                current_account=current_account,
            )

        self.assertEqual(result.link_url, "https://t.me/test_bot?start=link-token")
        self.assertEqual(result.link_token, "link-token")
        token_mock.assert_awaited_once()
        session.commit.assert_awaited_once()
        log_mock.assert_called_once()

    async def test_generate_browser_link_requires_telegram_account(self) -> None:
        request = _make_request("/api/v1/accounts/link-browser")
        current_account = _make_account(telegram_id=None)

        with self.assertRaises(ApiError) as captured:
            await account_endpoints.generate_browser_link(
                request,
                session=object(),
                current_account=current_account,
            )

        self.assertEqual(captured.exception.error_code, "telegram_required")

    async def test_generate_browser_link_requires_webapp_url(self) -> None:
        request = _make_request("/api/v1/accounts/link-browser")
        current_account = _make_account(telegram_id=700001)
        settings.webapp_url = ""

        with self.assertRaises(ApiError) as captured:
            await account_endpoints.generate_browser_link(
                request,
                session=object(),
                current_account=current_account,
            )

        self.assertEqual(captured.exception.error_code, "webapp_url_missing")

    async def test_generate_browser_link_returns_tokenized_url(self) -> None:
        request = _make_request("/api/v1/accounts/link-browser")
        current_account = _make_account(telegram_id=700001)
        session = SimpleNamespace(commit=AsyncMock())

        with patch(
            "app.api.v1.endpoints.accounts.create_browser_link_token",
            new=AsyncMock(
                return_value=("browser-token", "https://webapp.test/link/browser-token")
            ),
        ) as token_mock:
            result = await account_endpoints.generate_browser_link(
                request,
                session=session,
                current_account=current_account,
            )

        self.assertEqual(result.link_token, "browser-token")
        self.assertEqual(result.link_url, "https://webapp.test/link/browser-token")
        token_mock.assert_awaited_once_with(
            session,
            account_id=current_account.id,
            webapp_url="https://webapp.test",
            ttl_seconds=3600,
        )
        session.commit.assert_awaited_once()

    async def test_complete_browser_link_maps_link_token_errors(self) -> None:
        request = _make_request("/api/v1/accounts/link-browser-complete")
        current_account = _make_account()
        payload = account_endpoints.LinkBrowserCompleteRequest(link_token="bad-token")

        with patch(
            "app.api.v1.endpoints.accounts.get_link_token",
            new=AsyncMock(side_effect=LinkTokenTypeMismatchError()),
        ):
            with self.assertRaises(ApiError) as captured:
                await account_endpoints.complete_browser_link(
                    payload,
                    request,
                    session=SimpleNamespace(),
                    credentials=None,
                    current_account=current_account,
                )

        self.assertEqual(captured.exception.error_code, "token_type_invalid")

    async def test_complete_browser_link_rolls_back_on_merge_failures(self) -> None:
        request = _make_request("/api/v1/accounts/link-browser-complete")
        current_account = _make_account()
        payload = account_endpoints.LinkBrowserCompleteRequest(link_token="good-token")
        token = SimpleNamespace(
            account_id=uuid.uuid4(),
            link_type=LinkType.BROWSER_FROM_TELEGRAM,
        )
        session = SimpleNamespace(rollback=AsyncMock())

        with (
            patch(
                "app.api.v1.endpoints.accounts.get_link_token",
                new=AsyncMock(return_value=token),
            ),
            patch(
                "app.api.v1.endpoints.accounts.link_browser_oauth_to_telegram_account",
                new=AsyncMock(side_effect=ValueError("telegram account missing")),
            ),
            self.assertRaises(ApiError) as captured,
        ):
            await account_endpoints.complete_browser_link(
                payload,
                request,
                session=session,
                credentials=None,
                current_account=current_account,
            )

        self.assertEqual(captured.exception.error_code, "account_not_found")
        session.rollback.assert_awaited_once()

    async def test_complete_browser_link_updates_cache_for_successful_merge(
        self,
    ) -> None:
        request = _make_request("/api/v1/accounts/link-browser-complete")
        current_account = _make_account()
        merged_account = _make_account(telegram_id=700777)
        payload = account_endpoints.LinkBrowserCompleteRequest(link_token="good-token")
        token = SimpleNamespace(
            account_id=uuid.uuid4(),
            link_type=LinkType.BROWSER_FROM_TELEGRAM,
        )
        session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
        cache = _DummyCache()
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="access-token"
        )

        with (
            patch(
                "app.api.v1.endpoints.accounts.get_link_token",
                new=AsyncMock(return_value=token),
            ),
            patch(
                "app.api.v1.endpoints.accounts.link_browser_oauth_to_telegram_account",
                new=AsyncMock(return_value=merged_account),
            ),
            patch("app.api.v1.endpoints.accounts.get_cache", return_value=cache),
            patch(
                "app.api.v1.endpoints.accounts.mark_link_token_consumed"
            ) as consume_mock,
        ):
            result = await account_endpoints.complete_browser_link(
                payload,
                request,
                session=session,
                credentials=credentials,
                current_account=current_account,
            )

        self.assertEqual(result.id, merged_account.id)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(merged_account)
        consume_mock.assert_called_once_with(token)
        self.assertEqual(
            cache.saved_tokens,
            [(f"auth:{credentials.credentials}", str(merged_account.id), 321)],
        )

    async def test_complete_browser_link_surfaces_merge_conflict(self) -> None:
        request = _make_request("/api/v1/accounts/link-browser-complete")
        current_account = _make_account()
        payload = account_endpoints.LinkBrowserCompleteRequest(link_token="good-token")
        token = SimpleNamespace(account_id=uuid.uuid4())
        session = SimpleNamespace(rollback=AsyncMock())

        with (
            patch(
                "app.api.v1.endpoints.accounts.get_link_token",
                new=AsyncMock(return_value=token),
            ),
            patch(
                "app.api.v1.endpoints.accounts.link_browser_oauth_to_telegram_account",
                new=AsyncMock(side_effect=AccountMergeConflictError("merge conflict")),
            ),
            self.assertRaises(ApiError) as captured,
        ):
            await account_endpoints.complete_browser_link(
                payload,
                request,
                session=session,
                credentials=None,
                current_account=current_account,
            )

        self.assertEqual(captured.exception.error_code, "merge_conflict")
