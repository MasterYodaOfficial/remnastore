from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import tempfile
import unittest
import uuid
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    Account,
    AccountEventLog,
    AccountStatus,
    Admin,
    AdminActionLog,
    AuthAccount,
    AuthProvider,
    LedgerEntry,
    LedgerEntryType,
    Payment,
    ReferralAttribution,
    ReferralReward,
    SubscriptionGrant,
    Withdrawal,
    WithdrawalDestinationType,
    WithdrawalStatus,
)
from app.db.session import get_session
from app.domain.payments import PaymentFlowType, PaymentProvider, PaymentStatus
from app.integrations.remnawave.client import RemnawaveUser
from app.main import create_app
from app.services.admin_auth import create_admin
from app.services.i18n import translate


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


class AdminAccountEndpointsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "admin-accounts.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._fake_gateway = FakeRemnawaveGateway(users={})

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module
        import app.services.admin_auth as admin_auth_service
        import app.services.admin_subscriptions as admin_subscriptions_service

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()

        self._admin_auth_service = admin_auth_service
        self._original_bootstrap_username = admin_auth_service.settings.admin_bootstrap_username
        self._original_bootstrap_password = admin_auth_service.settings.admin_bootstrap_password
        self._original_bootstrap_email = admin_auth_service.settings.admin_bootstrap_email
        self._original_bootstrap_full_name = admin_auth_service.settings.admin_bootstrap_full_name
        admin_auth_service.settings.admin_bootstrap_username = ""
        admin_auth_service.settings.admin_bootstrap_password = ""
        admin_auth_service.settings.admin_bootstrap_email = ""
        admin_auth_service.settings.admin_bootstrap_full_name = ""

        self._admin_subscriptions_service = admin_subscriptions_service
        self._original_admin_gateway_factory = admin_subscriptions_service.get_remnawave_gateway
        admin_subscriptions_service.get_remnawave_gateway = lambda: self._fake_gateway

        self.app = create_app()

        async def override_get_session():
            async with self._session_factory() as session:
                yield session

        self.app.dependency_overrides[get_session] = override_get_session
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        self._cache_module._cache = self._original_cache
        self._admin_auth_service.settings.admin_bootstrap_username = self._original_bootstrap_username
        self._admin_auth_service.settings.admin_bootstrap_password = self._original_bootstrap_password
        self._admin_auth_service.settings.admin_bootstrap_email = self._original_bootstrap_email
        self._admin_auth_service.settings.admin_bootstrap_full_name = self._original_bootstrap_full_name
        self._admin_subscriptions_service.get_remnawave_gateway = self._original_admin_gateway_factory
        await self._engine.dispose()
        self._tmpdir.cleanup()

    async def _create_admin_token(self) -> str:
        async with self._session_factory() as session:
            admin = await create_admin(
                session,
                username="root",
                password="secret-password",
                email="root@example.com",
                full_name="Root Admin",
            )
            await session.commit()
            await session.refresh(admin)

        response = await self.client.post(
            "/api/v1/admin/auth/login",
            json={"login": "root", "password": "secret-password"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    async def test_search_accounts_by_auth_email_and_telegram_id(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email=None,
                display_name="Search Target",
                telegram_id=777000111,
                username="search_target",
                balance=900,
            )
            session.add(account)
            await session.flush()
            session.add(
                AuthAccount(
                    account_id=account.id,
                    provider=AuthProvider.GOOGLE,
                    provider_uid="google-search-target",
                    email="search-target@example.com",
                    display_name="Search Target",
                )
            )
            await session.commit()

        response_by_email = await self.client.get(
            "/api/v1/admin/accounts/search",
            params={"query": "search-target@example.com"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response_by_email.status_code, 200)
        body = response_by_email.json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["username"], "search_target")
        self.assertEqual(body["items"][0]["telegram_id"], 777000111)

        response_by_telegram = await self.client.get(
            "/api/v1/admin/accounts/search",
            params={"query": "777000111"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response_by_telegram.status_code, 200)
        self.assertEqual(len(response_by_telegram.json()["items"]), 1)

    async def test_subscription_plans_endpoint_returns_catalog(self) -> None:
        token = await self._create_admin_token()

        response = await self.client.get(
            "/api/v1/admin/accounts/subscription-plans",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(len(body), 1)
        self.assertIsInstance(body[0]["code"], str)
        self.assertIsInstance(body[0]["duration_days"], int)

    async def test_account_detail_returns_recent_finance_and_subscription_blocks(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email="detail@example.com",
                display_name="Detail User",
                telegram_id=555444333,
                username="detail_user",
                first_name="Detail",
                last_name="User",
                locale="ru",
                status=AccountStatus.ACTIVE,
                balance=1300,
                referral_code="DETAILCODE",
                referral_earnings=400,
                referrals_count=2,
                subscription_status="active",
                subscription_is_trial=False,
            )
            session.add(account)
            await session.flush()

            session.add(
                AuthAccount(
                    account_id=account.id,
                    provider=AuthProvider.SUPABASE,
                    provider_uid="supabase-detail-user",
                    email="detail@example.com",
                    display_name="Detail User",
                )
            )
            session.add(
                LedgerEntry(
                    account_id=account.id,
                    entry_type=LedgerEntryType.TOPUP_PAYMENT,
                    amount=500,
                    currency="RUB",
                    balance_before=800,
                    balance_after=1300,
                    reference_type="payment",
                    reference_id="pay-1",
                    comment="Пополнение",
                )
            )
            session.add(
                Payment(
                    account_id=account.id,
                    provider=PaymentProvider.YOOKASSA,
                    flow_type=PaymentFlowType.WALLET_TOPUP,
                    status=PaymentStatus.PENDING,
                    amount=500,
                    currency="RUB",
                    provider_payment_id="detail-payment",
                    description="Пополнение баланса",
                )
            )
            session.add(
                Withdrawal(
                    account_id=account.id,
                    amount=300,
                    destination_type=WithdrawalDestinationType.SBP,
                    destination_value="+79990000000",
                    status=WithdrawalStatus.NEW,
                    user_comment="Нужен вывод",
                )
            )
            await session.commit()
            account_id = str(account.id)

        response = await self.client.get(
            f"/api/v1/admin/accounts/{account_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], account_id)
        self.assertEqual(body["email"], "detail@example.com")
        self.assertEqual(body["balance"], 1300)
        self.assertEqual(body["subscription_status"], "active")
        self.assertEqual(body["ledger_entries_count"], 1)
        self.assertEqual(body["payments_count"], 1)
        self.assertEqual(body["pending_payments_count"], 1)
        self.assertEqual(body["withdrawals_count"], 1)
        self.assertEqual(body["pending_withdrawals_count"], 1)
        self.assertEqual(len(body["auth_accounts"]), 1)
        self.assertEqual(len(body["recent_ledger_entries"]), 1)
        self.assertEqual(len(body["recent_payments"]), 1)
        self.assertEqual(len(body["recent_withdrawals"]), 1)
        self.assertEqual(body["recent_ledger_entries"][0]["comment"], "Пополнение")
        self.assertEqual(body["recent_payments"][0]["status"], PaymentStatus.PENDING.value)
        self.assertEqual(body["recent_withdrawals"][0]["status"], WithdrawalStatus.NEW.value)
        self.assertEqual(body["referral_chain"]["direct_referrals_count"], 0)
        self.assertEqual(body["referral_chain"]["rewarded_direct_referrals_count"], 0)
        self.assertEqual(body["referral_chain"]["pending_direct_referrals_count"], 0)
        self.assertEqual(body["referral_chain"]["direct_referrals"], [])
        self.assertIsNone(body["referral_chain"]["referrer"])

    async def test_account_detail_returns_referral_chain(self) -> None:
        token = await self._create_admin_token()
        now = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)

        async with self._session_factory() as session:
            referrer = Account(
                email="partner@example.com",
                display_name="Partner User",
                username="partner_user",
                telegram_id=401001,
                referral_code="PARTNER",
                status=AccountStatus.ACTIVE,
            )
            account = Account(
                email="ref-owner@example.com",
                display_name="Referral Owner",
                username="ref_owner",
                telegram_id=402002,
                referral_code="OWNER",
                referral_earnings=180,
                referrals_count=2,
                referral_reward_rate=30,
                status=AccountStatus.ACTIVE,
            )
            rewarded_referral = Account(
                email="rewarded@example.com",
                display_name="Rewarded Referral",
                username="rewarded_ref",
                telegram_id=403003,
                referral_code="REWARDED",
                referred_by_account_id=account.id,
                subscription_status="ACTIVE",
                subscription_expires_at=now + timedelta(days=30),
                status=AccountStatus.ACTIVE,
            )
            pending_referral = Account(
                email="pending@example.com",
                display_name="Pending Referral",
                username="pending_ref",
                telegram_id=404004,
                referral_code="PENDING",
                referred_by_account_id=account.id,
                status=AccountStatus.BLOCKED,
            )
            session.add_all([referrer, account, rewarded_referral, pending_referral])
            await session.flush()

            account.referred_by_account_id = referrer.id
            rewarded_referral.referred_by_account_id = account.id
            pending_referral.referred_by_account_id = account.id

            account_referrer_attribution = ReferralAttribution(
                referrer_account_id=referrer.id,
                referred_account_id=account.id,
                referral_code="PARTNER",
                created_at=now - timedelta(days=14),
            )
            rewarded_attribution = ReferralAttribution(
                referrer_account_id=account.id,
                referred_account_id=rewarded_referral.id,
                referral_code="OWNER",
                created_at=now - timedelta(days=5),
            )
            pending_attribution = ReferralAttribution(
                referrer_account_id=account.id,
                referred_account_id=pending_referral.id,
                referral_code="OWNER",
                created_at=now - timedelta(days=2),
            )
            session.add_all(
                [
                    account_referrer_attribution,
                    rewarded_attribution,
                    pending_attribution,
                ]
            )
            await session.flush()

            session.add(
                ReferralReward(
                    attribution_id=rewarded_attribution.id,
                    referrer_account_id=account.id,
                    referred_account_id=rewarded_referral.id,
                    subscription_grant_id=901,
                    ledger_entry_id=801,
                    purchase_amount_rub=600,
                    reward_amount=180,
                    reward_rate=30,
                    currency="RUB",
                    created_at=now - timedelta(days=4),
                )
            )
            await session.commit()
            account_id = str(account.id)

        response = await self.client.get(
            f"/api/v1/admin/accounts/{account_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        chain = response.json()["referral_chain"]
        self.assertEqual(chain["effective_reward_rate"], 30.0)
        self.assertEqual(chain["direct_referrals_count"], 2)
        self.assertEqual(chain["rewarded_direct_referrals_count"], 1)
        self.assertEqual(chain["pending_direct_referrals_count"], 1)
        self.assertEqual(chain["referrer"]["username"], "partner_user")
        self.assertEqual(chain["referrer"]["referral_code"], "PARTNER")
        self.assertEqual(chain["referrer"]["status"], AccountStatus.ACTIVE.value)
        self.assertEqual(chain["direct_referrals"][0]["username"], "pending_ref")
        self.assertEqual(chain["direct_referrals"][0]["reward_status"], "pending")
        self.assertEqual(chain["direct_referrals"][0]["reward_amount"], 0)
        self.assertEqual(chain["direct_referrals"][0]["status"], AccountStatus.BLOCKED.value)
        self.assertEqual(chain["direct_referrals"][1]["username"], "rewarded_ref")
        self.assertEqual(chain["direct_referrals"][1]["reward_status"], "rewarded")
        self.assertEqual(chain["direct_referrals"][1]["reward_amount"], 180)
        self.assertEqual(chain["direct_referrals"][1]["reward_rate"], 30.0)
        self.assertEqual(chain["direct_referrals"][1]["purchase_amount"], 600)
        self.assertEqual(chain["direct_referrals"][1]["subscription_status"], "ACTIVE")
        self.assertIsNotNone(chain["direct_referrals"][1]["reward_created_at"])

    async def test_account_ledger_entries_history_supports_pagination_and_entry_type_filter(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email="ledger-history@example.com",
                display_name="Ledger History User",
                balance=1150,
            )
            session.add(account)
            await session.flush()

            session.add_all(
                [
                    LedgerEntry(
                        account_id=account.id,
                        entry_type=LedgerEntryType.TOPUP_PAYMENT,
                        amount=500,
                        currency="RUB",
                        balance_before=0,
                        balance_after=500,
                        reference_type="payment",
                        reference_id="pay-1",
                        comment="Первое пополнение",
                        created_at=datetime(2026, 3, 11, 10, 0, tzinfo=UTC),
                    ),
                    LedgerEntry(
                        account_id=account.id,
                        entry_type=LedgerEntryType.ADMIN_CREDIT,
                        amount=700,
                        currency="RUB",
                        balance_before=500,
                        balance_after=1200,
                        reference_type="admin_adjustment",
                        reference_id="adj-1",
                        comment="Ручное начисление",
                        created_by_admin_id=uuid.uuid4(),
                        created_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
                    ),
                    LedgerEntry(
                        account_id=account.id,
                        entry_type=LedgerEntryType.ADMIN_DEBIT,
                        amount=-50,
                        currency="RUB",
                        balance_before=1200,
                        balance_after=1150,
                        reference_type="admin_adjustment",
                        reference_id="adj-2",
                        comment="Коррекция",
                        created_by_admin_id=uuid.uuid4(),
                        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()
            account_id = str(account.id)

        page_response = await self.client.get(
            f"/api/v1/admin/accounts/{account_id}/ledger-entries",
            params={"limit": 2, "offset": 0},
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(page_response.status_code, 200)
        page_body = page_response.json()
        self.assertEqual(page_body["total"], 3)
        self.assertEqual(page_body["limit"], 2)
        self.assertEqual([item["entry_type"] for item in page_body["items"]], [
            LedgerEntryType.ADMIN_DEBIT.value,
            LedgerEntryType.ADMIN_CREDIT.value,
        ])
        self.assertIsNotNone(page_body["items"][0]["created_by_admin_id"])

        filtered_response = await self.client.get(
            f"/api/v1/admin/accounts/{account_id}/ledger-entries",
            params={"entry_type": LedgerEntryType.ADMIN_CREDIT.value, "limit": 10, "offset": 0},
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(filtered_response.status_code, 200)
        filtered_body = filtered_response.json()
        self.assertEqual(filtered_body["total"], 1)
        self.assertEqual(len(filtered_body["items"]), 1)
        self.assertEqual(filtered_body["items"][0]["entry_type"], LedgerEntryType.ADMIN_CREDIT.value)
        self.assertEqual(filtered_body["items"][0]["comment"], "Ручное начисление")

    async def test_balance_adjustment_updates_balance_and_is_idempotent(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email="adjust@example.com",
                display_name="Adjust User",
                balance=1000,
            )
            session.add(account)
            await session.commit()
            account_id = str(account.id)

        payload = {
            "amount": 250,
            "comment": "Ручная корректировка по сверке",
            "idempotency_key": "admin-adjust-1",
        }

        response = await self.client.post(
            f"/api/v1/admin/accounts/{account_id}/balance-adjustments",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["account_id"], account_id)
        self.assertEqual(body["balance"], 1250)
        self.assertEqual(body["ledger_entry"]["entry_type"], LedgerEntryType.ADMIN_CREDIT.value)
        self.assertEqual(body["ledger_entry"]["amount"], 250)
        self.assertEqual(body["ledger_entry"]["comment"], "Ручная корректировка по сверке")

        duplicate_response = await self.client.post(
            f"/api/v1/admin/accounts/{account_id}/balance-adjustments",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(duplicate_response.status_code, 200)
        duplicate_body = duplicate_response.json()
        self.assertEqual(duplicate_body["ledger_entry"]["id"], body["ledger_entry"]["id"])
        self.assertEqual(duplicate_body["balance"], 1250)

        async with self._session_factory() as session:
            stored_account = await session.get(Account, uuid.UUID(account_id))
            assert stored_account is not None
            self.assertEqual(stored_account.balance, 1250)

            result = await session.execute(
                select(LedgerEntry)
                .where(LedgerEntry.account_id == stored_account.id)
                .order_by(LedgerEntry.id.asc())
            )
            entries = list(result.scalars().all())
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].entry_type, LedgerEntryType.ADMIN_CREDIT)

            event_logs = list(
                (
                    await session.execute(
                        select(AccountEventLog)
                        .where(AccountEventLog.account_id == stored_account.id)
                        .order_by(AccountEventLog.id.asc())
                    )
                ).scalars()
            )
            self.assertEqual([item.event_type for item in event_logs], ["admin.balance_adjustment"])
            self.assertEqual(event_logs[0].payload["ledger_entry_id"], entries[0].id)

    async def test_balance_adjustment_rejects_insufficient_funds(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email="debit@example.com",
                display_name="Debit User",
                balance=120,
            )
            session.add(account)
            await session.commit()
            account_id = str(account.id)

        response = await self.client.post(
            f"/api/v1/admin/accounts/{account_id}/balance-adjustments",
            json={
                "amount": -300,
                "comment": "Списать ошибочное начисление",
                "idempotency_key": "admin-adjust-2",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], translate("api.ledger.errors.insufficient_funds"))

        async with self._session_factory() as session:
            stored_account = await session.get(Account, uuid.UUID(account_id))
            assert stored_account is not None
            self.assertEqual(stored_account.balance, 120)

            result = await session.execute(
                select(LedgerEntry).where(LedgerEntry.account_id == stored_account.id)
            )
            self.assertEqual(list(result.scalars().all()), [])

    async def test_subscription_grant_updates_subscription_and_is_idempotent(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email="grant@example.com",
                display_name="Grant User",
                telegram_id=700100200,
                balance=0,
            )
            session.add(account)
            await session.commit()
            account_id = str(account.id)

        response = await self.client.post(
            f"/api/v1/admin/accounts/{account_id}/subscription-grants",
            json={
                "plan_code": "plan_1m",
                "comment": "Выдали доступ после офлайн-оплаты",
                "idempotency_key": "admin-subscription-grant-1",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["account_id"], account_id)
        self.assertEqual(body["plan_code"], "plan_1m")
        self.assertEqual(body["subscription_status"], "ACTIVE")
        self.assertTrue(body["subscription_url"].startswith("https://panel.test/sub/"))

        duplicate_response = await self.client.post(
            f"/api/v1/admin/accounts/{account_id}/subscription-grants",
            json={
                "plan_code": "plan_1m",
                "comment": "Выдали доступ после офлайн-оплаты",
                "idempotency_key": "admin-subscription-grant-1",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(duplicate_response.status_code, 200)
        duplicate_body = duplicate_response.json()
        self.assertEqual(duplicate_body["subscription_grant_id"], body["subscription_grant_id"])
        self.assertEqual(duplicate_body["audit_log_id"], body["audit_log_id"])

        async with self._session_factory() as session:
            stored_account = await session.get(Account, uuid.UUID(account_id))
            assert stored_account is not None
            self.assertEqual(stored_account.subscription_status, "ACTIVE")
            self.assertFalse(stored_account.subscription_is_trial)
            self.assertIsNotNone(stored_account.subscription_expires_at)

            grants_result = await session.execute(
                select(SubscriptionGrant)
                .where(SubscriptionGrant.account_id == stored_account.id)
                .order_by(SubscriptionGrant.id.asc())
            )
            grants = list(grants_result.scalars().all())
            self.assertEqual(len(grants), 1)
            self.assertEqual(grants[0].purchase_source, "admin")
            self.assertEqual(grants[0].amount, 0)
            self.assertIsNotNone(grants[0].applied_at)

            logs_result = await session.execute(
                select(AdminActionLog)
                .where(AdminActionLog.target_account_id == stored_account.id)
                .order_by(AdminActionLog.id.asc())
            )
            logs = list(logs_result.scalars().all())
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].comment, "Выдали доступ после офлайн-оплаты")
            self.assertEqual(logs[0].payload["plan_code"], "plan_1m")
            self.assertEqual(logs[0].payload["subscription_grant_id"], grants[0].id)

            event_logs = list(
                (
                    await session.execute(
                        select(AccountEventLog)
                        .where(AccountEventLog.account_id == stored_account.id)
                        .order_by(AccountEventLog.id.asc())
                    )
                ).scalars()
            )
            self.assertEqual([item.event_type for item in event_logs], ["admin.subscription_grant"])
            self.assertEqual(event_logs[0].payload["subscription_grant_id"], grants[0].id)

    async def test_account_status_change_updates_status_and_is_idempotent(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email="blocked-user@example.com",
                display_name="Blocked User",
                status=AccountStatus.ACTIVE,
            )
            session.add(account)
            await session.commit()
            account_id = str(account.id)

        payload = {
            "status": AccountStatus.BLOCKED.value,
            "comment": "Блокировка по abuse signal",
            "idempotency_key": "admin-status-change-1",
        }

        response = await self.client.post(
            f"/api/v1/admin/accounts/{account_id}/status",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["account_id"], account_id)
        self.assertEqual(body["previous_status"], AccountStatus.ACTIVE.value)
        self.assertEqual(body["status"], AccountStatus.BLOCKED.value)

        duplicate_response = await self.client.post(
            f"/api/v1/admin/accounts/{account_id}/status",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(duplicate_response.status_code, 200)
        duplicate_body = duplicate_response.json()
        self.assertEqual(duplicate_body["audit_log_id"], body["audit_log_id"])
        self.assertEqual(duplicate_body["status"], AccountStatus.BLOCKED.value)

        async with self._session_factory() as session:
            stored_account = await session.get(Account, uuid.UUID(account_id))
            assert stored_account is not None
            self.assertEqual(stored_account.status, AccountStatus.BLOCKED)

            logs_result = await session.execute(
                select(AdminActionLog)
                .where(AdminActionLog.target_account_id == stored_account.id)
                .order_by(AdminActionLog.id.asc())
            )
            logs = list(logs_result.scalars().all())
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].comment, "Блокировка по abuse signal")
            self.assertEqual(logs[0].payload["previous_status"], AccountStatus.ACTIVE.value)
            self.assertEqual(logs[0].payload["next_status"], AccountStatus.BLOCKED.value)

            event_logs = list(
                (
                    await session.execute(
                        select(AccountEventLog)
                        .where(AccountEventLog.account_id == stored_account.id)
                        .order_by(AccountEventLog.id.asc())
                    )
                ).scalars()
            )
            self.assertEqual([item.event_type for item in event_logs], ["admin.account_status_change"])
            self.assertEqual(event_logs[0].payload["next_status"], AccountStatus.BLOCKED.value)

    async def test_account_event_logs_endpoint_returns_latest_events(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            account = Account(
                email="events@example.com",
                display_name="Events User",
                status=AccountStatus.ACTIVE,
            )
            session.add(account)
            await session.flush()
            session.add_all(
                [
                    AccountEventLog(
                        account_id=account.id,
                        actor_account_id=account.id,
                        event_type="payment.intent.created",
                        outcome="success",
                        source="api",
                        request_id="req-1",
                        payload={"payment_id": 11},
                    ),
                    AccountEventLog(
                        account_id=account.id,
                        actor_admin_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                        event_type="payment.finalized",
                        outcome="failure",
                        source="webhook",
                        request_id="req-2",
                        payload={"final_status": "failed"},
                    ),
                    AccountEventLog(
                        account_id=account.id,
                        actor_admin_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                        event_type="admin.balance_adjustment",
                        outcome="success",
                        source="admin",
                        request_id="req-3",
                        payload={"amount": 100},
                    ),
                ]
            )
            await session.commit()
            account_id = str(account.id)

        response = await self.client.get(
            f"/api/v1/admin/accounts/{account_id}/event-logs",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["items"][0]["event_type"], "admin.balance_adjustment")
        self.assertEqual(body["items"][1]["event_type"], "payment.finalized")
        self.assertEqual(body["items"][2]["event_type"], "payment.intent.created")

        filtered_response = await self.client.get(
            f"/api/v1/admin/accounts/{account_id}/event-logs",
            params=[
                ("event_type", "payment.intent.created"),
                ("source", "api"),
                ("outcome", "success"),
                ("request_id", "req-1"),
            ],
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(filtered_response.status_code, 200)
        filtered_body = filtered_response.json()
        self.assertEqual(filtered_body["total"], 1)
        self.assertEqual(filtered_body["items"][0]["event_type"], "payment.intent.created")
        self.assertEqual(filtered_body["items"][0]["payload"]["payment_id"], 11)

    async def test_global_account_event_log_search_returns_context_and_supports_filters(self) -> None:
        token = await self._create_admin_token()

        async with self._session_factory() as session:
            admin = (
                await session.execute(select(Admin).where(Admin.username == "root"))
            ).scalar_one()
            account_a = Account(
                email="alpha@example.com",
                display_name="Alpha User",
                telegram_id=700001,
                username="alpha",
                status=AccountStatus.ACTIVE,
            )
            account_b = Account(
                email="beta@example.com",
                display_name="Beta User",
                telegram_id=700002,
                username="beta",
                status=AccountStatus.BLOCKED,
            )
            session.add_all([account_a, account_b])
            await session.flush()
            session.add_all(
                [
                    AccountEventLog(
                        account_id=account_a.id,
                        actor_account_id=account_a.id,
                        actor_admin_id=admin.id,
                        event_type="payment.intent.created",
                        outcome="success",
                        source="api",
                        request_id="req-alpha",
                        payload={"payment_id": 1001},
                    ),
                    AccountEventLog(
                        account_id=account_b.id,
                        actor_account_id=account_a.id,
                        actor_admin_id=admin.id,
                        event_type="admin.balance_adjustment",
                        outcome="success",
                        source="admin",
                        request_id="req-beta",
                        payload={"amount": 500},
                    ),
                    AccountEventLog(
                        account_id=account_b.id,
                        event_type="payment.finalized",
                        outcome="failure",
                        source="webhook",
                        request_id="req-failure",
                        payload={"reason": "provider_error"},
                    ),
                ]
            )
            await session.commit()

        filtered_response = await self.client.get(
            "/api/v1/admin/accounts/event-logs/search",
            params=[
                ("actor_admin_id", str(admin.id)),
                ("source", "admin"),
            ],
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(filtered_response.status_code, 200)
        filtered_body = filtered_response.json()
        self.assertEqual(filtered_body["total"], 1)
        self.assertEqual(filtered_body["items"][0]["event_type"], "admin.balance_adjustment")
        self.assertEqual(filtered_body["items"][0]["account"]["display_name"], "Beta User")
        self.assertEqual(filtered_body["items"][0]["actor_account"]["username"], "alpha")
        self.assertEqual(filtered_body["items"][0]["actor_admin"]["username"], "root")

        telegram_response = await self.client.get(
            "/api/v1/admin/accounts/event-logs/search",
            params={"telegram_id": "700001"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(telegram_response.status_code, 200)
        telegram_body = telegram_response.json()
        self.assertEqual(telegram_body["total"], 1)
        self.assertEqual(telegram_body["items"][0]["request_id"], "req-alpha")

        request_response = await self.client.get(
            "/api/v1/admin/accounts/event-logs/search",
            params=[
                ("request_id", "req-failure"),
                ("event_type", "payment.finalized"),
                ("outcome", "failure"),
            ],
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(request_response.status_code, 200)
        request_body = request_response.json()
        self.assertEqual(request_body["total"], 1)
        self.assertEqual(request_body["items"][0]["account"]["email"], "beta@example.com")
        self.assertEqual(request_body["items"][0]["payload"]["reason"], "provider_error")
