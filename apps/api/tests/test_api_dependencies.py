import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies import (
    get_current_account,
    get_current_admin,
    require_superuser_admin,
    verify_internal_api_token,
)
from app.api.errors import ApiError
from app.core.config import settings
from app.core.security import TokenError
from app.db.models import Account, AccountStatus
from app.integrations.supabase import (
    SupabaseAuthConfigurationError,
    SupabaseAuthError,
    SupabaseAuthInvalidTokenError,
)
from app.services.accounts import AccountIdentityConflictError


class _DummyCache:
    def __init__(self) -> None:
        self.cached_account_id: str | None = None
        self.deleted_keys: list[tuple[str, ...]] = []
        self.set_calls: list[tuple[str, str, int]] = []

    def auth_token_account_key(self, access_token: str) -> str:
        return f"auth:{access_token}"

    def account_response_key(self, account_id: str) -> str:
        return f"account:{account_id}"

    async def get_str(self, key: str) -> str | None:
        del key
        return self.cached_account_id

    async def set_str(self, key: str, value: str, ttl_seconds: int) -> None:
        self.set_calls.append((key, value, ttl_seconds))

    async def delete(self, *keys: str) -> None:
        self.deleted_keys.append(keys)


class ApiDependenciesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._original_api_token = settings.api_token
        self._original_jwt_secret = settings.jwt_secret
        self._original_auth_ttl = settings.auth_token_cache_ttl_seconds
        settings.api_token = "internal-token"
        settings.jwt_secret = "jwt-secret"
        settings.auth_token_cache_ttl_seconds = 123

    def tearDown(self) -> None:
        settings.api_token = self._original_api_token
        settings.jwt_secret = self._original_jwt_secret
        settings.auth_token_cache_ttl_seconds = self._original_auth_ttl

    @staticmethod
    def _credentials(token: str) -> HTTPAuthorizationCredentials:
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    def test_verify_internal_api_token_requires_configured_secret(self) -> None:
        settings.api_token = ""

        with self.assertRaises(HTTPException) as captured:
            verify_internal_api_token("Bearer internal-token")

        self.assertEqual(captured.exception.status_code, 503)

    def test_verify_internal_api_token_rejects_missing_or_invalid_bearer(self) -> None:
        with self.assertRaises(HTTPException) as captured:
            verify_internal_api_token(None)
        self.assertEqual(captured.exception.status_code, 401)

        with self.assertRaises(HTTPException) as captured:
            verify_internal_api_token("Token value")
        self.assertEqual(captured.exception.status_code, 401)

        with self.assertRaises(HTTPException) as captured:
            verify_internal_api_token("Bearer wrong-token")
        self.assertEqual(captured.exception.status_code, 401)

    def test_verify_internal_api_token_accepts_valid_token(self) -> None:
        verify_internal_api_token("Bearer internal-token")

    async def test_get_current_account_requires_credentials(self) -> None:
        with self.assertRaises(HTTPException) as captured:
            await get_current_account(credentials=None, session=object())

        self.assertEqual(captured.exception.status_code, 401)
        self.assertEqual(captured.exception.detail, "missing credentials")

    async def test_get_current_account_accepts_valid_jwt_subject(self) -> None:
        account = Account(id=uuid.uuid4(), status=AccountStatus.ACTIVE)

        with (
            patch(
                "app.api.dependencies.decode_access_token",
                return_value={"sub": str(account.id)},
            ),
            patch("app.api.dependencies.get_cache", return_value=_DummyCache()),
            patch(
                "app.api.dependencies.get_account_by_id",
                new=AsyncMock(return_value=account),
            ),
        ):
            result = await get_current_account(
                credentials=self._credentials("jwt-token"),
                session=object(),
            )

        self.assertIs(result, account)

    async def test_get_current_account_rejects_missing_jwt_subject(self) -> None:
        with (
            patch(
                "app.api.dependencies.decode_access_token",
                return_value={"scope": "account"},
            ),
            patch("app.api.dependencies.get_cache", return_value=_DummyCache()),
        ):
            with self.assertRaises(HTTPException) as captured:
                await get_current_account(
                    credentials=self._credentials("jwt-token"),
                    session=object(),
                )

        self.assertEqual(captured.exception.status_code, 401)
        self.assertEqual(captured.exception.detail, "token missing subject")

    async def test_get_current_account_rejects_missing_or_blocked_account(self) -> None:
        with (
            patch(
                "app.api.dependencies.decode_access_token",
                return_value={"sub": str(uuid.uuid4())},
            ),
            patch("app.api.dependencies.get_cache", return_value=_DummyCache()),
            patch(
                "app.api.dependencies.get_account_by_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            with self.assertRaises(HTTPException) as captured:
                await get_current_account(
                    credentials=self._credentials("jwt-token"),
                    session=object(),
                )
        self.assertEqual(captured.exception.detail, "account not found")

        blocked_account = Account(id=uuid.uuid4(), status=AccountStatus.BLOCKED)
        with (
            patch(
                "app.api.dependencies.decode_access_token",
                return_value={"sub": str(blocked_account.id)},
            ),
            patch("app.api.dependencies.get_cache", return_value=_DummyCache()),
            patch(
                "app.api.dependencies.get_account_by_id",
                new=AsyncMock(return_value=blocked_account),
            ),
        ):
            with self.assertRaises(HTTPException) as captured:
                await get_current_account(
                    credentials=self._credentials("jwt-token"),
                    session=object(),
                )
        self.assertEqual(captured.exception.status_code, 403)
        self.assertEqual(captured.exception.detail, "account blocked")

    async def test_get_current_account_uses_cached_account_when_jwt_is_invalid(
        self,
    ) -> None:
        account = Account(id=uuid.uuid4(), status=AccountStatus.ACTIVE)
        cache = _DummyCache()
        cache.cached_account_id = str(account.id)

        with (
            patch(
                "app.api.dependencies.decode_access_token",
                side_effect=TokenError("invalid"),
            ),
            patch("app.api.dependencies.get_cache", return_value=cache),
            patch(
                "app.api.dependencies.get_account_by_id",
                new=AsyncMock(return_value=account),
            ),
            patch("app.api.dependencies.SupabaseAuthClient") as supabase_client,
        ):
            result = await get_current_account(
                credentials=self._credentials("bearer-token"),
                session=object(),
            )

        self.assertIs(result, account)
        supabase_client.assert_not_called()

    async def test_get_current_account_deletes_stale_cache_then_falls_back_to_supabase(
        self,
    ) -> None:
        account = Account(id=uuid.uuid4(), status=AccountStatus.ACTIVE)
        cache = _DummyCache()
        cache.cached_account_id = str(uuid.uuid4())
        supabase_client = SimpleNamespace(get_user=AsyncMock(return_value=object()))

        with (
            patch(
                "app.api.dependencies.decode_access_token",
                side_effect=TokenError("invalid"),
            ),
            patch("app.api.dependencies.get_cache", return_value=cache),
            patch(
                "app.api.dependencies.get_account_by_id",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.dependencies.SupabaseAuthClient",
                return_value=supabase_client,
            ),
            patch(
                "app.api.dependencies.upsert_supabase_account",
                new=AsyncMock(return_value=account),
            ),
        ):
            result = await get_current_account(
                credentials=self._credentials("supabase-token"),
                session=object(),
            )

        self.assertIs(result, account)
        self.assertEqual(
            cache.deleted_keys,
            [("auth:supabase-token", f"account:{cache.cached_account_id}")],
        )
        self.assertEqual(
            cache.set_calls,
            [("auth:supabase-token", str(account.id), 123)],
        )

    async def test_get_current_account_maps_supabase_errors(self) -> None:
        cache = _DummyCache()

        for error, expected_status in (
            (
                SupabaseAuthConfigurationError("bad configuration"),
                500,
            ),
            (
                SupabaseAuthInvalidTokenError("invalid token"),
                401,
            ),
            (
                SupabaseAuthError("gateway error"),
                502,
            ),
        ):
            supabase_client = SimpleNamespace(get_user=AsyncMock(side_effect=error))
            with (
                patch(
                    "app.api.dependencies.decode_access_token",
                    side_effect=TokenError("invalid"),
                ),
                patch("app.api.dependencies.get_cache", return_value=cache),
                patch(
                    "app.api.dependencies.SupabaseAuthClient",
                    return_value=supabase_client,
                ),
            ):
                with self.assertRaises(HTTPException) as captured:
                    await get_current_account(
                        credentials=self._credentials("supabase-token"),
                        session=object(),
                    )
            self.assertEqual(captured.exception.status_code, expected_status)

    async def test_get_current_account_maps_identity_conflict_and_blocked_supabase_account(
        self,
    ) -> None:
        cache = _DummyCache()
        supabase_client = SimpleNamespace(get_user=AsyncMock(return_value=object()))

        with (
            patch(
                "app.api.dependencies.decode_access_token",
                side_effect=TokenError("invalid"),
            ),
            patch("app.api.dependencies.get_cache", return_value=cache),
            patch(
                "app.api.dependencies.SupabaseAuthClient",
                return_value=supabase_client,
            ),
            patch(
                "app.api.dependencies.upsert_supabase_account",
                new=AsyncMock(side_effect=AccountIdentityConflictError("conflict")),
            ),
        ):
            with self.assertRaises(HTTPException) as captured:
                await get_current_account(
                    credentials=self._credentials("supabase-token"),
                    session=object(),
                )
        self.assertEqual(captured.exception.status_code, 409)

        blocked_account = Account(id=uuid.uuid4(), status=AccountStatus.BLOCKED)
        with (
            patch(
                "app.api.dependencies.decode_access_token",
                side_effect=TokenError("invalid"),
            ),
            patch("app.api.dependencies.get_cache", return_value=cache),
            patch(
                "app.api.dependencies.SupabaseAuthClient",
                return_value=supabase_client,
            ),
            patch(
                "app.api.dependencies.upsert_supabase_account",
                new=AsyncMock(return_value=blocked_account),
            ),
        ):
            with self.assertRaises(HTTPException) as captured:
                await get_current_account(
                    credentials=self._credentials("supabase-token"),
                    session=object(),
                )
        self.assertEqual(captured.exception.status_code, 403)
        self.assertEqual(captured.exception.detail, "account blocked")

    async def test_get_current_admin_validates_token_and_admin_state(self) -> None:
        with self.assertRaises(ApiError) as captured:
            await get_current_admin(credentials=None, session=object())
        self.assertEqual(captured.exception.error_code, "admin_missing_credentials")

        with patch(
            "app.api.dependencies.decode_access_token",
            side_effect=TokenError("invalid"),
        ):
            with self.assertRaises(ApiError) as captured:
                await get_current_admin(
                    credentials=self._credentials("admin-token"),
                    session=object(),
                )
        self.assertEqual(captured.exception.error_code, "admin_invalid_token")

        with patch(
            "app.api.dependencies.decode_access_token",
            return_value={"scope": "user", "sub": "admin-id"},
        ):
            with self.assertRaises(ApiError) as captured:
                await get_current_admin(
                    credentials=self._credentials("admin-token"),
                    session=object(),
                )
        self.assertEqual(captured.exception.error_code, "admin_invalid_scope")

        with patch(
            "app.api.dependencies.decode_access_token",
            return_value={"scope": "admin"},
        ):
            with self.assertRaises(ApiError) as captured:
                await get_current_admin(
                    credentials=self._credentials("admin-token"),
                    session=object(),
                )
        self.assertEqual(captured.exception.error_code, "admin_token_missing_subject")

        disabled_admin = SimpleNamespace(is_active=False, is_superuser=False)
        with (
            patch(
                "app.api.dependencies.decode_access_token",
                return_value={"scope": "admin", "sub": "admin-id"},
            ),
            patch(
                "app.api.dependencies.get_admin_by_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            with self.assertRaises(ApiError) as captured:
                await get_current_admin(
                    credentials=self._credentials("admin-token"),
                    session=object(),
                )
        self.assertEqual(captured.exception.error_code, "admin_not_found")

        with (
            patch(
                "app.api.dependencies.decode_access_token",
                return_value={"scope": "admin", "sub": "admin-id"},
            ),
            patch(
                "app.api.dependencies.get_admin_by_id",
                new=AsyncMock(return_value=disabled_admin),
            ),
        ):
            with self.assertRaises(ApiError) as captured:
                await get_current_admin(
                    credentials=self._credentials("admin-token"),
                    session=object(),
                )
        self.assertEqual(captured.exception.error_code, "admin_disabled")

    async def test_get_current_admin_and_require_superuser_succeed(self) -> None:
        admin = SimpleNamespace(is_active=True, is_superuser=True)

        with (
            patch(
                "app.api.dependencies.decode_access_token",
                return_value={"scope": "admin", "sub": "admin-id"},
            ),
            patch(
                "app.api.dependencies.get_admin_by_id",
                new=AsyncMock(return_value=admin),
            ),
        ):
            current_admin = await get_current_admin(
                credentials=self._credentials("admin-token"),
                session=object(),
            )

        self.assertIs(current_admin, admin)
        self.assertIs(await require_superuser_admin(current_admin), admin)

        with self.assertRaises(ApiError) as captured:
            await require_superuser_admin(
                SimpleNamespace(is_active=True, is_superuser=False)
            )
        self.assertEqual(captured.exception.error_code, "admin_superuser_required")
