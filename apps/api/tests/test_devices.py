import tempfile
import json
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
import httpx
from remnawave import RemnawaveSDK
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plan_fixtures import seed_subscription_plans
from app.api.dependencies import get_current_account
from app.db.base import Base
from app.db.models import (
    Account,
    AccountDeviceSettings,
    DevicePrepayment,
    DevicePurchase,
    LedgerEntry,
    SubscriptionGrant,
    SubscriptionPlanRecord,
)
from app.db.session import get_session
from app.integrations.remnawave import RemnawaveRequestError, RemnawaveUser
from app.integrations.remnawave.client import RemnawaveGateway
from app.main import create_app
from app.services.devices import reconcile_device_purchases
from test_payments import FakeYooKassaGateway
from app.domain.payments import (
    PaymentWebhookEvent,
    PaymentProvider,
    PaymentFlowType,
    PaymentStatus,
)


class FakeDeviceGateway:
    def __init__(self, user):
        self.user = user
        self.devices = [{"hwid": "phone", "platform": "iOS", "device_model": "iPhone"}]
        self.limit_calls = []
        self.fail_updates = False

    async def get_user_by_uuid(self, user_uuid):
        return self.user if user_uuid == self.user.uuid else None

    async def get_hwid_devices(self, user_uuid):
        return list(self.devices) if user_uuid == self.user.uuid else []

    async def delete_hwid_device(self, user_uuid, hwid):
        self.devices = [device for device in self.devices if device["hwid"] != hwid]

    async def reset_hwid_devices(self, user_uuid):
        self.devices = []

    async def set_hwid_device_limit(self, user_uuid, limit):
        if self.fail_updates:
            raise RemnawaveRequestError("offline")
        self.limit_calls.append(limit)
        self.user.hwid_device_limit = limit

    async def provision_user(self, **kwargs):
        self.user.expire_at = kwargs["expire_at"]
        return self.user


class DeviceEndpointsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(self.tmp.name) / 'devices.db'}"
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.now = datetime.now(UTC).replace(microsecond=0)
        self.expires_at = self.now + timedelta(days=90)
        self.account_id = uuid.uuid4()
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await seed_subscription_plans(connection)
        async with self.sessions() as session:
            plan = await session.get(SubscriptionPlanRecord, "plan_3m")
            plan.extra_device_price_rub = 135
            plan = await session.get(SubscriptionPlanRecord, "plan_1m")
            plan.extra_device_price_rub = 50
            session.add(
                Account(
                    id=self.account_id,
                    balance=2000,
                    subscription_status="ACTIVE",
                    remnawave_user_uuid=self.account_id,
                    subscription_expires_at=self.expires_at,
                    subscription_is_trial=False,
                    subscription_url="https://panel.test/sub",
                )
            )
            await session.flush()
            session.add(
                SubscriptionGrant(
                    account_id=self.account_id,
                    purchase_source="wallet",
                    reference_type="test",
                    reference_id=str(self.account_id),
                    plan_code="plan_3m",
                    amount=560,
                    currency="RUB",
                    duration_days=90,
                    base_expires_at=self.now,
                    target_expires_at=self.expires_at,
                    applied_at=self.now,
                )
            )
            await session.commit()
        self.gateway = FakeDeviceGateway(
            RemnawaveUser(
                uuid=self.account_id,
                username="test",
                status="ACTIVE",
                expire_at=self.expires_at,
                subscription_url="https://panel.test/sub",
                telegram_id=None,
                email=None,
                tag=None,
                hwid_device_limit=3,
            )
        )
        self.patches = [
            patch("app.services.devices.now_utc", side_effect=lambda: self.now),
            patch(
                "app.services.devices.get_remnawave_gateway", return_value=self.gateway
            ),
            patch(
                "app.services.subscriptions.get_remnawave_gateway",
                return_value=self.gateway,
            ),
            patch(
                "app.services.purchases.get_remnawave_gateway",
                return_value=self.gateway,
            ),
            patch(
                "app.services.cache._cache",
                SimpleNamespace(
                    account_response_key=lambda x: f"account:{x}", delete=AsyncMock()
                ),
            ),
        ]
        for item in self.patches:
            item.start()
        self.app = create_app()

        async def session_override():
            async with self.sessions() as session:
                yield session

        async def account_override():
            async with self.sessions() as session:
                return await session.get(Account, self.account_id)

        self.app.dependency_overrides[get_session] = session_override
        self.app.dependency_overrides[get_current_account] = account_override
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        for item in reversed(self.patches):
            item.stop()
        await self.engine.dispose()
        self.tmp.cleanup()

    async def test_devices_endpoint_accepts_current_panel_hwid_response(self):
        gateway = RemnawaveGateway.__new__(RemnawaveGateway)
        async with AsyncClient(
            base_url="https://panel.test/api/",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "response": {
                            "total": 1.0,
                            "devices": [
                                {
                                    "hwid": "current-phone",
                                    "userId": 123,
                                    "deviceModel": "iPhone",
                                    "osVersion": "18",
                                    "platform": "iOS",
                                    "createdAt": "2026-10-19T18:55:00Z",
                                    "updatedAt": "2026-10-19T18:55:00Z",
                                }
                            ],
                        }
                    },
                )
            ),
        ) as panel:
            gateway._sdk = RemnawaveSDK(client=panel)
            self.gateway.get_hwid_devices = gateway.get_hwid_devices
            response = await self.client.get("/api/v1/devices")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["devices"][0]["hwid"], "current-phone")
        self.assertEqual(response.json()["devices"][0]["device_model"], "iPhone")
        self.assertEqual(response.json()["limit"], 3)

    async def _quote(self, quantity=1):
        response = await self.client.post(
            "/api/v1/devices/quote", json={"quantity": quantity}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def _purchase(self, quote=None, key="purchase"):
        quote = quote or await self._quote()
        response = await self.client.post(
            "/api/v1/devices/purchase",
            json={"quote_token": quote["quote_token"], "idempotency_key": key},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_list_and_remove_only_owned_device(self):
        response = await self.client.get("/api/v1/devices")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["limit"], 3)
        response = await self.client.post(
            "/api/v1/devices/remove", json={"hwid": "foreign-phone"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(self.gateway.devices), 1)
        response = await self.client.post(
            "/api/v1/devices/remove", json={"hwid": "phone"}
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.gateway.devices, [])

    async def test_reset_keeps_paid_quota(self):
        await self._purchase()
        response = await self.client.post("/api/v1/devices/reset")
        self.assertEqual(response.status_code, 204)
        response = await self.client.get("/api/v1/devices")
        self.assertEqual(response.json()["limit"], 4)
        self.assertEqual(response.json()["devices"], [])

    async def test_prorated_price_and_shared_expiry(self):
        self.now += timedelta(days=60)
        quote = await self._quote(2)
        self.assertEqual(quote["amount_rub"], 90)
        self.assertEqual(quote["limit"], 5)
        result = await self._purchase(quote)
        self.assertTrue(result["applied"])
        self.assertEqual(self.gateway.limit_calls, [5])
        async with self.sessions() as session:
            account = await session.get(Account, self.account_id)
            self.assertEqual(account.balance, 1910)
            self.assertEqual(
                account.subscription_expires_at.replace(tzinfo=UTC), self.expires_at
            )

    async def test_duplicate_purchase_debits_once(self):
        quote = await self._quote()
        first = await self._purchase(quote)
        second = await self._purchase(quote)
        self.assertEqual(first["purchase_id"], second["purchase_id"])
        async with self.sessions() as session:
            self.assertEqual(len(list(await session.scalars(select(LedgerEntry)))), 1)
            self.assertEqual(
                len(list(await session.scalars(select(DevicePrepayment)))), 1
            )

    async def test_panel_outage_keeps_paid_order_for_reconciliation(self):
        self.gateway.fail_updates = True
        result = await self._purchase()
        self.assertFalse(result["applied"])
        response = await self.client.get("/api/v1/devices")
        self.assertTrue(response.json()["sync_pending"])
        async with self.sessions() as session:
            self.assertEqual(
                (await session.get(Account, self.account_id)).balance, 1865
            )
        self.gateway.fail_updates = False
        async with self.sessions() as session:
            self.assertEqual(
                await reconcile_device_purchases(
                    session, gateway_factory=lambda: self.gateway
                ),
                1,
            )
        response = await self.client.get("/api/v1/devices")
        self.assertEqual(response.json()["limit"], 4)

    async def test_unapplied_expired_order_is_refunded_once(self):
        self.gateway.fail_updates = True
        await self._purchase()
        self.now += timedelta(days=91)
        async with self.sessions() as session:
            await reconcile_device_purchases(
                session, gateway_factory=lambda: self.gateway
            )
            await reconcile_device_purchases(
                session, gateway_factory=lambda: self.gateway
            )
            self.assertEqual(
                (await session.get(Account, self.account_id)).balance, 2000
            )
            purchase = await session.scalar(select(DevicePurchase))
            self.assertIsNotNone(purchase.refunded_at)

    async def test_quote_cannot_be_tampered_with(self):
        quote = await self._quote()
        quote["quote_token"] = quote["quote_token"][:-8] + "xxxxxxxx"
        response = await self.client.post(
            "/api/v1/devices/purchase",
            json={"quote_token": quote["quote_token"], "idempotency_key": "tampered"},
        )
        self.assertEqual(response.status_code, 409)
        async with self.sessions() as session:
            self.assertEqual(
                (await session.get(Account, self.account_id)).balance, 2000
            )

    async def test_price_snapshot_survives_admin_change(self):
        await self._quote()
        async with self.sessions() as session:
            plan = await session.get(SubscriptionPlanRecord, "plan_3m")
            plan.extra_device_price_rub = 999
            await session.commit()
        self.now += timedelta(days=60)
        quote = await self._quote()
        self.assertEqual(quote["amount_rub"], 45)

    async def test_cancel_only_changes_next_renewal(self):
        await self._purchase()
        response = await self.client.put(
            "/api/v1/devices/renewal", json={"extra_count": 0}
        )
        self.assertEqual(response.status_code, 204)
        state = (await self.client.get("/api/v1/devices")).json()
        self.assertEqual(state["extra_count"], 1)
        self.assertEqual(state["renewal_extra_count"], 0)
        self.assertEqual(state["limit"], 4)

    async def test_paid_renewal_preserves_one_expiry_and_adds_full_period_price(self):
        await self._purchase()
        response = await self.client.post(
            "/api/v1/devices/plans/plan_1m/quote", json={}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total_amount_rub"], 249)
        response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={
                "idempotency_key": "renew",
                "extra_devices": 1,
                "expected_amount": 249,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.gateway.user.hwid_device_limit, 4)
        async with self.sessions() as session:
            account = await session.get(Account, self.account_id)
            self.assertEqual(
                account.subscription_expires_at.replace(tzinfo=UTC),
                self.expires_at + timedelta(days=30),
            )
            self.assertEqual(account.balance, 2000 - 135 - 249)

    async def test_early_renewal_downgrade_credits_unused_actual_payment(self):
        await self._purchase()
        self.now += timedelta(days=30)
        response = await self.client.put(
            "/api/v1/devices/renewal", json={"extra_count": 0}
        )
        self.assertEqual(response.status_code, 204)
        quote = (
            await self.client.post("/api/v1/devices/plans/plan_1m/quote", json={})
        ).json()
        self.assertEqual(quote["refund_rub"], 90)
        response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "downgrade", "extra_devices": 0},
        )
        self.assertEqual(response.status_code, 200, response.text)
        async with self.sessions() as session:
            self.assertEqual(
                (await session.get(Account, self.account_id)).balance,
                2000 - 135 - 199 + 90,
            )
            self.assertEqual(
                (await session.get(AccountDeviceSettings, self.account_id)).extra_count,
                0,
            )
        self.assertEqual(self.gateway.user.hwid_device_limit, 3)

    async def test_expected_price_mismatch_does_not_charge(self):
        response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={
                "idempotency_key": "price-mismatch",
                "extra_devices": 1,
                "expected_amount": 1,
            },
        )
        self.assertEqual(response.status_code, 409)
        async with self.sessions() as session:
            self.assertEqual(
                (await session.get(Account, self.account_id)).balance, 2000
            )

    async def test_downgrade_refunds_only_removed_seat_across_separate_purchases(self):
        await self._purchase(key="first-seat")
        await self._purchase(key="second-seat")
        self.now += timedelta(days=30)
        quote = await self.client.post(
            "/api/v1/devices/plans/plan_1m/quote", json={"extra_devices": 1}
        )
        self.assertEqual(quote.status_code, 200, quote.text)
        self.assertEqual(quote.json()["refund_rub"], 90)
        response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "keep-one", "extra_devices": 1},
        )
        self.assertEqual(response.status_code, 200, response.text)
        async with self.sessions() as session:
            lots = list(
                await session.scalars(
                    select(DevicePrepayment).order_by(DevicePrepayment.id)
                )
            )
            self.assertEqual([lot.active_quantity for lot in lots], [1, 0, 1])
            self.assertEqual(
                (await session.get(Account, self.account_id)).balance,
                2000 - 270 - 249 + 90,
            )

    async def test_multiple_prepaid_terms_use_each_terms_discount(self):
        response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "early-renew"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.now += timedelta(days=60)
        quote = await self._quote()
        self.assertEqual(quote["amount_rub"], 45 + 50)
        self.assertEqual(
            datetime.fromisoformat(quote["expires_at"]).replace(tzinfo=UTC),
            self.expires_at + timedelta(days=30),
        )

    async def test_insufficient_funds_returns_conflict_without_order(self):
        async with self.sessions() as session:
            (await session.get(Account, self.account_id)).balance = 1
            await session.commit()
        quote = await self._quote()
        response = await self.client.post(
            "/api/v1/devices/purchase",
            json={"idempotency_key": "no-funds", "quote_token": quote["quote_token"]},
        )
        self.assertEqual(response.status_code, 409, response.text)
        async with self.sessions() as session:
            self.assertIsNone(await session.scalar(select(DevicePurchase)))

    async def test_reused_key_with_different_quote_is_rejected(self):
        await self._purchase()
        quote = await self._quote(2)
        response = await self.client.post(
            "/api/v1/devices/purchase",
            json={"idempotency_key": "purchase", "quote_token": quote["quote_token"]},
        )
        self.assertEqual(response.status_code, 409)

    async def test_excess_registered_devices_block_downgrade_before_debit(self):
        await self._purchase()
        self.gateway.devices = [{"hwid": str(i)} for i in range(4)]
        response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={"idempotency_key": "excess", "extra_devices": 0},
        )
        self.assertEqual(response.status_code, 409, response.text)
        async with self.sessions() as session:
            self.assertEqual(
                (await session.get(Account, self.account_id)).balance, 1865
            )

    async def test_unlimited_account_keeps_manual_limit_and_cannot_buy(self):
        self.gateway.user.hwid_device_limit = 0
        response = await self.client.get("/api/v1/devices")
        self.assertEqual(response.json()["limit"], 0)
        response = await self.client.post("/api/v1/devices/quote", json={"quantity": 1})
        self.assertEqual(response.status_code, 422)

    async def test_previously_disabled_price_can_be_configured_later(self):
        async with self.sessions() as session:
            plan = await session.get(SubscriptionPlanRecord, "plan_3m")
            plan.extra_device_price_rub = None
            await session.commit()
        response = await self.client.get("/api/v1/devices")
        self.assertFalse(response.json()["can_purchase"])
        async with self.sessions() as session:
            (
                await session.get(SubscriptionPlanRecord, "plan_3m")
            ).extra_device_price_rub = 135
            await session.commit()
        self.assertEqual((await self._quote())["amount_rub"], 135)

    async def test_card_renewal_applies_paid_seats_once_from_persisted_quote(self):
        gateway = FakeYooKassaGateway()
        with patch("app.services.payments.get_yookassa_gateway", return_value=gateway):
            response = await self.client.post(
                "/api/v1/payments/yookassa/plans/plan_1m",
                json={
                    "idempotency_key": "card-devices",
                    "extra_devices": 1,
                    "expected_amount": 384,
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["amount"], 384)
            payment_id = response.json()["provider_payment_id"]
            gateway.put_event(
                "card-success",
                PaymentWebhookEvent(
                    provider=PaymentProvider.YOOKASSA,
                    provider_event_id="card-success",
                    provider_payment_id=payment_id,
                    status=PaymentStatus.SUCCEEDED,
                    amount=384,
                    currency="RUB",
                    flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                    account_id=self.account_id,
                ),
            )
            for _ in range(2):
                response = await self.client.post(
                    "/api/v1/webhooks/payments/yookassa",
                    content=json.dumps({"event_id": "card-success"}),
                    headers={"content-type": "application/json"},
                )
                self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.gateway.user.hwid_device_limit, 4)
        async with self.sessions() as session:
            self.assertEqual(
                (await session.get(Account, self.account_id)).balance, 2000
            )
            self.assertEqual(
                len(list(await session.scalars(select(DevicePrepayment)))), 2
            )

    async def test_stars_cannot_charge_ruble_device_addon(self):
        response = await self.client.post(
            "/api/v1/payments/telegram-stars/plans/plan_1m",
            json={"idempotency_key": "stars-devices", "extra_devices": 1},
        )
        self.assertEqual(response.status_code, 409, response.text)

    async def test_changed_refund_requires_new_confirmation_before_charge(self):
        await self._purchase()
        self.now += timedelta(days=30)
        response = await self.client.post(
            "/api/v1/subscriptions/wallet/plans/plan_1m",
            json={
                "idempotency_key": "refund-mismatch",
                "extra_devices": 0,
                "expected_amount": 199,
                "expected_refund_rub": 999,
            },
        )
        self.assertEqual(response.status_code, 409, response.text)
        async with self.sessions() as session:
            self.assertEqual(
                (await session.get(Account, self.account_id)).balance, 1865
            )
