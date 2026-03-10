from datetime import datetime, timezone

from pydantic import BaseModel

from app.db.models import Account, AccountStatus
from app.schemas.account import AccountResponse
from app.schemas.subscription import SubscriptionStateResponse


class TrialBootstrapResponse(BaseModel):
    can_start_now: bool
    reason: str | None = None
    has_used_trial: bool = False
    checked_at: datetime
    strict_check_required_on_start: bool = True

    @classmethod
    def from_account(cls, account: Account) -> "TrialBootstrapResponse":
        reason: str | None = None
        can_start_now = True
        subscription = SubscriptionStateResponse.from_account(account)

        if account.status == AccountStatus.BLOCKED:
            can_start_now = False
            reason = "account_blocked"
        elif account.has_used_trial:
            can_start_now = False
            reason = "trial_already_used"
        elif (
            subscription.is_active
            or account.subscription_url is not None
            or account.subscription_expires_at is not None
            or account.subscription_status is not None
            or account.remnawave_user_uuid is not None
        ):
            can_start_now = False
            reason = "subscription_exists"

        return cls(
            can_start_now=can_start_now,
            reason=reason,
            has_used_trial=account.has_used_trial,
            checked_at=datetime.now(timezone.utc),
        )


class BootstrapResponse(BaseModel):
    account: AccountResponse
    subscription: SubscriptionStateResponse
    trial_ui: TrialBootstrapResponse

    @classmethod
    def from_account(cls, account: Account) -> "BootstrapResponse":
        return cls(
            account=AccountResponse.model_validate(account),
            subscription=SubscriptionStateResponse.from_account(account),
            trial_ui=TrialBootstrapResponse.from_account(account),
        )
