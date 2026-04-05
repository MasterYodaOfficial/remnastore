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
    AccountEventLog,
    AccountStatus,
    LedgerEntry,
    Notification,
    NotificationType,
    ReferralReward,
    SubscriptionGrant,
    TelegramReferralIntent,
)
from app.db.session import get_session
from app.main import create_app
from app.services.i18n import translate
from app.services.plans import get_subscription_plan
from app.services import referrals as referrals_service

PLAN_1M = get_subscription_plan("plan_1m")
PLAN_1M_PRICE_RUB = PLAN_1M.price_rub


def _referral_reward_for_amount(amount: int, *, rate: Decimal | float) -> int:
    return referrals_service.calculate_referral_reward_amount(
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

        self._original_default_referral_reward_rate = (
            settings.default_referral_reward_rate
        )
        self._original_api_token = settings.api_token
        settings.default_referral_reward_rate = 20.0
        settings.api_token = "test-api-token"

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
        settings.default_referral_reward_rate = (
            self._original_default_referral_reward_rate
        )
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

    async def _get_referral_rewards(
        self, referrer_account_id: uuid.UUID
    ) -> list[ReferralReward]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ReferralReward).where(
                    ReferralReward.referrer_account_id == referrer_account_id
                )
            )
            return list(result.scalars().all())

    async def _get_ledger_entries(self, account_id: uuid.UUID) -> list[LedgerEntry]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(LedgerEntry)
                .where(LedgerEntry.account_id == account_id)
                .order_by(LedgerEntry.id.asc())
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

    async def _get_telegram_referral_intent(
        self, telegram_id: int
    ) -> TelegramReferralIntent | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TelegramReferralIntent).where(
                    TelegramReferralIntent.telegram_id == telegram_id
                )
            )
            return result.scalar_one_or_none()

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

    async def _create_subscription_grant(
        self,
        *,
        account_id: uuid.UUID,
        plan_code: str = "plan_1m",
        amount: int = PLAN_1M_PRICE_RUB,
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
        self.assertEqual(
            first_response.json()["referred_by_account_id"], str(referrer.id)
        )

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

        referred_event_types = [
            item.event_type for item in await self._get_account_event_logs(referred.id)
        ]
        referrer_event_types = [
            item.event_type for item in await self._get_account_event_logs(referrer.id)
        ]
        self.assertIn("referral.claim", referred_event_types)
        self.assertIn("referral.attributed", referrer_event_types)

    async def test_claim_referral_code_rejects_self_referral(self) -> None:
        account = await self._create_account(referral_code="ref-self")
        self._current_account_id = account.id

        response = await self.client.post(
            "/api/v1/referrals/claim",
            json={"referral_code": "ref-self"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            translate("api.referrals.errors.self_referral"),
        )
        self.assertEqual(response.json()["error_code"], "self_referral")

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
            translate("api.referrals.errors.window_closed"),
        )
        self.assertEqual(response.json()["error_code"], "window_closed")

        stored_referrer = await self._get_account(referrer.id)
        self.assertIsNotNone(stored_referrer)
        assert stored_referrer is not None
        self.assertEqual(stored_referrer.referrals_count, 0)

    async def test_claim_referral_code_allows_admin_grant_before_first_paid_purchase(
        self,
    ) -> None:
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
                amount=PLAN_1M_PRICE_RUB,
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
        expected_reward = _referral_reward_for_amount(
            PLAN_1M_PRICE_RUB,
            rate=settings.default_referral_reward_rate,
        )
        self.assertEqual(body["referral_earnings"], expected_reward)
        self.assertEqual(body["available_for_withdraw"], expected_reward)
        self.assertEqual(body["effective_reward_rate"], 20.0)

        rewards = await self._get_referral_rewards(referrer.id)
        self.assertEqual(len(rewards), 1)
        entries = await self._get_ledger_entries(referrer.id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].amount, expected_reward)

        event_types = [
            item.event_type for item in await self._get_account_event_logs(referrer.id)
        ]
        self.assertIn("referral.reward.granted", event_types)

        feed_response = await self.client.get("/api/v1/referrals/feed")
        self.assertEqual(feed_response.status_code, 200)
        feed_body = feed_response.json()
        self.assertEqual(feed_body["total"], 1)
        self.assertEqual(feed_body["limit"], 20)
        self.assertEqual(feed_body["offset"], 0)
        self.assertEqual(feed_body["status_filter"], "all")
        self.assertEqual(len(feed_body["items"]), 1)
        self.assertEqual(feed_body["items"][0]["referred_account_id"], str(referred.id))
        self.assertEqual(feed_body["items"][0]["reward_amount"], expected_reward)
        self.assertEqual(feed_body["items"][0]["status"], "active")

    async def test_feed_supports_pagination_and_status_filters(self) -> None:
        referrer = await self._create_account(referral_code="ref-feed")
        pending_referred = await self._create_account(display_name="Pending Referral")
        active_referred_older = await self._create_account(
            display_name="Older Paid Referral"
        )
        active_referred_newer = await self._create_account(
            display_name="Newer Paid Referral"
        )

        async with self._session_factory() as session:
            pending_claim = await referrals_service.claim_referral_code(
                session,
                account_id=pending_referred.id,
                referral_code="ref-feed",
            )
            older_claim = await referrals_service.claim_referral_code(
                session,
                account_id=active_referred_older.id,
                referral_code="ref-feed",
            )
            newer_claim = await referrals_service.claim_referral_code(
                session,
                account_id=active_referred_newer.id,
                referral_code="ref-feed",
            )

            older_grant = SubscriptionGrant(
                account_id=active_referred_older.id,
                payment_id=None,
                purchase_source="wallet",
                reference_type="wallet_purchase",
                reference_id="feed-grant-older",
                plan_code="plan_1m",
                amount=PLAN_1M_PRICE_RUB,
                currency="RUB",
                duration_days=30,
                base_expires_at=datetime.now(UTC),
                target_expires_at=datetime.now(UTC) + timedelta(days=30),
                applied_at=datetime.now(UTC),
            )
            newer_grant = SubscriptionGrant(
                account_id=active_referred_newer.id,
                payment_id=None,
                purchase_source="wallet",
                reference_type="wallet_purchase",
                reference_id="feed-grant-newer",
                plan_code="plan_1m",
                amount=PLAN_1M_PRICE_RUB,
                currency="RUB",
                duration_days=30,
                base_expires_at=datetime.now(UTC),
                target_expires_at=datetime.now(UTC) + timedelta(days=30),
                applied_at=datetime.now(UTC),
            )
            session.add_all([older_grant, newer_grant])
            await session.flush()

            older_reward = (
                await referrals_service.apply_first_referral_reward_for_grant(
                    session,
                    grant=older_grant,
                )
            )
            newer_reward = (
                await referrals_service.apply_first_referral_reward_for_grant(
                    session,
                    grant=newer_grant,
                )
            )

            pending_claim.attribution.created_at = datetime(
                2026, 4, 1, 12, 0, tzinfo=UTC
            )
            older_claim.attribution.created_at = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
            newer_claim.attribution.created_at = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
            assert older_reward is not None
            assert newer_reward is not None
            older_reward.created_at = datetime(2026, 4, 4, 12, 0, tzinfo=UTC)
            newer_reward.created_at = datetime(2026, 4, 5, 12, 0, tzinfo=UTC)
            await session.commit()

        self._current_account_id = referrer.id

        page_one = await self.client.get("/api/v1/referrals/feed?limit=2&offset=0")
        self.assertEqual(page_one.status_code, 200)
        page_one_body = page_one.json()
        self.assertEqual(page_one_body["total"], 3)
        self.assertEqual(page_one_body["limit"], 2)
        self.assertEqual(page_one_body["offset"], 0)
        self.assertEqual(
            [item["referred_account_id"] for item in page_one_body["items"]],
            [str(active_referred_newer.id), str(active_referred_older.id)],
        )

        page_two = await self.client.get("/api/v1/referrals/feed?limit=2&offset=2")
        self.assertEqual(page_two.status_code, 200)
        page_two_body = page_two.json()
        self.assertEqual(page_two_body["total"], 3)
        self.assertEqual(
            [item["referred_account_id"] for item in page_two_body["items"]],
            [str(pending_referred.id)],
        )

        active_only = await self.client.get("/api/v1/referrals/feed?status=active")
        self.assertEqual(active_only.status_code, 200)
        active_only_body = active_only.json()
        self.assertEqual(active_only_body["status_filter"], "active")
        self.assertEqual(active_only_body["total"], 2)
        self.assertEqual(
            [item["referred_account_id"] for item in active_only_body["items"]],
            [str(active_referred_newer.id), str(active_referred_older.id)],
        )
        self.assertTrue(
            all(item["status"] == "active" for item in active_only_body["items"])
        )

        pending_only = await self.client.get("/api/v1/referrals/feed?status=pending")
        self.assertEqual(pending_only.status_code, 200)
        pending_only_body = pending_only.json()
        self.assertEqual(pending_only_body["status_filter"], "pending")
        self.assertEqual(pending_only_body["total"], 1)
        self.assertEqual(
            [item["referred_account_id"] for item in pending_only_body["items"]],
            [str(pending_referred.id)],
        )
        self.assertTrue(
            all(item["status"] == "pending" for item in pending_only_body["items"])
        )

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

    async def test_telegram_auth_rejects_fully_blocked_account(self) -> None:
        await self._create_account(
            telegram_id=700003,
            status=AccountStatus.BLOCKED,
            username="blocked-telegram-user",
        )

        with patch.object(
            auth_endpoints,
            "verify_telegram_init_data",
            return_value={
                "user": {
                    "id": 700003,
                    "username": "blocked-telegram-user",
                    "first_name": "Blocked",
                    "last_name": "User",
                    "is_premium": False,
                    "language_code": "ru",
                }
            },
        ):
            response = await self.client.post(
                "/api/v1/auth/telegram/webapp",
                json={"init_data": "stub"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            translate("api.accounts.errors.account_blocked"),
        )
        self.assertEqual(response.json()["error_code"], "account_blocked")

    async def test_internal_telegram_access_reports_full_block(self) -> None:
        await self._create_account(
            telegram_id=700004,
            status=AccountStatus.BLOCKED,
        )

        response = await self.client.get(
            "/api/v1/internal/telegram-accounts/700004/access",
            headers={"Authorization": f"Bearer {settings.api_token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "telegram_id": 700004,
                "exists": True,
                "status": "blocked",
                "fully_blocked": True,
                "telegram_bot_blocked": False,
            },
        )

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
                amount=PLAN_1M_PRICE_RUB,
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
                amount=PLAN_1M_PRICE_RUB,
                currency="RUB",
                duration_days=30,
                base_expires_at=datetime.now(UTC),
                target_expires_at=datetime.now(UTC) + timedelta(days=60),
                applied_at=datetime.now(UTC),
            )
            session.add(first_grant)
            session.add(second_grant)
            await session.flush()

            first_reward = (
                await referrals_service.apply_first_referral_reward_for_grant(
                    session,
                    grant=first_grant,
                )
            )
            second_reward = (
                await referrals_service.apply_first_referral_reward_for_grant(
                    session,
                    grant=second_grant,
                )
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
        self.assertEqual(
            stored_referrer.referral_earnings,
            _referral_reward_for_amount(
                PLAN_1M_PRICE_RUB,
                rate=Decimal("33.00"),
            ),
        )

        notifications = await self._get_notifications(referrer.id)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(
            notifications[0].type, NotificationType.REFERRAL_REWARD_RECEIVED
        )


if __name__ == "__main__":
    unittest.main()
