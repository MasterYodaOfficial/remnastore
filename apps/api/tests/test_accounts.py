import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy.exc import IntegrityError

from app.services.accounts import (
    AccountIdentityConflictError,
    upsert_supabase_account,
)


class _DummySession:
    def __init__(self) -> None:
        self.rollback = AsyncMock()


class UpsertSupabaseAccountTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_on_auth_provider_unique_violation(self) -> None:
        session = _DummySession()
        expected_account = object()
        integrity_error = IntegrityError(
            "INSERT",
            {},
            Exception("uq_auth_provider_uid"),
        )

        with patch(
            "app.services.accounts._upsert_supabase_account_once",
            new=AsyncMock(side_effect=[integrity_error, expected_account]),
        ) as upsert_once:
            result = await upsert_supabase_account(session, supabase_user=object())

        self.assertIs(result, expected_account)
        session.rollback.assert_awaited_once()
        self.assertEqual(upsert_once.await_count, 2)

    async def test_raises_conflict_after_second_unique_violation(self) -> None:
        session = _DummySession()
        integrity_error = IntegrityError(
            "INSERT",
            {},
            Exception("uq_auth_provider_uid"),
        )

        with patch(
            "app.services.accounts._upsert_supabase_account_once",
            new=AsyncMock(side_effect=[integrity_error, integrity_error]),
        ):
            with self.assertRaises(AccountIdentityConflictError):
                await upsert_supabase_account(session, supabase_user=object())

        self.assertEqual(session.rollback.await_count, 2)
