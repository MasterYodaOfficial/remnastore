from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Account, AccountStatus
from app.integrations.remnawave import (
    RemnawaveConfigurationError,
    RemnawaveRequestError,
    RemnawaveUser,
    get_remnawave_gateway,
)
from app.schemas.subscription import SubscriptionStateResponse, TrialEligibilityResponse
from app.services.cache import get_cache


class SubscriptionServiceError(Exception):
    pass


class TrialEligibilityError(SubscriptionServiceError):
    def __init__(self, reason: str, *, status_code: int = 400):
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


class RemnawaveSyncError(SubscriptionServiceError):
    pass


@dataclass(slots=True)
class TrialEligibility:
    eligible: bool
    reason: Optional[str] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _target_remnawave_user_uuid(account: Account) -> UUID:
    return account.remnawave_user_uuid or account.id


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def _clear_account_cache(account_id: UUID) -> None:
    cache = get_cache()
    await cache.delete(cache.account_response_key(str(account_id)))


async def _load_managed_account(session: AsyncSession, account_id: UUID) -> Account:
    result = await session.execute(
        select(Account).where(Account.id == account_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise SubscriptionServiceError(f"Account not found: {account_id}")
    return account


async def _load_account_by_remnawave_user_uuid(
    session: AsyncSession,
    remnawave_user_uuid: UUID,
) -> Account | None:
    result = await session.execute(
        select(Account)
        .where(
            or_(
                Account.remnawave_user_uuid == remnawave_user_uuid,
                Account.id == remnawave_user_uuid,
            )
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


def _apply_remote_user(account: Account, remote_user: RemnawaveUser) -> None:
    account.remnawave_user_uuid = remote_user.uuid
    account.subscription_url = remote_user.subscription_url
    account.subscription_status = remote_user.status
    account.subscription_expires_at = _normalize_datetime(remote_user.expire_at)
    account.subscription_last_synced_at = _utcnow()
    account.subscription_is_trial = remote_user.tag == "TRIAL"
    account.email = account.email or remote_user.email
    account.telegram_id = account.telegram_id or remote_user.telegram_id


def _clear_remote_subscription_snapshot(account: Account) -> None:
    account.remnawave_user_uuid = None
    account.subscription_url = None
    account.subscription_status = None
    account.subscription_expires_at = None
    account.subscription_last_synced_at = _utcnow()
    account.subscription_is_trial = False


async def get_current_subscription(account: Account) -> SubscriptionStateResponse:
    return SubscriptionStateResponse.from_account(account)


async def _find_remnawave_identity_conflict(
    account: Account,
    gateway,
) -> RemnawaveUser | None:
    target_uuid = _target_remnawave_user_uuid(account)

    if account.email:
        users_with_email = await gateway.get_users_by_email(account.email)
        for remote_user in users_with_email:
            if remote_user.uuid != target_uuid:
                return remote_user

    if account.telegram_id is not None:
        users_with_telegram = await gateway.get_users_by_telegram_id(account.telegram_id)
        for remote_user in users_with_telegram:
            if remote_user.uuid != target_uuid:
                return remote_user

    return None


async def sync_current_subscription(
    session: AsyncSession,
    *,
    account: Account,
) -> SubscriptionStateResponse:
    account = await _load_managed_account(session, account.id)

    try:
        gateway = get_remnawave_gateway()
    except RemnawaveConfigurationError as exc:
        raise RemnawaveSyncError(str(exc)) from exc

    try:
        remote_user = await gateway.get_user_by_uuid(_target_remnawave_user_uuid(account))
    except RemnawaveRequestError as exc:
        raise RemnawaveSyncError(str(exc)) from exc

    if remote_user is None:
        _clear_remote_subscription_snapshot(account)
    else:
        _apply_remote_user(account, remote_user)

    await session.commit()
    await session.refresh(account)
    await _clear_account_cache(account.id)
    return SubscriptionStateResponse.from_account(account)


async def get_trial_eligibility(
    session: AsyncSession,
    *,
    account: Account,
) -> TrialEligibilityResponse:
    account = await _load_managed_account(session, account.id)

    if account.status == AccountStatus.BLOCKED:
        eligibility = TrialEligibility(eligible=False, reason="account_blocked")
    elif account.trial_used_at is not None:
        eligibility = TrialEligibility(eligible=False, reason="trial_already_used")
    else:
        try:
            gateway = get_remnawave_gateway()
        except RemnawaveConfigurationError:
            eligibility = TrialEligibility(eligible=False, reason="remnawave_not_configured")
        else:
            try:
                remote_user = await gateway.get_user_by_uuid(_target_remnawave_user_uuid(account))
            except RemnawaveRequestError:
                eligibility = TrialEligibility(eligible=False, reason="remnawave_unavailable")
            else:
                if remote_user is not None:
                    _apply_remote_user(account, remote_user)
                    await session.commit()
                    await session.refresh(account)
                    await _clear_account_cache(account.id)
                    eligibility = TrialEligibility(eligible=False, reason="subscription_exists")
                else:
                    try:
                        identity_conflict = await _find_remnawave_identity_conflict(account, gateway)
                    except RemnawaveRequestError:
                        eligibility = TrialEligibility(
                            eligible=False,
                            reason="remnawave_unavailable",
                        )
                    else:
                        if identity_conflict is not None:
                            eligibility = TrialEligibility(
                                eligible=False,
                                reason="remnawave_identity_conflict",
                            )
                        elif account.subscription_url or account.subscription_expires_at is not None:
                            eligibility = TrialEligibility(
                                eligible=False,
                                reason="subscription_exists",
                            )
                        else:
                            eligibility = TrialEligibility(eligible=True)

    return TrialEligibilityResponse(
        eligible=eligibility.eligible,
        reason=eligibility.reason,
        has_used_trial=account.has_used_trial,
        subscription_status=account.subscription_status,
        subscription_expires_at=account.subscription_expires_at,
        remnawave_user_uuid=account.remnawave_user_uuid,
    )


async def activate_trial(
    session: AsyncSession,
    *,
    account: Account,
) -> SubscriptionStateResponse:
    account = await _load_managed_account(session, account.id)
    eligibility = await get_trial_eligibility(session, account=account)
    if not eligibility.eligible:
        status_code = 400
        if eligibility.reason == "account_blocked":
            status_code = 403
        elif eligibility.reason == "remnawave_unavailable":
            status_code = 502
        elif eligibility.reason == "remnawave_not_configured":
            status_code = 503
        raise TrialEligibilityError(eligibility.reason or "trial_not_eligible", status_code=status_code)

    try:
        gateway = get_remnawave_gateway()
    except RemnawaveConfigurationError as exc:
        raise RemnawaveSyncError(str(exc)) from exc

    now = _utcnow()
    trial_ends_at = now + timedelta(days=settings.trial_duration_days)

    try:
        remote_user = await gateway.provision_user(
            user_uuid=_target_remnawave_user_uuid(account),
            expire_at=trial_ends_at,
            email=account.email,
            telegram_id=account.telegram_id,
            is_trial=True,
        )
    except RemnawaveRequestError as exc:
        raise RemnawaveSyncError(str(exc)) from exc

    _apply_remote_user(account, remote_user)
    account.subscription_is_trial = True
    account.trial_used_at = now
    account.trial_ends_at = trial_ends_at

    await session.commit()
    await session.refresh(account)
    await _clear_account_cache(account.id)
    return SubscriptionStateResponse.from_account(account)


async def sync_subscription_by_remnawave_user_uuid(
    session: AsyncSession,
    *,
    remnawave_user_uuid: UUID,
) -> Account | None:
    account = await _load_account_by_remnawave_user_uuid(session, remnawave_user_uuid)
    if account is None:
        return None

    try:
        gateway = get_remnawave_gateway()
    except RemnawaveConfigurationError as exc:
        raise RemnawaveSyncError(str(exc)) from exc

    try:
        remote_user = await gateway.get_user_by_uuid(remnawave_user_uuid)
    except RemnawaveRequestError as exc:
        raise RemnawaveSyncError(str(exc)) from exc

    if remote_user is None:
        _clear_remote_subscription_snapshot(account)
    else:
        _apply_remote_user(account, remote_user)

    await session.commit()
    await session.refresh(account)
    await _clear_account_cache(account.id)
    return account
