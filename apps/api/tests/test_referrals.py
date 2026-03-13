from datetime import UTC, datetime, timedelta
from decimal import Decimal
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_account
from app.api.v1.endpoints import auth as auth_endpoints
from app.core.config import settings
from app.db.base import Base
from app.db.models import (
    Account,
    LedgerEntry,
    Notification,
    NotificationType,
    ReferralAttribution,
    ReferralReward,
    SubscriptionGrant,
    TelegramReferralIntent,
)
from app.db.session import get_session
from app.main import create_app
from app.services import referrals as referrals_service


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


class ReferralFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "referrals.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._current_account_id: uuid.UUID | None = None

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()

        self._original_default_referral_reward_rate = settings.default_referral_reward_rate
        self._original_api_token = settings.api_token
        settings.default_referral_reward_rate = 20.0
        settings.api_token = "test-api-token"

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
        settings.default_referral_reward_rate = self._original_default_referral_reward_rate
        settings.api_token = self._original_api_token
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

    async def _get_referral_rewards(self, referrer_account_id: uuid.UUID) -> list[ReferralReward]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ReferralReward).where(ReferralReward.referrer_account_id == referrer_account_id)
            )
            return list(result.scalars().all())

    async def _get_ledger_entries(self, account_id: uuid.UUID) -> list[LedgerEntry]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(LedgerEntry).where(LedgerEntry.account_id == account_id).order_by(LedgerEntry.id.asc())
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

    async def _get_account_by_telegram_id(self, telegram_id: int) -> Account | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Account).where(Account.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()

    async def _get_telegram_referral_intent(self, telegram_id: int) -> TelegramReferralIntent | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TelegramReferralIntent).where(TelegramReferralIntent.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()

    async def _create_subscription_grant(
        self,
        *,
        account_id: uuid.UUID,
        plan_code: str = "plan_1m",
        amount: int = 299,
        purchase_source: str = "wallet",
        reference_type: str = "wallet_purchase",
    ) -> SubscriptionGrant:
        async with self._session_factory() as session:
            now = datetime.now(UTC)
            grant = SubscriptionGrant(
                account_id=account_id,
                payment_id=None,
                purchase_source=purchase_source,
                reference_type=reference_type,
                reference_id=f"test-{uuid.uuid4().hex}",
                plan_code=plan_code,
                amount=amount,
                currency="RUB",
                duration_days=30,
                base_expires_at=now,
                target_expires_at=now + timedelta(days=30),
                applied_at=now,
            )
            session.add(grant)
            await session.commit()
            await session.refresh(grant)
            return grant

    async def test_claim_referral_code_is_idempotent_for_same_referrer(self) -> None:
        referrer = await self._create_account(referral_code="ref-owner")
        referred = await self._create_account(referral_code="ref-user")
        self._current_account_id = referred.id

        first_response = await self.client.post(
            "/api/v1/referrals/claim",
            json={"referral_code": "ref-owner"},
        )
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json()["created"], True)
        self.assertEqual(first_response.json()["referred_by_account_id"], str(referrer.id))

        second_response = await self.client.post(
            "/api/v1/referrals/claim",
            json={"referral_code": "ref-owner"},
        )
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["created"], False)

        stored_referred = await self._get_account(referred.id)
        self.assertIsNotNone(stored_referred)
        assert stored_referred is not None
        self.assertEqual(stored_referred.referred_by_account_id, referrer.id)

        stored_referrer = await self._get_account(referrer.id)
        self.assertIsNotNone(stored_referrer)
        assert stored_referrer is not None
        self.assertEqual(stored_referrer.referrals_count, 1)

    async def test_claim_referral_code_rejects_self_referral(self) -> None:
        account = await self._create_account(referral_code="ref-self")
        self._current_account_id = account.id

        response = await self.client.post(
            "/api/v1/referrals/claim",
            json={"referral_code": "ref-self"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "self referral is not allowed")

    async def test_claim_referral_code_rejects_after_first_paid_purchase(self) -> None:
        referrer = await self._create_account(referral_code="ref-late")
        referred = await self._create_account(referral_code="ref-buyer")
        await self._create_subscription_grant(account_id=referred.id)
        self._current_account_id = referred.id

        response = await self.client.post(
            "/api/v1/referrals/claim",
            json={"referral_code": "ref-late"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            "referral attribution is closed after the first paid purchase",
        )

        stored_referrer = await self._get_account(referrer.id)
        self.assertIsNotNone(stored_referrer)
        assert stored_referrer is not None
        self.assertEqual(stored_referrer.referrals_count, 0)

    async def test_claim_referral_code_allows_admin_grant_before_first_paid_purchase(self) -> None:
        referrer = await self._create_account(referral_code="ref-admin")
        referred = await self._create_account(referral_code="ref-manual")
        await self._create_subscription_grant(
            account_id=referred.id,
            amount=0,
            purchase_source="admin",
            reference_type="admin_manual_grant",
        )
        self._current_account_id = referred.id

        response = await self.client.post(
            "/api/v1/referrals/claim",
            json={"referral_code": "ref-admin"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], True)
        self.assertEqual(response.json()["referred_by_account_id"], str(referrer.id))

    async def test_summary_returns_real_referrals_and_rewards(self) -> None:
        referrer = await self._create_account(referral_code="ref-summary")
        referred = await self._create_account(referral_code="ref-new")

        async with self._session_factory() as session:
            claim_result = await referrals_service.claim_referral_code(
                session,
                account_id=referred.id,
                referral_code="ref-summary",
            )
            grant = SubscriptionGrant(
                account_id=referred.id,
                payment_id=None,
                purchase_source="wallet",
                reference_type="wallet_purchase",
                reference_id="summary-grant",
                plan_code="plan_1m",
                amount=299,
                currency="RUB",
                duration_days=30,
                base_expires_at=datetime.now(UTC),
                target_expires_at=datetime.now(UTC) + timedelta(days=30),
                applied_at=datetime.now(UTC),
            )
            session.add(grant)
            await session.flush()
            reward = await referrals_service.apply_first_referral_reward_for_grant(
                session,
                grant=grant,
            )
            await session.commit()

        self.assertIsNotNone(claim_result.attribution.id)
        self.assertIsNotNone(reward)

        self._current_account_id = referrer.id
        response = await self.client.get("/api/v1/referrals/summary")
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["referral_code"], "ref-summary")
        self.assertEqual(body["referrals_count"], 1)
        self.assertEqual(body["referral_earnings"], 59)
        self.assertEqual(body["available_for_withdraw"], 59)
        self.assertEqual(body["effective_reward_rate"], 20.0)
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["referred_account_id"], str(referred.id))
        self.assertEqual(body["items"][0]["reward_amount"], 59)
        self.assertEqual(body["items"][0]["status"], "active")

        rewards = await self._get_referral_rewards(referrer.id)
        self.assertEqual(len(rewards), 1)
        entries = await self._get_ledger_entries(referrer.id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].amount, 59)

    async def test_bot_webhook_records_pending_telegram_referral_intent(self) -> None:
        await self._create_account(referral_code="ref-bot")

        response = await self.client.post(
            "/api/v1/webhooks/referrals/telegram-start",
            json={"telegram_id": 700001, "referral_code": "ref-bot"},
            headers={"Authorization": f"Bearer {settings.api_token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ok"], True)

        intent = await self._get_telegram_referral_intent(700001)
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.referral_code, "ref-bot")
        self.assertEqual(intent.status, "pending")
        self.assertIsNone(intent.account_id)
        self.assertIsNone(intent.consumed_at)

    async def test_telegram_auth_applies_pending_referral_intent(self) -> None:
        referrer = await self._create_account(referral_code="ref-auth")

        webhook_response = await self.client.post(
            "/api/v1/webhooks/referrals/telegram-start",
            json={"telegram_id": 700002, "referral_code": "ref-auth"},
            headers={"Authorization": f"Bearer {settings.api_token}"},
        )
        self.assertEqual(webhook_response.status_code, 200)

        with patch.object(
            auth_endpoints,
            "verify_telegram_init_data",
            return_value={
                "user": {
                    "id": 700002,
                    "username": "new-ref-user",
                    "first_name": "Referral",
                    "last_name": "User",
                    "is_premium": False,
                    "language_code": "ru",
                }
            },
        ):
            auth_response = await self.client.post(
                "/api/v1/auth/telegram/webapp",
                json={"init_data": "stub"},
            )

        self.assertEqual(auth_response.status_code, 200)
        body = auth_response.json()
        self.assertIsNotNone(body["referral_result"])
        self.assertEqual(body["referral_result"]["created"], True)
        self.assertEqual(body["referral_result"]["applied"], True)

        referred_account = await self._get_account_by_telegram_id(700002)
        self.assertIsNotNone(referred_account)
        assert referred_account is not None
        self.assertEqual(referred_account.referred_by_account_id, referrer.id)

        intent = await self._get_telegram_referral_intent(700002)
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.status, "applied")
        self.assertEqual(intent.account_id, referred_account.id)
        self.assertIsNotNone(intent.consumed_at)

    async def test_reward_uses_partner_override_and_only_once(self) -> None:
        referrer = await self._create_account(
            referral_code="ref-partner",
            referral_reward_rate=Decimal("33.00"),
        )
        referred = await self._create_account(referral_code="ref-customer")

        async with self._session_factory() as session:
            await referrals_service.claim_referral_code(
                session,
                account_id=referred.id,
                referral_code="ref-partner",
            )
            first_grant = SubscriptionGrant(
                account_id=referred.id,
                payment_id=None,
                purchase_source="wallet",
                reference_type="wallet_purchase",
                reference_id="override-1",
                plan_code="plan_1m",
                amount=299,
                currency="RUB",
                duration_days=30,
                base_expires_at=datetime.now(UTC),
                target_expires_at=datetime.now(UTC) + timedelta(days=30),
                applied_at=datetime.now(UTC),
            )
            second_grant = SubscriptionGrant(
                account_id=referred.id,
                payment_id=None,
                purchase_source="wallet",
                reference_type="wallet_purchase",
                reference_id="override-2",
                plan_code="plan_1m",
                amount=299,
                currency="RUB",
                duration_days=30,
                base_expires_at=datetime.now(UTC),
                target_expires_at=datetime.now(UTC) + timedelta(days=60),
                applied_at=datetime.now(UTC),
            )
            session.add(first_grant)
            session.add(second_grant)
            await session.flush()

            first_reward = await referrals_service.apply_first_referral_reward_for_grant(
                session,
                grant=first_grant,
            )
            second_reward = await referrals_service.apply_first_referral_reward_for_grant(
                session,
                grant=second_grant,
            )
            await session.commit()

        self.assertIsNotNone(first_reward)
        self.assertIsNotNone(second_reward)
        assert first_reward is not None
        assert second_reward is not None
        self.assertEqual(first_reward.id, second_reward.id)

        stored_referrer = await self._get_account(referrer.id)
        self.assertIsNotNone(stored_referrer)
        assert stored_referrer is not None
        self.assertEqual(stored_referrer.referral_earnings, 98)

        notifications = await self._get_notifications(referrer.id)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].type, NotificationType.REFERRAL_REWARD_RECEIVED)


if __name__ == "__main__":
    unittest.main()
