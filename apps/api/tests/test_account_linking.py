from dataclasses import dataclass
from datetime import UTC, datetime
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
    AdminActionLog,
    AdminActionType,
    AuthAccount,
    AuthLinkToken,
    AuthProvider,
    Broadcast,
    BroadcastChannel,
    BroadcastContentType,
    BroadcastDelivery,
    BroadcastDeliveryStatus,
    BroadcastRun,
    BroadcastRunStatus,
    BroadcastRunType,
    BroadcastStatus,
    LinkType,
    LoginSource,
    Notification,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationPriority,
    NotificationType,
    Payment,
    PaymentEvent,
    SubscriptionGrant,
    TelegramReferralIntent,
    Withdrawal,
    WithdrawalDestinationType,
    WithdrawalStatus,
)
from app.db.session import get_session
from app.domain.payments import PaymentFlowType, PaymentProvider, PaymentStatus
from app.integrations.remnawave.client import RemnawaveUser
from app.main import create_app
from app.services import account_linking
from app.services.account_linking import create_telegram_link_token
from app.services.i18n import translate


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

    def __post_init__(self) -> None:
        self.deleted_user_ids: list[uuid.UUID] = []

    async def get_user_by_uuid(self, user_uuid: uuid.UUID) -> RemnawaveUser | None:
        return self.users.get(user_uuid)

    async def get_users_by_email(self, email: str) -> list[RemnawaveUser]:
        return [user for user in self.users.values() if user.email == email]

    async def get_users_by_telegram_id(self, telegram_id: int) -> list[RemnawaveUser]:
        return [user for user in self.users.values() if user.telegram_id == telegram_id]

    async def upsert_user(
        self,
        *,
        user_uuid: uuid.UUID,
        expire_at: datetime,
        email: str | None,
        telegram_id: int | None,
        status: str | None,
        is_trial: bool,
    ) -> RemnawaveUser:
        user = RemnawaveUser(
            uuid=user_uuid,
            username=f"acc_{user_uuid.hex}",
            status=status or "ACTIVE",
            expire_at=expire_at,
            subscription_url=f"https://panel.test/sub/{user_uuid.hex[:8]}",
            telegram_id=telegram_id,
            email=email,
            tag="TRIAL" if is_trial else None,
        )
        self.users[user_uuid] = user
        return user

    async def delete_user(self, user_uuid: uuid.UUID) -> None:
        self.deleted_user_ids.append(user_uuid)
        self.users.pop(user_uuid, None)


class AccountLinkingFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "account-linking.sqlite3"
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

        self._original_webapp_url = settings.webapp_url
        self._original_bot_username = settings.telegram_bot_username
        settings.webapp_url = "https://webapp.test"
        settings.telegram_bot_username = "test_bot"

        self._original_utcnow = account_linking._utcnow
        account_linking._utcnow = lambda: datetime.now(UTC).replace(tzinfo=None)
        self._original_gateway_factory = account_linking.get_remnawave_gateway
        account_linking.get_remnawave_gateway = lambda: self._fake_gateway

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
        settings.webapp_url = self._original_webapp_url
        settings.telegram_bot_username = self._original_bot_username
        account_linking._utcnow = self._original_utcnow
        account_linking.get_remnawave_gateway = self._original_gateway_factory
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

    async def _create_auth_account(
        self,
        *,
        account_id: uuid.UUID,
        provider: AuthProvider,
        provider_uid: str,
        email: str | None = None,
        display_name: str | None = None,
    ) -> AuthAccount:
        async with self._session_factory() as session:
            auth_account = AuthAccount(
                account_id=account_id,
                provider=provider,
                provider_uid=provider_uid,
                email=email,
                display_name=display_name,
            )
            session.add(auth_account)
            await session.commit()
            await session.refresh(auth_account)
            return auth_account

    async def _get_account(self, account_id: uuid.UUID) -> Account | None:
        async with self._session_factory() as session:
            return await session.get(Account, account_id)

    async def _get_link_token(self, link_token: str) -> AuthLinkToken | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AuthLinkToken).where(AuthLinkToken.link_token == link_token)
            )
            return result.scalar_one_or_none()

    async def _get_auth_accounts(self, account_id: uuid.UUID) -> list[AuthAccount]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AuthAccount).where(AuthAccount.account_id == account_id)
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

    async def _create_withdrawal(
        self,
        *,
        account_id: uuid.UUID,
        amount: int,
        destination_type: WithdrawalDestinationType = WithdrawalDestinationType.CARD,
        destination_value: str = "2200123412341234",
    ) -> Withdrawal:
        async with self._session_factory() as session:
            withdrawal = Withdrawal(
                account_id=account_id,
                amount=amount,
                destination_type=destination_type,
                destination_value=destination_value,
                status=WithdrawalStatus.NEW,
            )
            session.add(withdrawal)
            await session.commit()
            await session.refresh(withdrawal)
            return withdrawal

    async def _get_withdrawal(self, withdrawal_id: int) -> Withdrawal | None:
        async with self._session_factory() as session:
            return await session.get(Withdrawal, withdrawal_id)

    async def _merge_accounts_direct(
        self,
        *,
        source_account_id: uuid.UUID,
        target_account_id: uuid.UUID,
    ) -> Account:
        async with self._session_factory() as session:
            merged_account = await account_linking.merge_accounts(
                session,
                source_account_id=source_account_id,
                target_account_id=target_account_id,
                last_login_source=LoginSource.BROWSER_OAUTH,
            )
            await session.commit()
            await session.refresh(merged_account)
            return merged_account

    async def test_browser_to_telegram_flow_and_token_reuse(self) -> None:
        browser_account = await self._create_account(
            email="browser@example.com",
            display_name="Browser User",
            balance=15,
        )
        self._current_account_id = browser_account.id

        response = await self.client.post("/api/v1/accounts/link-telegram")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["expires_in_seconds"], 3600)
        self.assertEqual(
            body["link_url"], f"https://t.me/test_bot?start={body['link_token']}"
        )

        token = await self._get_link_token(body["link_token"])
        self.assertIsNotNone(token)
        assert token is not None
        self.assertEqual(token.account_id, browser_account.id)
        self.assertEqual(token.link_type, LinkType.TELEGRAM_FROM_BROWSER)

        confirm_response = await self.client.post(
            "/api/v1/accounts/link-telegram-confirm",
            json={
                "link_token": body["link_token"],
                "telegram_id": 100500,
                "username": "linked_telegram",
                "first_name": "Telegram",
                "last_name": "User",
                "is_premium": True,
            },
        )
        self.assertEqual(confirm_response.status_code, 200)
        confirm_body = confirm_response.json()
        self.assertEqual(confirm_body["id"], str(browser_account.id))
        self.assertEqual(confirm_body["telegram_id"], 100500)
        self.assertEqual(confirm_body["username"], "linked_telegram")
        self.assertEqual(confirm_body["last_login_source"], "browser_oauth")

        stored_account = await self._get_account(browser_account.id)
        self.assertIsNotNone(stored_account)
        assert stored_account is not None
        self.assertEqual(stored_account.telegram_id, 100500)
        self.assertEqual(stored_account.username, "linked_telegram")

        consumed_token = await self._get_link_token(body["link_token"])
        self.assertIsNotNone(consumed_token)
        assert consumed_token is not None
        self.assertIsNotNone(consumed_token.consumed_at)

        reused_response = await self.client.post(
            "/api/v1/accounts/link-telegram-confirm",
            json={
                "link_token": body["link_token"],
                "telegram_id": 100500,
            },
        )
        self.assertEqual(reused_response.status_code, 400)
        self.assertEqual(
            reused_response.json()["detail"],
            translate("api.linking.errors.token_already_used"),
        )
        self.assertEqual(reused_response.json()["error_code"], "token_already_used")

    async def test_browser_to_telegram_merges_existing_telegram_account(self) -> None:
        browser_account = await self._create_account(
            email="browser@example.com",
            display_name="Browser User",
            balance=11,
            referral_earnings=4,
        )
        telegram_account = await self._create_account(
            telegram_id=200200,
            first_name="Existing Telegram",
            balance=9,
            referral_earnings=6,
            referrals_count=3,
        )
        await self._create_auth_account(
            account_id=telegram_account.id,
            provider=AuthProvider.SUPABASE,
            provider_uid="telegram-existing",
        )
        pending_withdrawal = await self._create_withdrawal(
            account_id=telegram_account.id, amount=5
        )

        self._current_account_id = browser_account.id
        token_response = await self.client.post("/api/v1/accounts/link-telegram")
        self.assertEqual(token_response.status_code, 200)
        link_token = token_response.json()["link_token"]

        confirm_response = await self.client.post(
            "/api/v1/accounts/link-telegram-confirm",
            json={
                "link_token": link_token,
                "telegram_id": 200200,
                "username": "merged_account",
                "first_name": "Merged",
            },
        )
        self.assertEqual(confirm_response.status_code, 200)
        confirm_body = confirm_response.json()
        self.assertEqual(confirm_body["id"], str(browser_account.id))
        self.assertEqual(confirm_body["balance"], 20)
        self.assertEqual(confirm_body["referral_earnings"], 10)
        self.assertEqual(confirm_body["referrals_count"], 3)

        merged_account = await self._get_account(browser_account.id)
        self.assertIsNotNone(merged_account)
        assert merged_account is not None
        self.assertEqual(merged_account.balance, 20)
        self.assertEqual(merged_account.referral_earnings, 10)
        self.assertEqual(merged_account.referrals_count, 3)
        self.assertEqual(merged_account.telegram_id, 200200)

        removed_source_account = await self._get_account(telegram_account.id)
        self.assertIsNone(removed_source_account)

        auth_accounts = await self._get_auth_accounts(browser_account.id)
        self.assertEqual(len(auth_accounts), 1)
        self.assertEqual(auth_accounts[0].provider_uid, "telegram-existing")

        moved_withdrawal = await self._get_withdrawal(pending_withdrawal.id)
        self.assertIsNotNone(moved_withdrawal)
        assert moved_withdrawal is not None
        self.assertEqual(moved_withdrawal.account_id, browser_account.id)

    async def test_merge_accounts_moves_business_records_and_resolves_duplicates(
        self,
    ) -> None:
        now = datetime(2026, 3, 15, 12, 0)
        browser_account = await self._create_account(
            email="browser@example.com",
            display_name="Browser User",
            balance=11,
            referral_earnings=4,
        )
        telegram_account = await self._create_account(
            telegram_id=200200,
            first_name="Existing Telegram",
            balance=9,
            referral_earnings=6,
            referrals_count=3,
        )
        await self._create_auth_account(
            account_id=telegram_account.id,
            provider=AuthProvider.SUPABASE,
            provider_uid="telegram-existing",
        )
        pending_withdrawal = await self._create_withdrawal(
            account_id=telegram_account.id, amount=5
        )

        async with self._session_factory() as session:
            payment = Payment(
                account_id=telegram_account.id,
                provider=PaymentProvider.YOOKASSA,
                flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                status=PaymentStatus.SUCCEEDED,
                amount=990,
                currency="RUB",
                provider_payment_id="merge-pay-src-1",
                external_reference="merge-pay-src-1",
                plan_code="plan_1m",
                description="merge payment",
                raw_payload={"payment": "src"},
            )
            session.add(payment)
            await session.flush()

            payment_event = PaymentEvent(
                payment_id=payment.id,
                account_id=telegram_account.id,
                provider=PaymentProvider.YOOKASSA,
                flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                status=PaymentStatus.SUCCEEDED,
                provider_event_id="merge-evt-src-1",
                provider_payment_id="merge-pay-src-1",
                amount=990,
                currency="RUB",
                raw_payload={"event": "src"},
                processed_at=now,
            )
            subscription_grant = SubscriptionGrant(
                account_id=telegram_account.id,
                payment_id=payment.id,
                purchase_source="direct_payment",
                reference_type="payment",
                reference_id="merge-pay-src-1",
                plan_code="plan_1m",
                amount=990,
                currency="RUB",
                duration_days=30,
                base_expires_at=now,
                target_expires_at=datetime(2026, 4, 14, 12, 0),
                applied_at=now,
            )
            target_notification = Notification(
                account_id=browser_account.id,
                type=NotificationType.PAYMENT_SUCCEEDED,
                title="Target notification",
                body="target",
                priority=NotificationPriority.SUCCESS,
                dedupe_key="payment-merge-dup",
            )
            source_notification = Notification(
                account_id=telegram_account.id,
                type=NotificationType.PAYMENT_SUCCEEDED,
                title="Source notification",
                body="source",
                priority=NotificationPriority.SUCCESS,
                dedupe_key="payment-merge-dup",
            )
            session.add_all(
                [
                    payment_event,
                    subscription_grant,
                    target_notification,
                    source_notification,
                ]
            )
            await session.flush()

            target_notification_delivery = NotificationDelivery(
                notification_id=target_notification.id,
                channel=NotificationChannel.IN_APP,
                status=NotificationDeliveryStatus.DELIVERED,
                attempts_count=1,
                last_attempt_at=now,
                delivered_at=now,
            )
            source_notification_delivery = NotificationDelivery(
                notification_id=source_notification.id,
                channel=NotificationChannel.TELEGRAM,
                status=NotificationDeliveryStatus.PENDING,
                attempts_count=0,
            )

            broadcast = Broadcast(
                name="Merge broadcast",
                title="Merge",
                body_html="<b>merge</b>",
                content_type=BroadcastContentType.TEXT,
                channels=[BroadcastChannel.TELEGRAM.value],
                buttons=[],
                audience={},
                status=BroadcastStatus.COMPLETED,
                estimated_total_accounts=2,
                estimated_in_app_recipients=0,
                estimated_telegram_recipients=2,
                created_by_admin_id=uuid.uuid4(),
                updated_by_admin_id=uuid.uuid4(),
                launched_at=now,
                completed_at=now,
            )
            session.add(broadcast)
            await session.flush()

            broadcast_run = BroadcastRun(
                broadcast_id=broadcast.id,
                run_type=BroadcastRunType.SEND_NOW,
                status=BroadcastRunStatus.COMPLETED,
                triggered_by_admin_id=uuid.uuid4(),
                snapshot_total_accounts=2,
                snapshot_in_app_targets=0,
                snapshot_telegram_targets=2,
                started_at=now,
                completed_at=now,
            )
            session.add(broadcast_run)
            await session.flush()

            target_delivery = BroadcastDelivery(
                run_id=broadcast_run.id,
                broadcast_id=broadcast.id,
                account_id=browser_account.id,
                channel=BroadcastChannel.TELEGRAM,
                status=BroadcastDeliveryStatus.FAILED,
                attempts_count=1,
                last_attempt_at=now,
                error_code="timeout",
                error_message="timeout",
            )
            source_delivery = BroadcastDelivery(
                run_id=broadcast_run.id,
                broadcast_id=broadcast.id,
                account_id=telegram_account.id,
                channel=BroadcastChannel.TELEGRAM,
                status=BroadcastDeliveryStatus.DELIVERED,
                provider_message_id="message-1",
                notification_id=source_notification.id,
                attempts_count=2,
                last_attempt_at=now,
                delivered_at=now,
            )
            referral_intent = TelegramReferralIntent(
                telegram_id=telegram_account.telegram_id,
                referral_code="merge-ref-code",
                status="applied",
                account_id=telegram_account.id,
                consumed_at=now,
            )
            admin_action_log = AdminActionLog(
                admin_id=uuid.uuid4(),
                action_type=AdminActionType.SUBSCRIPTION_GRANT,
                target_account_id=telegram_account.id,
                payload={"origin": "merge-test"},
            )

            session.add_all(
                [
                    target_notification_delivery,
                    source_notification_delivery,
                    target_delivery,
                    source_delivery,
                    referral_intent,
                    admin_action_log,
                ]
            )
            await session.commit()

        merged_account = await self._merge_accounts_direct(
            source_account_id=telegram_account.id,
            target_account_id=browser_account.id,
        )
        self.assertEqual(merged_account.id, browser_account.id)
        self.assertEqual(merged_account.balance, 20)
        self.assertEqual(merged_account.referral_earnings, 10)
        self.assertEqual(merged_account.referrals_count, 3)
        self.assertEqual(merged_account.telegram_id, 200200)

        async with self._session_factory() as session:
            self.assertIsNone(await session.get(Account, telegram_account.id))

            moved_payment = await session.scalar(
                select(Payment).where(Payment.provider_payment_id == "merge-pay-src-1")
            )
            self.assertIsNotNone(moved_payment)
            assert moved_payment is not None
            self.assertEqual(moved_payment.account_id, browser_account.id)

            moved_event = await session.scalar(
                select(PaymentEvent).where(
                    PaymentEvent.provider_event_id == "merge-evt-src-1"
                )
            )
            self.assertIsNotNone(moved_event)
            assert moved_event is not None
            self.assertEqual(moved_event.account_id, browser_account.id)

            moved_grant = await session.scalar(
                select(SubscriptionGrant).where(
                    SubscriptionGrant.reference_id == "merge-pay-src-1"
                )
            )
            self.assertIsNotNone(moved_grant)
            assert moved_grant is not None
            self.assertEqual(moved_grant.account_id, browser_account.id)

            moved_withdrawal = await session.get(Withdrawal, pending_withdrawal.id)
            self.assertIsNotNone(moved_withdrawal)
            assert moved_withdrawal is not None
            self.assertEqual(moved_withdrawal.account_id, browser_account.id)

            notifications = list(
                (
                    await session.execute(
                        select(Notification)
                        .where(Notification.account_id == browser_account.id)
                        .order_by(Notification.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            self.assertEqual(len(notifications), 2)
            self.assertEqual(
                sum(
                    1
                    for notification in notifications
                    if notification.dedupe_key == "payment-merge-dup"
                ),
                1,
            )
            self.assertEqual(
                sum(
                    1
                    for notification in notifications
                    if notification.dedupe_key is None
                ),
                1,
            )

            deliveries = list(
                (
                    await session.execute(
                        select(BroadcastDelivery)
                        .where(BroadcastDelivery.account_id == browser_account.id)
                        .order_by(BroadcastDelivery.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            self.assertEqual(len(deliveries), 1)
            self.assertEqual(deliveries[0].status, BroadcastDeliveryStatus.DELIVERED)
            self.assertEqual(deliveries[0].provider_message_id, "message-1")
            self.assertEqual(deliveries[0].notification_id, source_notification.id)

            moved_referral_intent = await session.scalar(
                select(TelegramReferralIntent).where(
                    TelegramReferralIntent.referral_code == "merge-ref-code"
                )
            )
            self.assertIsNotNone(moved_referral_intent)
            assert moved_referral_intent is not None
            self.assertEqual(moved_referral_intent.account_id, browser_account.id)

            admin_logs = list(
                (await session.execute(select(AdminActionLog))).scalars().all()
            )
            self.assertEqual(len(admin_logs), 1)
            self.assertEqual(admin_logs[0].payload, {"origin": "merge-test"})
            self.assertEqual(admin_logs[0].target_account_id, browser_account.id)

    async def test_merge_accounts_keeps_remote_user_with_latest_online_at(self) -> None:
        browser_remote_uuid = uuid.uuid4()
        telegram_remote_uuid = uuid.uuid4()
        browser_account = await self._create_account(
            email="browser-online@example.com",
            display_name="Browser User",
            remnawave_user_uuid=browser_remote_uuid,
            subscription_url="https://panel.test/sub/browser-online",
            subscription_status="ACTIVE",
            subscription_expires_at=datetime(2026, 6, 10, 12, 0),
            subscription_last_synced_at=datetime(2026, 3, 15, 10, 0),
        )
        telegram_account = await self._create_account(
            telegram_id=777111,
            first_name="Telegram User",
            remnawave_user_uuid=telegram_remote_uuid,
            subscription_url="https://panel.test/sub/telegram-online",
            subscription_status="ACTIVE",
            subscription_expires_at=datetime(2026, 5, 10, 12, 0),
            subscription_last_synced_at=datetime(2026, 3, 15, 11, 0),
        )

        self._fake_gateway.users[browser_remote_uuid] = RemnawaveUser(
            uuid=browser_remote_uuid,
            username=f"acc_{browser_remote_uuid.hex}",
            status="ACTIVE",
            expire_at=datetime(2026, 6, 10, 12, 0),
            subscription_url="https://panel.test/sub/browser-online",
            telegram_id=None,
            email=browser_account.email,
            tag=None,
            online_at=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        )
        self._fake_gateway.users[telegram_remote_uuid] = RemnawaveUser(
            uuid=telegram_remote_uuid,
            username=f"acc_{telegram_remote_uuid.hex}",
            status="ACTIVE",
            expire_at=datetime(2026, 5, 10, 12, 0),
            subscription_url="https://panel.test/sub/telegram-online",
            telegram_id=telegram_account.telegram_id,
            email=None,
            tag=None,
            online_at=datetime(2026, 4, 2, 9, 0, tzinfo=UTC),
        )

        merged_account = await self._merge_accounts_direct(
            source_account_id=telegram_account.id,
            target_account_id=browser_account.id,
        )

        self.assertEqual(merged_account.remnawave_user_uuid, telegram_remote_uuid)
        self.assertEqual(
            merged_account.subscription_url,
            f"https://panel.test/sub/{telegram_remote_uuid.hex[:8]}",
        )
        self.assertEqual(
            merged_account.subscription_expires_at,
            datetime(2026, 6, 10, 12, 0),
        )
        self.assertEqual(self._fake_gateway.deleted_user_ids, [browser_remote_uuid])
        self.assertNotIn(browser_remote_uuid, self._fake_gateway.users)

        kept_remote_user = self._fake_gateway.users[telegram_remote_uuid]
        self.assertEqual(
            kept_remote_user.expire_at,
            datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        )
        self.assertEqual(kept_remote_user.email, browser_account.email)
        self.assertEqual(kept_remote_user.telegram_id, telegram_account.telegram_id)

        event_logs = await self._get_account_event_logs(browser_account.id)
        merge_events = [
            item for item in event_logs if item.event_type == "account.merge.completed"
        ]
        self.assertEqual(len(merge_events), 1)
        self.assertEqual(
            merge_events[0].payload["remnawave_reconcile"]["selection_reason"],
            "latest_online_at",
        )
        self.assertEqual(
            merge_events[0].payload["remnawave_reconcile"]["kept_user_uuid"],
            str(telegram_remote_uuid),
        )

    async def test_merge_accounts_keeps_remote_user_with_latest_first_connected_at(
        self,
    ) -> None:
        browser_remote_uuid = uuid.uuid4()
        telegram_remote_uuid = uuid.uuid4()
        browser_account = await self._create_account(
            email="browser-first-connected@example.com",
            remnawave_user_uuid=browser_remote_uuid,
            subscription_url="https://panel.test/sub/browser-first",
            subscription_status="ACTIVE",
            subscription_expires_at=datetime(2026, 4, 10, 12, 0),
        )
        telegram_account = await self._create_account(
            telegram_id=777112,
            remnawave_user_uuid=telegram_remote_uuid,
            subscription_url="https://panel.test/sub/telegram-first",
            subscription_status="ACTIVE",
            subscription_expires_at=datetime(2026, 4, 15, 12, 0),
        )

        self._fake_gateway.users[browser_remote_uuid] = RemnawaveUser(
            uuid=browser_remote_uuid,
            username=f"acc_{browser_remote_uuid.hex}",
            status="ACTIVE",
            expire_at=datetime(2026, 4, 10, 12, 0),
            subscription_url="https://panel.test/sub/browser-first",
            telegram_id=None,
            email=browser_account.email,
            tag=None,
            first_connected_at=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
        )
        self._fake_gateway.users[telegram_remote_uuid] = RemnawaveUser(
            uuid=telegram_remote_uuid,
            username=f"acc_{telegram_remote_uuid.hex}",
            status="ACTIVE",
            expire_at=datetime(2026, 4, 15, 12, 0),
            subscription_url="https://panel.test/sub/telegram-first",
            telegram_id=telegram_account.telegram_id,
            email=None,
            tag=None,
            first_connected_at=datetime(2026, 3, 12, 12, 0, tzinfo=UTC),
        )

        merged_account = await self._merge_accounts_direct(
            source_account_id=telegram_account.id,
            target_account_id=browser_account.id,
        )

        self.assertEqual(merged_account.remnawave_user_uuid, telegram_remote_uuid)
        event_logs = await self._get_account_event_logs(browser_account.id)
        merge_events = [
            item for item in event_logs if item.event_type == "account.merge.completed"
        ]
        self.assertEqual(len(merge_events), 1)
        self.assertEqual(
            merge_events[0].payload["remnawave_reconcile"]["selection_reason"],
            "latest_first_connected_at",
        )

    async def test_merge_accounts_prefers_paid_remote_over_trial_without_usage_signals(
        self,
    ) -> None:
        browser_remote_uuid = uuid.uuid4()
        telegram_remote_uuid = uuid.uuid4()
        browser_account = await self._create_account(
            email="browser-trial@example.com",
            remnawave_user_uuid=browser_remote_uuid,
            subscription_url="https://panel.test/sub/browser-trial",
            subscription_status="ACTIVE",
            subscription_expires_at=datetime(2026, 4, 10, 12, 0),
            subscription_is_trial=True,
        )
        telegram_account = await self._create_account(
            telegram_id=777113,
            remnawave_user_uuid=telegram_remote_uuid,
            subscription_url="https://panel.test/sub/telegram-paid",
            subscription_status="ACTIVE",
            subscription_expires_at=datetime(2026, 4, 5, 12, 0),
            subscription_is_trial=False,
        )

        self._fake_gateway.users[browser_remote_uuid] = RemnawaveUser(
            uuid=browser_remote_uuid,
            username=f"acc_{browser_remote_uuid.hex}",
            status="ACTIVE",
            expire_at=datetime(2026, 4, 10, 12, 0),
            subscription_url="https://panel.test/sub/browser-trial",
            telegram_id=None,
            email=browser_account.email,
            tag="TRIAL",
        )
        self._fake_gateway.users[telegram_remote_uuid] = RemnawaveUser(
            uuid=telegram_remote_uuid,
            username=f"acc_{telegram_remote_uuid.hex}",
            status="ACTIVE",
            expire_at=datetime(2026, 4, 5, 12, 0),
            subscription_url="https://panel.test/sub/telegram-paid",
            telegram_id=telegram_account.telegram_id,
            email=None,
            tag=None,
        )

        merged_account = await self._merge_accounts_direct(
            source_account_id=telegram_account.id,
            target_account_id=browser_account.id,
        )

        self.assertEqual(merged_account.remnawave_user_uuid, telegram_remote_uuid)
        self.assertFalse(merged_account.subscription_is_trial)
        event_logs = await self._get_account_event_logs(browser_account.id)
        merge_events = [
            item for item in event_logs if item.event_type == "account.merge.completed"
        ]
        self.assertEqual(len(merge_events), 1)
        self.assertEqual(
            merge_events[0].payload["remnawave_reconcile"]["selection_reason"],
            "paid_over_trial",
        )

    async def test_merge_accounts_reconciles_existing_remnawave_users(self) -> None:
        browser_remote_uuid = uuid.uuid4()
        telegram_remote_uuid = uuid.uuid4()
        browser_account = await self._create_account(
            email="browser@example.com",
            display_name="Browser User",
            remnawave_user_uuid=browser_remote_uuid,
            subscription_url="https://panel.test/sub/browser",
            subscription_status="ACTIVE",
            subscription_expires_at=datetime(2026, 4, 10, 12, 0),
            subscription_last_synced_at=datetime(2026, 3, 15, 10, 0),
        )
        telegram_account = await self._create_account(
            telegram_id=777001,
            first_name="Telegram User",
            remnawave_user_uuid=telegram_remote_uuid,
            subscription_url="https://panel.test/sub/telegram",
            subscription_status="ACTIVE",
            subscription_expires_at=datetime(2026, 5, 10, 12, 0),
            subscription_last_synced_at=datetime(2026, 3, 15, 11, 0),
        )

        self._fake_gateway.users[browser_remote_uuid] = RemnawaveUser(
            uuid=browser_remote_uuid,
            username=f"acc_{browser_remote_uuid.hex}",
            status="ACTIVE",
            expire_at=datetime(2026, 4, 10, 12, 0),
            subscription_url="https://panel.test/sub/browser",
            telegram_id=None,
            email=browser_account.email,
            tag=None,
        )
        self._fake_gateway.users[telegram_remote_uuid] = RemnawaveUser(
            uuid=telegram_remote_uuid,
            username=f"acc_{telegram_remote_uuid.hex}",
            status="ACTIVE",
            expire_at=datetime(2026, 5, 10, 12, 0),
            subscription_url="https://panel.test/sub/telegram",
            telegram_id=telegram_account.telegram_id,
            email=None,
            tag=None,
        )

        merged_account = await self._merge_accounts_direct(
            source_account_id=telegram_account.id,
            target_account_id=browser_account.id,
        )

        self.assertEqual(merged_account.remnawave_user_uuid, telegram_remote_uuid)
        self.assertEqual(
            merged_account.subscription_url,
            f"https://panel.test/sub/{telegram_remote_uuid.hex[:8]}",
        )
        self.assertEqual(
            merged_account.subscription_expires_at,
            datetime(2026, 5, 10, 12, 0),
        )
        self.assertEqual(merged_account.telegram_id, telegram_account.telegram_id)
        self.assertEqual(self._fake_gateway.deleted_user_ids, [browser_remote_uuid])
        self.assertNotIn(browser_remote_uuid, self._fake_gateway.users)

        kept_remote_user = self._fake_gateway.users[telegram_remote_uuid]
        self.assertEqual(
            kept_remote_user.expire_at,
            datetime(2026, 5, 10, 12, 0, tzinfo=UTC),
        )
        self.assertEqual(kept_remote_user.email, browser_account.email)
        self.assertEqual(kept_remote_user.telegram_id, telegram_account.telegram_id)

        event_logs = await self._get_account_event_logs(browser_account.id)
        merge_events = [
            item for item in event_logs if item.event_type == "account.merge.completed"
        ]
        self.assertEqual(len(merge_events), 1)
        self.assertEqual(
            merge_events[0].payload["remnawave_reconcile"]["selection_reason"],
            "latest_expires_at",
        )

        removed_source_account = await self._get_account(telegram_account.id)
        self.assertIsNone(removed_source_account)

    async def test_telegram_to_browser_flow_and_token_reuse(self) -> None:
        telegram_account = await self._create_account(
            telegram_id=300300,
            username="telegram_owner",
            first_name="Telegram",
            balance=12,
            referral_earnings=5,
            referrals_count=2,
        )
        browser_account = await self._create_account(
            email="browser@example.com",
            display_name="Browser User",
            balance=8,
            referral_earnings=1,
        )
        await self._create_auth_account(
            account_id=browser_account.id,
            provider=AuthProvider.SUPABASE,
            provider_uid="browser-user-1",
            email="browser@example.com",
        )

        self._current_account_id = telegram_account.id
        token_response = await self.client.post("/api/v1/accounts/link-browser")
        self.assertEqual(token_response.status_code, 200)
        token_body = token_response.json()
        self.assertIn("link_flow=browser", token_body["link_url"])
        self.assertTrue(token_body["link_token"].endswith("_BROWSER"))

        link_token = await self._get_link_token(token_body["link_token"])
        self.assertIsNotNone(link_token)
        assert link_token is not None
        self.assertEqual(link_token.link_type, LinkType.BROWSER_FROM_TELEGRAM)

        self._current_account_id = browser_account.id
        complete_response = await self.client.post(
            "/api/v1/accounts/link-browser-complete",
            headers={"Authorization": "Bearer browser-session-token"},
            json={"link_token": token_body["link_token"]},
        )
        self.assertEqual(complete_response.status_code, 200)
        complete_body = complete_response.json()
        self.assertEqual(complete_body["id"], str(telegram_account.id))
        self.assertEqual(complete_body["balance"], 20)
        self.assertEqual(complete_body["referral_earnings"], 6)
        self.assertEqual(complete_body["referrals_count"], 2)
        self.assertEqual(complete_body["last_login_source"], "browser_oauth")

        merged_telegram_account = await self._get_account(telegram_account.id)
        self.assertIsNotNone(merged_telegram_account)
        assert merged_telegram_account is not None
        self.assertEqual(merged_telegram_account.balance, 20)
        self.assertEqual(merged_telegram_account.referral_earnings, 6)

        removed_browser_account = await self._get_account(browser_account.id)
        self.assertIsNone(removed_browser_account)

        moved_auth_accounts = await self._get_auth_accounts(telegram_account.id)
        self.assertEqual(len(moved_auth_accounts), 1)
        self.assertEqual(moved_auth_accounts[0].provider_uid, "browser-user-1")

        consumed_token = await self._get_link_token(token_body["link_token"])
        self.assertIsNotNone(consumed_token)
        assert consumed_token is not None
        self.assertIsNotNone(consumed_token.consumed_at)

        self._current_account_id = telegram_account.id
        reused_response = await self.client.post(
            "/api/v1/accounts/link-browser-complete",
            headers={"Authorization": "Bearer browser-session-token"},
            json={"link_token": token_body["link_token"]},
        )
        self.assertEqual(reused_response.status_code, 400)
        self.assertEqual(
            reused_response.json()["detail"],
            translate("api.linking.errors.token_already_used"),
        )
        self.assertEqual(reused_response.json()["error_code"], "token_already_used")

    async def test_expired_link_token_is_rejected(self) -> None:
        browser_account = await self._create_account(email="browser@example.com")

        async with self._session_factory() as session:
            link_token, _ = await create_telegram_link_token(
                session,
                account_id=browser_account.id,
                ttl_seconds=-1,
            )
            await session.commit()

        expired_response = await self.client.post(
            "/api/v1/accounts/link-telegram-confirm",
            json={
                "link_token": link_token,
                "telegram_id": 404404,
            },
        )
        self.assertEqual(expired_response.status_code, 400)
        self.assertEqual(
            expired_response.json()["detail"],
            translate("api.linking.errors.token_expired"),
        )


if __name__ == "__main__":
    unittest.main()
