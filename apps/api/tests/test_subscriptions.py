import hashlib
import hmac
import json
from dataclasses import dataclass
from decimal import Decimal
from datetime import UTC, datetime, timedelta
import tempfile
import unittest
import uuid
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_account
from app.core.config import settings
from app.db.base import Base
from app.db.models import (
    Account,
    AccountEventLog,
    AccountStatus,
    LedgerEntry,
    LedgerEntryType,
    Notification,
    NotificationType,
    SubscriptionGrant,
)
from app.db.session import get_session
from app.integrations.remnawave.client import RemnawaveRequestError, RemnawaveUser
from app.main import create_app
from app.services.i18n import translate
from app.services.referrals import calculate_referral_reward_amount
from app.services.plans import get_subscription_plans
from app.services.purchases import reconcile_pending_wallet_plan_purchases
from app.services import subscriptions as subscriptions_service

PLAN_1M = next(plan for plan in get_subscription_plans() if plan.code == "plan_1m")
PLAN_1M_PRICE_RUB = PLAN_1M.price_rub


def _referral_reward(amount: int, *, rate: float | Decimal) -> int:
    return calculate_referral_reward_amount(
        purchase_amount_rub=amount,
        reward_rate=Decimal(str(rate)),
    )


class DummyCache:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def auth_token_account_key(self, access_token: str) -> str:
        return f"auth:{access_token}"

    def account_response_key(self, account_id: str) -> str:
        return f"account:{account_id}"

    async def get_str(self, key: str) -> str | None:
        return self._values.get(key)

    async def set_str(self, key: str, value: str, ttl_seconds: int) -> None:
        del ttl_seconds
        self._values[key] = value

    async def get_json(self, key: str):
        del key
        return None

    async def set_json(self, key: str, value, ttl_seconds: int) -> None:
        del key, value, ttl_seconds

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._values.pop(key, None)


@dataclass
class FakeRemnawaveGateway:
    users: dict[uuid.UUID, RemnawaveUser]

    async def get_user_by_uuid(self, user_uuid: uuid.UUID) -> RemnawaveUser | None:
        return self.users.get(user_uuid)

    async def get_users_by_email(self, email: str) -> list[RemnawaveUser]:
        return [user for user in self.users.values() if user.email == email]

    async def get_users_by_telegram_id(self, telegram_id: int) -> list[RemnawaveUser]:
        return [user for user in self.users.values() if user.telegram_id == telegram_id]

    async def provision_user(
        self,
        *,
        user_uuid: uuid.UUID,
        expire_at: datetime,
        email: str | None,
        telegram_id: int | None,
        is_trial: bool,
    ) -> RemnawaveUser:
        user = RemnawaveUser(
            uuid=user_uuid,
            username=f"acc_{user_uuid.hex}",
            status="ACTIVE",
            expire_at=expire_at,
            subscription_url=f"https://panel.test/sub/{user_uuid.hex[:8]}",
            telegram_id=telegram_id,
            email=email,
            tag="TRIAL" if is_trial else None,
        )
        self.users[user_uuid] = user
        return user


class UnavailableRemnawaveGateway:
    async def get_user_by_uuid(self, user_uuid: uuid.UUID) -> RemnawaveUser | None:
        del user_uuid
        raise RemnawaveRequestError("ConnectError")

    async def get_users_by_email(self, email: str) -> list[RemnawaveUser]:
        del email
        raise RemnawaveRequestError("ConnectError")

    async def get_users_by_telegram_id(self, telegram_id: int) -> list[RemnawaveUser]:
        del telegram_id
        raise RemnawaveRequestError("ConnectError")

    async def provision_user(
        self,
        *,
        user_uuid: uuid.UUID,
        expire_at: datetime,
        email: str | None,
        telegram_id: int | None,
        is_trial: bool,
    ) -> RemnawaveUser:
        del user_uuid, expire_at, email, telegram_id, is_trial
        raise RemnawaveRequestError("ConnectError")


class MissingSubscriptionUrlGateway(FakeRemnawaveGateway):
    async def provision_user(
        self,
        *,
        user_uuid: uuid.UUID,
        expire_at: datetime,
        email: str | None,
        telegram_id: int | None,
        is_trial: bool,
    ) -> RemnawaveUser:
        user = await super().provision_user(
            user_uuid=user_uuid,
            expire_at=expire_at,
            email=email,
            telegram_id=telegram_id,
            is_trial=is_trial,
        )
        user.subscription_url = " "
        self.users[user_uuid] = user
        return user


