from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_account
from app.db.base import Base
from app.db.models import (
    Account,
    LedgerEntry,
    LedgerEntryType,
    Payment,
    PromoCampaign,
    PromoCampaignStatus,
    PromoCode,
    PromoEffectType,
    PromoRedemption,
    PromoRedemptionStatus,
    SubscriptionGrant,
)
from app.db.session import get_session
from app.domain.payments import (
    CreatePaymentIntentCommand,
    PaymentFlowType,
    PaymentIntentSnapshot,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookEvent,
)
from app.integrations.remnawave.client import RemnawaveUser
from app.main import create_app
from app.services.plans import get_subscription_plan

PLAN_1M = get_subscription_plan("plan_1m")
PLAN_1M_PRICE_RUB = PLAN_1M.price_rub
PLAN_1M_DURATION_DAYS = PLAN_1M.duration_days


class DummyCache:
    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def account_response_key(self, account_id: str) -> str:
        return f"account:{account_id}"

    async def delete(self, *keys: str) -> None:
        return None


@dataclass
class FakeRemnawaveGateway:
    users: dict[uuid.UUID, RemnawaveUser]

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


class FakeYooKassaGateway:
    provider = PaymentProvider.YOOKASSA

    def __init__(self) -> None:
        self._events: dict[str, PaymentWebhookEvent] = {}
        self.created_commands: list[CreatePaymentIntentCommand] = []

    async def create_payment_intent(self, command: CreatePaymentIntentCommand):
        self.created_commands.append(command)
        return PaymentIntentSnapshot(
            provider=PaymentProvider.YOOKASSA,
            flow_type=command.flow_type,
            account_id=command.account_id,
            status=PaymentStatus.PENDING,
            amount=command.amount,
            currency=command.currency,
            provider_payment_id=f"yoopay-{command.idempotency_key or 'generated'}",
            external_reference=command.idempotency_key,
            confirmation_url="https://yookassa.test/confirm",
            expires_at=None,
            raw_payload={
                "provider_payment_id": f"yoopay-{command.idempotency_key or 'generated'}"
            },
        )

    async def parse_webhook(self, *, raw_body: bytes, headers):
        del headers
        payload = json.loads(raw_body)
        return self._events[payload["event_id"]]

    def put_event(self, event_id: str, event: PaymentWebhookEvent) -> None:
        self._events[event_id] = event


class PromoFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "promos.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._current_account_id: uuid.UUID | None = None
        self._fake_gateway = FakeYooKassaGateway()
        self._fake_remnawave_gateway = FakeRemnawaveGateway(users={})

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module
        import app.services.payments as payments_service
        import app.services.subscriptions as subscriptions_service

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()

        self._payments_service = payments_service
        self._original_yookassa_gateway = payments_service.get_yookassa_gateway
        self._original_api_token = payments_service.settings.api_token
        payments_service.get_yookassa_gateway = lambda: self._fake_gateway
        payments_service.settings.api_token = "internal-token"

        self._subscriptions_service = subscriptions_service
        self._original_subscription_gateway = (
            subscriptions_service.get_remnawave_gateway
        )
        subscriptions_service.get_remnawave_gateway = lambda: (
            self._fake_remnawave_gateway
        )

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

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        self._cache_module._cache = self._original_cache
        self._payments_service.get_yookassa_gateway = self._original_yookassa_gateway
        self._payments_service.settings.api_token = self._original_api_token
        self._subscriptions_service.get_remnawave_gateway = (
            self._original_subscription_gateway
        )
        await self._engine.dispose()
        self._tmpdir.cleanup()

    async def _create_account(self, **values) -> Account:
        async with self._session_factory() as session:
            account = Account(**values)
            session.add(account)
            await session.commit()
            await session.refresh(account)
            return account

    async def _create_promo(
        self,
        *,
        code: str,
        effect_type: PromoEffectType,
        effect_value: int,
        plan_codes: list[str] | None = None,
    ) -> tuple[PromoCampaign, PromoCode]:
        async with self._session_factory() as session:
            campaign = PromoCampaign(
                name=f"Promo {code}",
                status=PromoCampaignStatus.ACTIVE,
                effect_type=effect_type,
                effect_value=effect_value,
                currency="RUB",
                plan_codes=plan_codes,
            )
            session.add(campaign)
            await session.flush()
            promo_code = PromoCode(
                campaign_id=campaign.id,
                code=code,
                is_active=True,
            )
            session.add(promo_code)
            await session.commit()
            await session.refresh(campaign)
            await session.refresh(promo_code)
            return campaign, promo_code

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

    async def _get_promo_redemptions(
        self, account_id: uuid.UUID
    ) -> list[PromoRedemption]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PromoRedemption)
                .where(PromoRedemption.account_id == account_id)
                .order_by(PromoRedemption.id.asc())
            )
            return list(result.scalars().all())

    async def _get_payment(self, provider_payment_id: str) -> Payment | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Payment).where(
                    Payment.provider_payment_id == provider_payment_id
                )
            )
            return result.scalar_one_or_none()

    async def test_quote_plan_promo_returns_discounted_amount(self) -> None:
        account = await self._create_account(email="quote@example.com")
        self._current_account_id = account.id
        await self._create_promo(
            code="SPRING20",
            effect_type=PromoEffectType.PERCENT_DISCOUNT,
            effect_value=20,
            plan_codes=["plan_1m"],
        )

        response = await self.client.post(
            "/api/v1/promos/plans/plan_1m/quote",
            json={"promo_code": "spring20", "currency": "rub"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "plan_code": "plan_1m",
                "promo_code": "SPRING20",
                "effect_type": "percent_discount",
                "original_amount": PLAN_1M_PRICE_RUB,
                "final_amount": PLAN_1M_PRICE_RUB - ((PLAN_1M_PRICE_RUB * 20) // 100),
                "discount_amount": (PLAN_1M_PRICE_RUB * 20) // 100,
                "currency": "RUB",
                "original_duration_days": PLAN_1M_DURATION_DAYS,
                "final_duration_days": PLAN_1M_DURATION_DAYS,
            },
        )

    async def test_redeem_balance_credit_is_idempotent(self) -> None:
        account = await self._create_account(email="balance@example.com", balance=0)
        self._current_account_id = account.id
        await self._create_promo(
            code="BONUS300",
            effect_type=PromoEffectType.BALANCE_CREDIT,
            effect_value=300,
        )

        first_response = await self.client.post(
            "/api/v1/promos/redeem",
            json={"code": "bonus300", "idempotency_key": "bonus-1"},
        )
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json()["balance"], 300)
        self.assertEqual(first_response.json()["balance_credit_amount"], 300)
        self.assertEqual(first_response.json()["status"], "applied")

        second_response = await self.client.post(
            "/api/v1/promos/redeem",
            json={"code": "bonus300", "idempotency_key": "bonus-1"},
        )
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["balance"], 300)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.balance, 300)

        ledger_entries = await self._get_ledger_entries(account.id)
        self.assertEqual(len(ledger_entries), 1)
        self.assertEqual(ledger_entries[0].entry_type, LedgerEntryType.PROMO_CREDIT)
        self.assertEqual(ledger_entries[0].amount, 300)

        redemptions = await self._get_promo_redemptions(account.id)
        self.assertEqual(len(redemptions), 1)
        self.assertEqual(redemptions[0].status, PromoRedemptionStatus.APPLIED)
        self.assertEqual(redemptions[0].ledger_entry_id, ledger_entries[0].id)

    async def test_wallet_plan_purchase_with_discounted_promo_tracks_redemption(
        self,
    ) -> None:
        account = await self._create_account(email="wallet@example.com", balance=1000)
        self._current_account_id = account.id
        await self._create_promo(
            code="HALF",
            effect_type=PromoEffectType.PERCENT_DISCOUNT,
            effect_value=50,
            plan_codes=["plan_1m"],
        )

        first_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-half", "promo_code": "half"},
        )
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json()["status"], "ACTIVE")

        second_response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "wallet-half", "promo_code": "half"},
        )
        self.assertEqual(second_response.status_code, 200)

        stored_account = await self._get_account(account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        discounted_amount = PLAN_1M_PRICE_RUB - ((PLAN_1M_PRICE_RUB * 50) // 100)
        self.assertEqual(stored_account.balance, 1000 - discounted_amount)
        self.assertEqual(stored_account.subscription_status, "ACTIVE")

        ledger_entries = await self._get_ledger_entries(account.id)
        self.assertEqual(len(ledger_entries), 1)
        self.assertEqual(
            ledger_entries[0].entry_type, LedgerEntryType.SUBSCRIPTION_DEBIT
        )
        self.assertEqual(ledger_entries[0].amount, -discounted_amount)

        grants = await self._get_subscription_grants(account.id)
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0].amount, discounted_amount)
        self.assertEqual(grants[0].duration_days, PLAN_1M_DURATION_DAYS)
        self.assertIsNotNone(grants[0].applied_at)

        redemptions = await self._get_promo_redemptions(account.id)
        self.assertEqual(len(redemptions), 1)
        self.assertEqual(redemptions[0].status, PromoRedemptionStatus.APPLIED)
        self.assertEqual(
            redemptions[0].discount_amount,
            (PLAN_1M_PRICE_RUB * 50) // 100,
        )
        self.assertEqual(redemptions[0].final_amount, discounted_amount)
        self.assertEqual(redemptions[0].subscription_grant_id, grants[0].id)

    async def test_direct_plan_payment_with_extra_days_applies_extended_grant(
        self,
    ) -> None:
        account = await self._create_account(email="payment@example.com", balance=0)
        self._current_account_id = account.id
        await self._create_promo(
            code="PLUS7",
            effect_type=PromoEffectType.EXTRA_DAYS,
            effect_value=7,
            plan_codes=["plan_1m"],
        )

        create_response = await self.client.post(
            "/api/v1/payments/yookassa/plans/plan_1m",
            json={
                "success_url": "https://app.example.com/payments/return",
                "idempotency_key": "plan-plus7",
                "promo_code": "plus7",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_response.json()["amount"], PLAN_1M_PRICE_RUB)

        stored_payment = await self._get_payment("yoopay-plan-plus7")
        self.assertIsNotNone(stored_payment)
        assert stored_payment is not None
        self.assertEqual(stored_payment.amount, PLAN_1M_PRICE_RUB)
        self.assertEqual(stored_payment.request_metadata["rm_plan_duration_days"], "37")
        self.assertEqual(stored_payment.request_metadata["rm_promo_code"], "PLUS7")

        redemptions = await self._get_promo_redemptions(account.id)
        self.assertEqual(len(redemptions), 1)
        self.assertEqual(redemptions[0].status, PromoRedemptionStatus.PENDING)
        self.assertEqual(redemptions[0].granted_duration_days, 37)

        self._fake_gateway.put_event(
            "plan-event-plus7",
            PaymentWebhookEvent(
                provider=PaymentProvider.YOOKASSA,
                provider_event_id="payment.succeeded:yoopay-plan-plus7",
                provider_payment_id="yoopay-plan-plus7",
                status=PaymentStatus.SUCCEEDED,
                amount=PLAN_1M_PRICE_RUB,
                currency="RUB",
                flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                account_id=account.id,
                external_reference="plan-plus7",
                raw_payload={"status": "succeeded"},
            ),
        )

        async def fake_apply_paid_purchase(
            account_obj: Account,
            *,
            source,
            target_expires_at: datetime,
        ):
            self.assertEqual(source.value, "direct_payment")
            account_obj.remnawave_user_uuid = account_obj.id
            account_obj.subscription_status = "ACTIVE"
            account_obj.subscription_expires_at = target_expires_at
            account_obj.subscription_url = (
                f"https://panel.test/sub/{account_obj.id.hex[:8]}"
            )
            account_obj.subscription_is_trial = False
            return SimpleNamespace(uuid=account_obj.id, expire_at=target_expires_at)

        with patch(
            "app.services.payments.apply_paid_purchase",
            side_effect=fake_apply_paid_purchase,
        ):
            webhook_response = await self.client.post(
                "/api/v1/webhooks/payments/yookassa",
                content=json.dumps({"event_id": "plan-event-plus7"}),
                headers={"content-type": "application/json"},
            )

        self.assertEqual(webhook_response.status_code, 200)
        self.assertTrue(webhook_response.json()["subscription_applied"])

        grants = await self._get_subscription_grants(account.id)
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0].duration_days, 37)
        self.assertIsNotNone(grants[0].applied_at)

        redemptions = await self._get_promo_redemptions(account.id)
        self.assertEqual(len(redemptions), 1)
        self.assertEqual(redemptions[0].status, PromoRedemptionStatus.APPLIED)
        self.assertEqual(redemptions[0].payment_id, stored_payment.id)
        self.assertEqual(redemptions[0].subscription_grant_id, grants[0].id)
