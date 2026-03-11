import unittest
import uuid
from datetime import UTC, datetime, timedelta

from app.db.models import Account
from app.integrations.remnawave.client import RemnawaveUser
from app.services.purchases import (
    PurchaseSource,
    apply_paid_purchase,
    apply_trial_purchase,
    compute_paid_plan_window,
)


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def provision_user(
        self,
        *,
        user_uuid: uuid.UUID,
        expire_at: datetime,
        email: str | None,
        telegram_id: int | None,
        is_trial: bool,
    ) -> RemnawaveUser:
        self.calls.append(
            {
                "user_uuid": user_uuid,
                "expire_at": expire_at,
                "email": email,
                "telegram_id": telegram_id,
                "is_trial": is_trial,
            }
        )
        return RemnawaveUser(
            uuid=user_uuid,
            username=f"acc_{user_uuid.hex}",
            status="ACTIVE",
            expire_at=expire_at,
            subscription_url=f"https://panel.test/sub/{user_uuid.hex[:8]}",
            telegram_id=telegram_id,
            email=email,
            tag="TRIAL" if is_trial else None,
        )


class PurchaseServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_apply_trial_purchase_marks_trial_snapshot(self) -> None:
        gateway = FakeGateway()
        now = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)
        account = Account(id=uuid.uuid4(), email="trial@example.com", telegram_id=1001)

        result = await apply_trial_purchase(
            account,
            trial_duration_days=3,
            now=now,
            gateway_factory=lambda: gateway,
        )

        self.assertEqual(result.source, PurchaseSource.TRIAL)
        self.assertEqual(result.target_expires_at, now + timedelta(days=3))
        self.assertEqual(account.subscription_status, "ACTIVE")
        self.assertTrue(account.subscription_is_trial)
        self.assertEqual(account.trial_used_at, now)
        self.assertEqual(account.trial_ends_at, now + timedelta(days=3))
        self.assertEqual(account.remnawave_user_uuid, account.id)
        self.assertEqual(gateway.calls[0]["is_trial"], True)

    async def test_apply_paid_purchase_clears_active_trial_flag_but_keeps_history(self) -> None:
        gateway = FakeGateway()
        purchased_at = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)
        target_expires_at = purchased_at + timedelta(days=30)
        account = Account(
            id=uuid.uuid4(),
            email="paid@example.com",
            trial_used_at=purchased_at - timedelta(days=2),
            trial_ends_at=purchased_at + timedelta(days=1),
            subscription_is_trial=True,
        )

        result = await apply_paid_purchase(
            account,
            source=PurchaseSource.DIRECT_PAYMENT,
            target_expires_at=target_expires_at,
            gateway_factory=lambda: gateway,
        )

        self.assertEqual(result.source, PurchaseSource.DIRECT_PAYMENT)
        self.assertEqual(result.target_expires_at, target_expires_at)
        self.assertEqual(account.subscription_status, "ACTIVE")
        self.assertFalse(account.subscription_is_trial)
        self.assertEqual(account.trial_used_at, purchased_at - timedelta(days=2))
        self.assertEqual(account.trial_ends_at, purchased_at + timedelta(days=1))
        self.assertEqual(gateway.calls[0]["is_trial"], False)

    def test_compute_paid_plan_window_extends_from_active_subscription(self) -> None:
        now = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)
        current_expires_at = now + timedelta(days=5)
        account = Account(
            id=uuid.uuid4(),
            subscription_expires_at=current_expires_at,
        )

        base_expires_at, target_expires_at = compute_paid_plan_window(
            account,
            duration_days=30,
            now=now,
        )

        self.assertEqual(base_expires_at, current_expires_at)
        self.assertEqual(target_expires_at, current_expires_at + timedelta(days=30))

    def test_compute_paid_plan_window_uses_now_for_expired_subscription(self) -> None:
        now = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)
        account = Account(
            id=uuid.uuid4(),
            subscription_expires_at=now - timedelta(days=1),
        )

        base_expires_at, target_expires_at = compute_paid_plan_window(
            account,
            duration_days=30,
            now=now,
        )

        self.assertEqual(base_expires_at, now)
        self.assertEqual(target_expires_at, now + timedelta(days=30))


if __name__ == "__main__":
    unittest.main()