@dataclass
class SelectivelyUnavailableRemnawaveGateway(FakeRemnawaveGateway):
    failing_user_ids: set[uuid.UUID]

    async def provision_user(
        self,
        *,
        user_uuid: uuid.UUID,
        expire_at: datetime,
        email: str | None,
        telegram_id: int | None,
        is_trial: bool,
    ) -> RemnawaveUser:
        if user_uuid in self.failing_user_ids:
            raise RemnawaveRequestError("ConnectError")
        return await super().provision_user(
            user_uuid=user_uuid,
            expire_at=expire_at,
            email=email,
            telegram_id=telegram_id,
            is_trial=is_trial,
        )


class SubscriptionFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "subscriptions.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._current_account_id: uuid.UUID | None = None
        self._fake_gateway = FakeRemnawaveGateway(users={})

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()

        self._original_trial_duration_days = settings.trial_duration_days
        self._original_api_token = settings.api_token
        settings.trial_duration_days = 3
        settings.api_token = "internal-token"
        self._original_remnawave_webhook_secret = settings.remnawave_webhook_secret
        settings.remnawave_webhook_secret = "test-remnawave-secret"

        self._original_gateway_factory = subscriptions_service.get_remnawave_gateway
        subscriptions_service.get_remnawave_gateway = lambda: self._fake_gateway

        self.app = create_app()

        async def override_get_session():
            async with self._session_factory() as session:
                yield session

        async def override_get_current_account():
            if self._current_account_id is None:
                raise AssertionError(
                    "current account is not configured for test request"
                )

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

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        settings.trial_duration_days = self._original_trial_duration_days
        settings.api_token = self._original_api_token
        settings.remnawave_webhook_secret = self._original_remnawave_webhook_secret
        subscriptions_service.get_remnawave_gateway = self._original_gateway_factory
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

    async def _get_ledger_entries(self, account_id: uuid.UUID) -> list[LedgerEntry]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(LedgerEntry)
                .where(LedgerEntry.account_id == account_id)
                .order_by(LedgerEntry.id.asc())
            )
            return list(result.scalars().all())

    async def _get_subscription_grants(
        self, account_id: uuid.UUID
    ) -> list[SubscriptionGrant]:
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

    async def _get_account_event_logs(
        self, account_id: uuid.UUID
    ) -> list[AccountEventLog]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AccountEventLog)
                .where(AccountEventLog.account_id == account_id)
                .order_by(AccountEventLog.id.asc())
            )
            return list(result.scalars().all())

    async def test_activate_trial_creates_remote_user_and_marks_snapshot(self) -> None:
        account = await self._create_account(email="trial@example.com")
        self._current_account_id = account.id

        response = await self.client.post("/api/v1/subscriptions/trial")
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["remnawave_user_uuid"], str(account.id))
        self.assertEqual(body["status"], "ACTIVE")
        self.assertTrue(body["is_active"])
        self.assertTrue(body["is_trial"])
        self.assertTrue(body["has_used_trial"])
        self.assertIsNotNone(body["subscription_url"])
        self.assertIsNotNone(body["trial_used_at"])
        self.assertIsNotNone(body["trial_ends_at"])

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.remnawave_user_uuid, account.id)
        self.assertEqual(stored_account.subscription_status, "ACTIVE")
        self.assertTrue(stored_account.subscription_is_trial)
        self.assertIsNotNone(stored_account.trial_used_at)
        self.assertIsNotNone(stored_account.trial_ends_at)

        event_logs = await self._get_account_event_logs(account.id)
        self.assertEqual(
            [item.event_type for item in event_logs], ["subscription.trial.activated"]
        )
        self.assertEqual(event_logs[0].source, "api")

    async def test_internal_bot_trial_activation_persists_bot_source(self) -> None:
        account = await self._create_account(
            email="trial-bot@example.com",
            telegram_id=758107031,
        )

        response = await self.client.post(
            f"/api/v1/internal/bot/subscriptions/trial/{account.telegram_id}",
            headers={"Authorization": "Bearer internal-token"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["telegram_id"], account.telegram_id)
        self.assertTrue(body["exists"])
        self.assertEqual(body["subscription"]["status"], "ACTIVE")
        self.assertTrue(body["subscription"]["is_trial"])

        event_logs = await self._get_account_event_logs(account.id)
        self.assertEqual(
            [item.event_type for item in event_logs], ["subscription.trial.activated"]
        )
        self.assertEqual(event_logs[0].source, "bot")

    async def test_bootstrap_me_uses_local_snapshot_without_remnawave_call(
        self,
    ) -> None:
        account = await self._create_account(email="bootstrap@example.com")
        self._current_account_id = account.id
        subscriptions_service.get_remnawave_gateway = lambda: (
            UnavailableRemnawaveGateway()
        )

        response = await self.client.get("/api/v1/bootstrap/me")
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(body["account"]["id"], str(account.id))
        self.assertEqual(body["subscription"]["remnawave_user_uuid"], None)
        self.assertEqual(body["trial_ui"]["can_start_now"], True)
        self.assertEqual(body["trial_ui"]["reason"], None)
        self.assertEqual(body["trial_ui"]["has_used_trial"], False)
        self.assertEqual(body["trial_ui"]["strict_check_required_on_start"], True)

    async def test_activate_trial_rejects_second_attempt(self) -> None:
        account = await self._create_account(email="trial-repeat@example.com")
        self._current_account_id = account.id

        first_response = await self.client.post("/api/v1/subscriptions/trial")
        self.assertEqual(first_response.status_code, 200)

        second_response = await self.client.post("/api/v1/subscriptions/trial")
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(second_response.json()["detail"], "trial_already_used")
        self.assertEqual(second_response.json()["error_code"], "trial_already_used")

    async def test_trial_eligibility_rejects_remnawave_identity_conflict(self) -> None:
        account = await self._create_account(
            email="conflict@example.com",
            telegram_id=777001,
        )
        self._current_account_id = account.id

        foreign_uuid = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self._fake_gateway.users[foreign_uuid] = RemnawaveUser(
            uuid=foreign_uuid,
            username=f"acc_{foreign_uuid.hex}",
            status="ACTIVE",
            expire_at=datetime.now(UTC) + timedelta(days=30),
            subscription_url="https://panel.test/sub/conflict",
            telegram_id=account.telegram_id,
            email=account.email,
            tag=None,
        )

        eligibility_response = await self.client.get(
            "/api/v1/subscriptions/trial-eligibility"
        )
        self.assertEqual(eligibility_response.status_code, 200)
        self.assertEqual(eligibility_response.json()["eligible"], False)
        self.assertEqual(
            eligibility_response.json()["reason"],
            "remnawave_identity_conflict",
        )

        activation_response = await self.client.post("/api/v1/subscriptions/trial")
        self.assertEqual(activation_response.status_code, 400)
        self.assertEqual(
            activation_response.json()["detail"],
            "remnawave_identity_conflict",
        )

    async def test_activate_trial_rejects_blocked_account(self) -> None:
        account = await self._create_account(
            email="blocked@example.com",
            status=AccountStatus.BLOCKED,
        )
        self._current_account_id = account.id

        response = await self.client.post("/api/v1/subscriptions/trial")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "account_blocked")
        self.assertEqual(response.json()["error_code"], "account_blocked")

    async def test_wallet_plan_purchase_rejects_blocked_account(self) -> None:
        account = await self._create_account(
            email="blocked-wallet@example.com",
            balance=1000,
            status=AccountStatus.BLOCKED,
        )
        self._current_account_id = account.id

        response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "blocked-wallet-plan-1m"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            translate("api.subscriptions.errors.account_blocked_purchase"),
        )
        self.assertEqual(response.json()["error_code"], "account_blocked_purchase")

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 1000)
        self.assertIsNone(stored_account.subscription_status)

    async def test_trial_eligibility_reports_remnawave_unavailable(self) -> None:
        account = await self._create_account(email="unavailable@example.com")
        self._current_account_id = account.id

        subscriptions_service.get_remnawave_gateway = lambda: (
            UnavailableRemnawaveGateway()
        )

        eligibility_response = await self.client.get(
            "/api/v1/subscriptions/trial-eligibility"
        )
        self.assertEqual(eligibility_response.status_code, 200)
        self.assertEqual(eligibility_response.json()["eligible"], False)
        self.assertEqual(
            eligibility_response.json()["reason"],
            "remnawave_unavailable",
        )

        activation_response = await self.client.post("/api/v1/subscriptions/trial")
        self.assertEqual(activation_response.status_code, 502)
        self.assertEqual(
            activation_response.json()["detail"],
            "remnawave_unavailable",
        )

    async def test_activate_trial_fails_when_remnawave_returns_empty_subscription_url(
        self,
    ) -> None:
        account = await self._create_account(email="trial-empty-url@example.com")
        self._current_account_id = account.id
        subscriptions_service.get_remnawave_gateway = lambda: (
            MissingSubscriptionUrlGateway(users={})
        )

        response = await self.client.post("/api/v1/subscriptions/trial")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"],
            translate("api.purchases.errors.remnawave_subscription_url_missing"),
        )

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertIsNone(stored_account.subscription_url)
        self.assertIsNone(stored_account.subscription_status)
        self.assertFalse(stored_account.has_used_trial)

    async def test_wallet_plan_purchase_debits_balance_and_applies_subscription(
        self,
    ) -> None:
        account = await self._create_account(email="wallet@example.com", balance=1000)
        self._current_account_id = account.id

        response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-plan-1m"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["status"], "ACTIVE")
        self.assertFalse(body["is_trial"])
        self.assertTrue(body["subscription_url"])

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 1000 - PLAN_1M_PRICE_RUB)
        self.assertEqual(stored_account.subscription_status, "ACTIVE")
        self.assertTrue(stored_account.subscription_url)

        entries = await self._get_ledger_entries(account.id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].entry_type, LedgerEntryType.SUBSCRIPTION_DEBIT)
        self.assertEqual(entries[0].amount, -PLAN_1M_PRICE_RUB)

        grants = await self._get_subscription_grants(account.id)
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0].purchase_source, "wallet")
        self.assertEqual(grants[0].reference_type, "wallet_purchase")
        self.assertEqual(grants[0].reference_id, "wallet-plan-1m")

        event_types = [
            item.event_type for item in await self._get_account_event_logs(account.id)
        ]
        self.assertIn("subscription.wallet_purchase.staged", event_types)
        self.assertIn("subscription.wallet_purchase.applied", event_types)
        self.assertIsNotNone(grants[0].applied_at)

    async def test_wallet_plan_purchase_after_trial_clears_current_trial_flag(
        self,
    ) -> None:
        account = await self._create_account(
            email="trial-to-paid@example.com", balance=1000
        )
        self._current_account_id = account.id

        trial_response = await self.client.post("/api/v1/subscriptions/trial")
        self.assertEqual(trial_response.status_code, 200)
        self.assertTrue(trial_response.json()["is_trial"])

        paid_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "trial-to-paid-plan-1m"},
        )
        self.assertEqual(paid_response.status_code, 200)
        paid_body = paid_response.json()

        self.assertFalse(paid_body["is_trial"])
        self.assertTrue(paid_body["has_used_trial"])
        self.assertIsNotNone(paid_body["trial_used_at"])
        self.assertIsNotNone(paid_body["trial_ends_at"])

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertFalse(stored_account.subscription_is_trial)
        self.assertIsNotNone(stored_account.trial_used_at)
        self.assertIsNotNone(stored_account.trial_ends_at)

    async def test_wallet_plan_purchase_same_idempotency_key_is_safe_to_repeat(
        self,
    ) -> None:
        account = await self._create_account(
            email="wallet-repeat@example.com", balance=1000
        )
        self._current_account_id = account.id

        first_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-repeat"},
        )
        self.assertEqual(first_response.status_code, 200)
        first_expires_at = first_response.json()["expires_at"]

        second_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-repeat"},
        )
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["expires_at"], first_expires_at)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 1000 - PLAN_1M_PRICE_RUB)

        entries = await self._get_ledger_entries(account.id)
        self.assertEqual(len(entries), 1)
        grants = await self._get_subscription_grants(account.id)
        self.assertEqual(len(grants), 1)

    async def test_wallet_plan_purchase_rejects_insufficient_funds(self) -> None:
        account = await self._create_account(
            email="wallet-low@example.com", balance=100
        )
        self._current_account_id = account.id

        response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-low"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            translate("api.ledger.errors.insufficient_funds"),
        )

        entries = await self._get_ledger_entries(account.id)
        self.assertEqual(entries, [])
        grants = await self._get_subscription_grants(account.id)
        self.assertEqual(grants, [])

    async def test_wallet_plan_purchase_can_resume_after_remnawave_failure(
        self,
    ) -> None:
        account = await self._create_account(
            email="wallet-resume@example.com", balance=1000
        )
        self._current_account_id = account.id
        subscriptions_service.get_remnawave_gateway = lambda: (
            UnavailableRemnawaveGateway()
        )

        first_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-resume"},
        )
        self.assertEqual(first_response.status_code, 502)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 1000 - PLAN_1M_PRICE_RUB)
        self.assertIsNone(stored_account.subscription_status)

        entries = await self._get_ledger_entries(account.id)
        self.assertEqual(len(entries), 1)
        grants = await self._get_subscription_grants(account.id)
        self.assertEqual(len(grants), 1)
        self.assertIsNone(grants[0].applied_at)

        subscriptions_service.get_remnawave_gateway = lambda: self._fake_gateway
        second_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-resume"},
        )
        self.assertEqual(second_response.status_code, 200)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 1000 - PLAN_1M_PRICE_RUB)
        self.assertEqual(stored_account.subscription_status, "ACTIVE")

        entries = await self._get_ledger_entries(account.id)
        self.assertEqual(len(entries), 1)
        grants = await self._get_subscription_grants(account.id)
        self.assertEqual(len(grants), 1)
        self.assertIsNotNone(grants[0].applied_at)

    async def test_wallet_plan_purchase_repeat_with_new_idempotency_resumes_pending_grant(
        self,
    ) -> None:
        account = await self._create_account(
            email="wallet-repeat-pending@example.com", balance=1000
        )
        self._current_account_id = account.id
        subscriptions_service.get_remnawave_gateway = lambda: (
            UnavailableRemnawaveGateway()
        )

        first_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-pending-first"},
        )
        self.assertEqual(first_response.status_code, 502)

        subscriptions_service.get_remnawave_gateway = lambda: self._fake_gateway
        second_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-pending-second"},
        )
        self.assertEqual(second_response.status_code, 200)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 1000 - PLAN_1M_PRICE_RUB)
        self.assertEqual(stored_account.subscription_status, "ACTIVE")

        entries = await self._get_ledger_entries(account.id)
        self.assertEqual(len(entries), 1)
        grants = await self._get_subscription_grants(account.id)
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0].reference_id, "wallet-pending-first")
        self.assertIsNotNone(grants[0].applied_at)

    async def test_wallet_plan_purchase_rejects_new_plan_while_previous_wallet_grant_pending(
        self,
    ) -> None:
        account = await self._create_account(
            email="wallet-pending-conflict@example.com", balance=5000
        )
        self._current_account_id = account.id
        subscriptions_service.get_remnawave_gateway = lambda: (
            UnavailableRemnawaveGateway()
        )

        first_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-pending-conflict-first"},
        )
        self.assertEqual(first_response.status_code, 502)

        alternate_plan_code = next(
            plan.code for plan in get_subscription_plans() if plan.code != "plan_1m"
        )
        second_response = await self.client.post(
            f"/api/v1/subscriptions/wallet/plans/{alternate_plan_code}",
            json={"idempotency_key": "wallet-pending-conflict-second"},
        )
        self.assertEqual(second_response.status_code, 409)
        self.assertEqual(
            second_response.json()["detail"],
            translate("api.purchases.errors.wallet_pending_purchase"),
        )

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 5000 - PLAN_1M_PRICE_RUB)
        self.assertIsNone(stored_account.subscription_status)

        entries = await self._get_ledger_entries(account.id)
        self.assertEqual(len(entries), 1)
        grants = await self._get_subscription_grants(account.id)
        self.assertEqual(len(grants), 1)
        self.assertIsNone(grants[0].applied_at)

    async def test_reconcile_pending_wallet_plan_purchases_applies_staged_purchase(
        self,
    ) -> None:
        account = await self._create_account(
            email="wallet-reconcile@example.com", balance=1000
        )
        self._current_account_id = account.id
        subscriptions_service.get_remnawave_gateway = lambda: (
            UnavailableRemnawaveGateway()
        )

        first_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-reconcile"},
        )
        self.assertEqual(first_response.status_code, 502)

        async with self._session_factory() as session:
            result = await reconcile_pending_wallet_plan_purchases(
                session,
                limit=10,
                gateway_factory=lambda: self._fake_gateway,
            )

        self.assertEqual(result.processed, 1)
        self.assertEqual(result.applied, 1)
        self.assertEqual(result.still_pending, 0)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 1000 - PLAN_1M_PRICE_RUB)
        self.assertEqual(stored_account.subscription_status, "ACTIVE")
        self.assertTrue(stored_account.subscription_url)

        grants = await self._get_subscription_grants(account.id)
        self.assertEqual(len(grants), 1)
        self.assertIsNotNone(grants[0].applied_at)

    async def test_reconcile_pending_wallet_plan_purchases_continues_after_rollback(
        self,
    ) -> None:
        failing_account = await self._create_account(
            email="wallet-reconcile-fail@example.com", balance=1000
        )
        successful_account = await self._create_account(
            email="wallet-reconcile-success@example.com", balance=1000
        )
        subscriptions_service.get_remnawave_gateway = lambda: (
            UnavailableRemnawaveGateway()
        )

        self._current_account_id = failing_account.id
        first_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-reconcile-failing"},
        )
        self.assertEqual(first_response.status_code, 502)

        self._current_account_id = successful_account.id
        second_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-reconcile-successful"},
        )
        self.assertEqual(second_response.status_code, 502)

        reconcile_gateway = SelectivelyUnavailableRemnawaveGateway(
            users={},
            failing_user_ids={failing_account.id},
        )
        async with self._session_factory() as session:
            result = await reconcile_pending_wallet_plan_purchases(
                session,
                limit=10,
                gateway_factory=lambda: reconcile_gateway,
            )

        self.assertEqual(result.processed, 2)
        self.assertEqual(result.applied, 1)
        self.assertEqual(result.still_pending, 1)

        failing_grants = await self._get_subscription_grants(failing_account.id)
        self.assertEqual(len(failing_grants), 1)
        self.assertIsNone(failing_grants[0].applied_at)

        successful_grants = await self._get_subscription_grants(successful_account.id)
        self.assertEqual(len(successful_grants), 1)
        self.assertIsNotNone(successful_grants[0].applied_at)

        stored_successful_account = await self._get_account(successful_account.id)
        self.assertIsNotNone(stored_successful_account)
        assert stored_successful_account is not None
        self.assertEqual(stored_successful_account.subscription_status, "ACTIVE")
        self.assertTrue(stored_successful_account.subscription_url)

    async def test_wallet_plan_purchase_can_resume_after_empty_subscription_url(
        self,
    ) -> None:
        account = await self._create_account(
            email="wallet-empty-url@example.com", balance=1000
        )
        self._current_account_id = account.id
        subscriptions_service.get_remnawave_gateway = lambda: (
            MissingSubscriptionUrlGateway(users={})
        )

        first_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-empty-url"},
        )
        self.assertEqual(first_response.status_code, 502)
        self.assertEqual(
            first_response.json()["detail"],
            translate("api.purchases.errors.remnawave_subscription_url_missing"),
        )

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 1000 - PLAN_1M_PRICE_RUB)
        self.assertIsNone(stored_account.subscription_url)
        self.assertIsNone(stored_account.subscription_status)

        grants = await self._get_subscription_grants(account.id)
        self.assertEqual(len(grants), 1)
        self.assertIsNone(grants[0].applied_at)

        subscriptions_service.get_remnawave_gateway = lambda: self._fake_gateway
        second_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-empty-url"},
        )
        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(second_response.json()["subscription_url"])

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 1000 - PLAN_1M_PRICE_RUB)
        self.assertTrue(stored_account.subscription_url)

        grants = await self._get_subscription_grants(account.id)
        self.assertEqual(len(grants), 1)
        self.assertIsNotNone(grants[0].applied_at)

    async def test_wallet_plan_purchase_applies_first_referral_reward(self) -> None:
        referrer = await self._create_account(
            email="referrer@example.com",
            referral_code="ref-wallet",
        )
        account = await self._create_account(
            email="wallet-ref@example.com",
            balance=1000,
            referral_code="ref-wallet-user",
        )
        self._current_account_id = account.id

        claim_response = await self.client.post(
            "/api/v1/referrals/claim",
            json={"referral_code": "ref-wallet"},
        )
        self.assertEqual(claim_response.status_code, 200)

        response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-referral-reward"},
        )
        self.assertEqual(response.status_code, 200)

        stored_referrer = await self._get_account(referrer.id)
        self.assertIsNotNone(stored_referrer)
        assert stored_referrer is not None
        self.assertEqual(stored_referrer.referrals_count, 1)
        self.assertEqual(
            stored_referrer.referral_earnings,
            _referral_reward(
                PLAN_1M_PRICE_RUB,
                rate=settings.default_referral_reward_rate,
            ),
        )

        referrer_entries = await self._get_ledger_entries(referrer.id)
        self.assertEqual(len(referrer_entries), 1)
        self.assertEqual(
            referrer_entries[0].entry_type, LedgerEntryType.REFERRAL_REWARD
        )
        self.assertEqual(
            referrer_entries[0].amount,
            _referral_reward(
                PLAN_1M_PRICE_RUB,
                rate=settings.default_referral_reward_rate,
            ),
        )

    async def test_wallet_plan_repeat_purchase_extends_active_subscription(
        self,
    ) -> None:
        account = await self._create_account(
            email="wallet-extend@example.com", balance=2000
        )
        self._current_account_id = account.id

        first_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-extend-1"},
        )
        self.assertEqual(first_response.status_code, 200)
        first_expires_at = datetime.fromisoformat(
            first_response.json()["expires_at"].replace("Z", "+00:00")
        )

        second_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-extend-2"},
        )
        self.assertEqual(second_response.status_code, 200)
        second_expires_at = datetime.fromisoformat(
            second_response.json()["expires_at"].replace("Z", "+00:00")
        )

        self.assertGreater(second_expires_at, first_expires_at + timedelta(days=29))

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 2000 - (PLAN_1M_PRICE_RUB * 2))

        entries = await self._get_ledger_entries(account.id)
        self.assertEqual(len(entries), 2)

    async def test_sync_subscription_updates_local_snapshot(self) -> None:
        account = await self._create_account(
            email="sync@example.com",
            remnawave_user_uuid=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        )
        self._current_account_id = account.id

        self._fake_gateway.users[account.remnawave_user_uuid] = RemnawaveUser(
            uuid=account.remnawave_user_uuid,
            username=f"acc_{account.remnawave_user_uuid.hex}",
            status="EXPIRED",
            expire_at=datetime.now(UTC) - timedelta(days=1),
            subscription_url="https://panel.test/sub/existing",
            telegram_id=None,
            email=account.email,
            tag=None,
        )

        response = await self.client.post("/api/v1/subscriptions/sync")
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["status"], "EXPIRED")
        self.assertFalse(body["is_active"])
        self.assertEqual(body["subscription_url"], "https://panel.test/sub/existing")

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.subscription_status, "EXPIRED")
        self.assertIsNotNone(stored_account.subscription_last_synced_at)

    async def test_remnawave_webhook_updates_local_snapshot(self) -> None:
        account = await self._create_account(email="webhook@example.com")
        expires_at = datetime.now(UTC) + timedelta(days=10)

        payload = {
            "scope": "user",
            "event": "user.modified",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "uuid": str(account.id),
                "status": "ACTIVE",
                "expireAt": expires_at.isoformat(),
                "subscriptionUrl": "https://panel.test/sub/webhook",
                "email": account.email,
                "tag": "TRIAL",
            },
        }
        raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            settings.remnawave_webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        response = await self.client.post(
            "/api/v1/webhooks/remnawave",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Remnawave-Signature": signature,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["handled"], True)
        self.assertEqual(response.json()["processed"], True)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.remnawave_user_uuid, account.id)
        self.assertEqual(stored_account.subscription_status, "ACTIVE")
        self.assertEqual(
            stored_account.subscription_url,
            "https://panel.test/sub/webhook",
        )
        self.assertTrue(stored_account.subscription_is_trial)

        event_logs = await self._get_account_event_logs(account.id)
        self.assertEqual(
            [item.event_type for item in event_logs], ["subscription.remnawave.webhook"]
        )
        self.assertEqual(event_logs[0].source, "webhook")
        self.assertEqual(event_logs[0].payload["remnawave_event"], "user.modified")
        self.assertEqual(event_logs[0].payload["remnawave_scope"], "user")

    async def test_remnawave_webhook_ignores_stale_secondary_uuid_after_merge(
        self,
    ) -> None:
        stale_secondary_uuid = uuid.uuid4()
        canonical_remote_uuid = uuid.uuid4()
        account = await self._create_account(
            id=stale_secondary_uuid,
            email="webhook-merge@example.com",
            remnawave_user_uuid=canonical_remote_uuid,
            subscription_status="ACTIVE",
            subscription_url="https://panel.test/sub/canonical",
        )
        expires_at = datetime.now(UTC) + timedelta(days=5)

        payload = {
            "scope": "user",
            "event": "user.modified",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "uuid": str(stale_secondary_uuid),
                "status": "EXPIRED",
                "expireAt": expires_at.isoformat(),
                "subscriptionUrl": "https://panel.test/sub/stale-secondary",
                "email": account.email,
            },
        }
        raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            settings.remnawave_webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        response = await self.client.post(
            "/api/v1/webhooks/remnawave",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Remnawave-Signature": signature,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["handled"], True)
        self.assertEqual(response.json()["processed"], False)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.remnawave_user_uuid, canonical_remote_uuid)
        self.assertEqual(
            stored_account.subscription_url,
            "https://panel.test/sub/canonical",
        )
        self.assertEqual(stored_account.subscription_status, "ACTIVE")

        event_logs = await self._get_account_event_logs(account.id)
        self.assertEqual(event_logs, [])

    async def test_sync_subscription_by_remnawave_user_uuid_ignores_stale_secondary_uuid(
        self,
    ) -> None:
        stale_secondary_uuid = uuid.uuid4()
        canonical_remote_uuid = uuid.uuid4()
        account = await self._create_account(
            id=stale_secondary_uuid,
            email="sync-merge@example.com",
            remnawave_user_uuid=canonical_remote_uuid,
            subscription_status="ACTIVE",
            subscription_url="https://panel.test/sub/canonical-sync",
        )

        self._fake_gateway.users[stale_secondary_uuid] = RemnawaveUser(
            uuid=stale_secondary_uuid,
            username=f"acc_{stale_secondary_uuid.hex}",
            status="EXPIRED",
            expire_at=datetime.now(UTC) + timedelta(days=5),
            subscription_url="https://panel.test/sub/stale-sync",
            telegram_id=None,
            email=account.email,
            tag=None,
        )

        async with self._session_factory() as session:
            synced_account = (
                await subscriptions_service.sync_subscription_by_remnawave_user_uuid(
                    session,
                    remnawave_user_uuid=stale_secondary_uuid,
                )
            )

        self.assertIsNone(synced_account)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.remnawave_user_uuid, canonical_remote_uuid)
        self.assertEqual(
            stored_account.subscription_url,
            "https://panel.test/sub/canonical-sync",
        )
        self.assertEqual(stored_account.subscription_status, "ACTIVE")

    async def test_remnawave_webhook_with_null_tag_clears_trial_flag(self) -> None:
        account = await self._create_account(
            email="webhook-clear-trial@example.com",
            subscription_status="ACTIVE",
            subscription_is_trial=True,
            trial_used_at=datetime.now(UTC) - timedelta(days=2),
            trial_ends_at=datetime.now(UTC) + timedelta(days=1),
        )
        expires_at = datetime.now(UTC) + timedelta(days=30)

        payload = {
            "scope": "user",
            "event": "user.modified",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "uuid": str(account.id),
                "status": "ACTIVE",
                "expireAt": expires_at.isoformat(),
                "subscriptionUrl": "https://panel.test/sub/paid",
                "email": account.email,
                "tag": None,
            },
        }
        raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            settings.remnawave_webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        response = await self.client.post(
            "/api/v1/webhooks/remnawave",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Remnawave-Signature": signature,
            },
        )
        self.assertEqual(response.status_code, 200)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertFalse(stored_account.subscription_is_trial)

    async def test_remnawave_webhook_first_connected_records_connection_event(
        self,
    ) -> None:
        account = await self._create_account(
            email="webhook-first-connected@example.com",
            subscription_status="ACTIVE",
        )
        first_connected_at = datetime.now(UTC) - timedelta(minutes=1)
        payload = {
            "scope": "user",
            "event": "user.first_connected",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "user": {
                    "uuid": str(account.id),
                    "status": "ACTIVE",
                    "expireAt": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
                    "subscriptionUrl": "https://panel.test/sub/first-connected",
                    "userTraffic": {
                        "usedTrafficBytes": 1024,
                        "lifetimeUsedTrafficBytes": 1024,
                        "onlineAt": first_connected_at.isoformat(),
                        "firstConnectedAt": first_connected_at.isoformat(),
                    },
                }
            },
        }
        raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            settings.remnawave_webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        response = await self.client.post(
            "/api/v1/webhooks/remnawave",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Remnawave-Signature": signature,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["handled"], True)
        self.assertEqual(response.json()["processed"], True)

        event_logs = await self._get_account_event_logs(account.id)
        self.assertEqual(
            [item.event_type for item in event_logs],
            [
                "subscription.remnawave.first_connected",
                "subscription.remnawave.webhook",
            ],
        )
        self.assertEqual(
            event_logs[0].payload["first_connected_at"],
            first_connected_at.isoformat(),
        )

    async def test_remnawave_webhook_creates_subscription_expiring_notification(
        self,
    ) -> None:
        account = await self._create_account(
            email="expires-soon@example.com",
            subscription_url="https://panel.test/sub/expires-soon",
        )
        expires_at = datetime.now(UTC) + timedelta(days=1)
        payload = {
            "scope": "user",
            "event": "user.expires_in_24_hours",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "uuid": str(account.id),
                "status": "ACTIVE",
                "expireAt": expires_at.isoformat(),
                "subscriptionUrl": "https://panel.test/sub/expires-soon",
            },
        }
        raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            settings.remnawave_webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        response = await self.client.post(
            "/api/v1/webhooks/remnawave",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Remnawave-Signature": signature,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["notification_types"], ["subscription_expiring"]
        )

        notifications = await self._get_notifications(account.id)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].type, NotificationType.SUBSCRIPTION_EXPIRING)
        self.assertEqual(notifications[0].payload["days_left"], 1)
        self.assertEqual(
            notifications[0].payload["remnawave_event"], "user.expires_in_24_hours"
        )

    async def test_remnawave_webhook_creates_subscription_expired_notification(
        self,
    ) -> None:
        account = await self._create_account(
            email="expired@example.com",
            subscription_status="ACTIVE",
        )
        expires_at = datetime.now(UTC) - timedelta(minutes=5)
        payload = {
            "scope": "user",
            "event": "user.expired",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "uuid": str(account.id),
                "status": "EXPIRED",
                "expireAt": expires_at.isoformat(),
            },
        }
        raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            settings.remnawave_webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        response = await self.client.post(
            "/api/v1/webhooks/remnawave",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Remnawave-Signature": signature,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["notification_types"], ["subscription_expired"]
        )

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.subscription_status, "EXPIRED")

        notifications = await self._get_notifications(account.id)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].type, NotificationType.SUBSCRIPTION_EXPIRED)
        self.assertEqual(notifications[0].payload["remnawave_event"], "user.expired")

    async def test_remnawave_webhook_accepts_unhandled_future_scope_event(self) -> None:
        payload = {
            "scope": "system",
            "event": "system.started",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {"version": "1.0.0"},
        }
        raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            settings.remnawave_webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        response = await self.client.post(
            "/api/v1/webhooks/remnawave",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Remnawave-Signature": signature,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["handled"], False)
        self.assertEqual(response.json()["processed"], False)

    async def test_remnawave_webhook_rejects_invalid_signature(self) -> None:
        account = await self._create_account(email="invalid-signature@example.com")

        response = await self.client.post(
            "/api/v1/webhooks/remnawave",
            json={"event": "user.modified", "data": str(account.id)},
            headers={"X-Remnawave-Signature": "invalid"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "invalid Remnawave signature")


if __name__ == "__main__":
    unittest.main()
