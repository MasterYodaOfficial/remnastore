from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account
from app.db.models import LedgerEntryType, SubscriptionGrant
from app.integrations.remnawave import (
    RemnawaveConfigurationError,
    RemnawaveRequestError,
    RemnawaveUser,
    get_remnawave_gateway,
)
from app.services.ledger import InsufficientFundsError, apply_debit_in_transaction, clear_account_cache
from app.services.plans import SubscriptionPlan, get_subscription_plan
from app.services.referrals import apply_first_referral_reward_for_grant


class PurchaseSource(str, Enum):
    TRIAL = "trial"
    WALLET = "wallet"
    DIRECT_PAYMENT = "direct_payment"
    ADMIN = "admin"
    PROMO = "promo"


class PurchaseServiceError(Exception):
    pass


class RemnawaveSyncError(PurchaseServiceError):
    pass


class PurchaseConflictError(PurchaseServiceError):
    pass


class RemnawaveProvisionGateway(Protocol):
    async def provision_user(
        self,
        *,
        user_uuid: UUID,
        expire_at: datetime,
        email: str | None,
        telegram_id: int | None,
        is_trial: bool,
        hwid_device_limit: int | None = None,
    ) -> RemnawaveUser: ...


GatewayFactory = Callable[[], RemnawaveProvisionGateway]


@dataclass(slots=True)
class PurchaseResult:
    source: PurchaseSource
    target_expires_at: datetime
    remote_user: RemnawaveUser
    trial_used_at: datetime | None = None
    trial_ends_at: datetime | None = None


WALLET_PURCHASE_REFERENCE_TYPE = "wallet_purchase"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def target_remnawave_user_uuid(account: Account) -> UUID:
    return account.remnawave_user_uuid or account.id


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def compute_paid_plan_window(
    account: Account,
    *,
    duration_days: int,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    effective_now = now or utcnow()
    current_expires_at = normalize_datetime(account.subscription_expires_at)
    base_expires_at = effective_now
    if current_expires_at is not None and current_expires_at > effective_now:
        base_expires_at = current_expires_at
    return base_expires_at, base_expires_at + timedelta(days=duration_days)


def apply_remote_subscription_snapshot(account: Account, remote_user: RemnawaveUser) -> None:
    account.remnawave_user_uuid = remote_user.uuid
    account.subscription_url = remote_user.subscription_url
    account.subscription_status = remote_user.status
    account.subscription_expires_at = normalize_datetime(remote_user.expire_at)
    account.subscription_last_synced_at = utcnow()
    account.subscription_is_trial = remote_user.tag == "TRIAL"
    account.email = account.email or remote_user.email
    account.telegram_id = account.telegram_id or remote_user.telegram_id


def clear_remote_subscription_snapshot(account: Account) -> None:
    account.remnawave_user_uuid = None
    account.subscription_url = None
    account.subscription_status = None
    account.subscription_expires_at = None
    account.subscription_last_synced_at = utcnow()
    account.subscription_is_trial = False


def _resolve_gateway(
    gateway_factory: GatewayFactory | None,
) -> RemnawaveProvisionGateway:
    factory = gateway_factory or get_remnawave_gateway
    try:
        return factory()
    except RemnawaveConfigurationError as exc:
        raise RemnawaveSyncError(str(exc)) from exc


def _require_subscription_url(remote_user: RemnawaveUser) -> str:
    subscription_url = getattr(remote_user, "subscription_url", None)
    if isinstance(subscription_url, str):
        subscription_url = subscription_url.strip()

    if not subscription_url:
        raise RemnawaveSyncError("Remnawave did not return subscription_url")

    return subscription_url


async def _apply_subscription_purchase(
    account: Account,
    *,
    source: PurchaseSource,
    target_expires_at: datetime,
    is_trial: bool,
    trial_used_at: datetime | None = None,
    gateway_factory: GatewayFactory | None = None,
) -> PurchaseResult:
    gateway = _resolve_gateway(gateway_factory)

    try:
        remote_user = await gateway.provision_user(
            user_uuid=target_remnawave_user_uuid(account),
            expire_at=target_expires_at,
            email=account.email,
            telegram_id=account.telegram_id,
            is_trial=is_trial,
        )
    except RemnawaveRequestError as exc:
        raise RemnawaveSyncError(str(exc)) from exc

    remote_user.subscription_url = _require_subscription_url(remote_user)
    apply_remote_subscription_snapshot(account, remote_user)
    account.subscription_is_trial = is_trial

    resolved_trial_used_at = None
    resolved_trial_ends_at = None
    if is_trial:
        resolved_trial_used_at = trial_used_at or utcnow()
        resolved_trial_ends_at = target_expires_at
        account.trial_used_at = resolved_trial_used_at
        account.trial_ends_at = resolved_trial_ends_at

    return PurchaseResult(
        source=source,
        target_expires_at=target_expires_at,
        remote_user=remote_user,
        trial_used_at=resolved_trial_used_at,
        trial_ends_at=resolved_trial_ends_at,
    )


async def apply_trial_purchase(
    account: Account,
    *,
    trial_duration_days: int,
    now: datetime | None = None,
    gateway_factory: GatewayFactory | None = None,
) -> PurchaseResult:
    purchased_at = now or utcnow()
    target_expires_at = purchased_at + timedelta(days=trial_duration_days)
    return await _apply_subscription_purchase(
        account,
        source=PurchaseSource.TRIAL,
        target_expires_at=target_expires_at,
        is_trial=True,
        trial_used_at=purchased_at,
        gateway_factory=gateway_factory,
    )


async def apply_paid_purchase(
    account: Account,
    *,
    source: PurchaseSource,
    target_expires_at: datetime,
    gateway_factory: GatewayFactory | None = None,
) -> PurchaseResult:
    return await _apply_subscription_purchase(
        account,
        source=source,
        target_expires_at=target_expires_at,
        is_trial=False,
        gateway_factory=gateway_factory,
    )


async def load_purchase_account_for_update(
    session: AsyncSession,
    *,
    account_id: UUID,
) -> Account:
    result = await session.execute(select(Account).where(Account.id == account_id).with_for_update())
    account = result.scalar_one_or_none()
    if account is None:
        raise PurchaseServiceError(f"Account not found: {account_id}")
    return account


async def get_subscription_grant_by_reference(
    session: AsyncSession,
    *,
    purchase_source: PurchaseSource,
    reference_type: str,
    reference_id: str,
    for_update: bool = False,
) -> SubscriptionGrant | None:
    statement = select(SubscriptionGrant).where(
        SubscriptionGrant.purchase_source == purchase_source.value,
        SubscriptionGrant.reference_type == reference_type,
        SubscriptionGrant.reference_id == reference_id,
    )
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    return result.scalar_one_or_none()


def _normalize_required_reference_id(reference_id: str) -> str:
    normalized = reference_id.strip()
    if not normalized:
        raise PurchaseConflictError("idempotency_key is required")
    return normalized


def _validate_existing_wallet_grant(
    grant: SubscriptionGrant,
    *,
    account_id: UUID,
    plan_code: str,
    amount: int,
    duration_days: int,
) -> None:
    if grant.account_id != account_id:
        raise PurchaseConflictError("idempotency key already belongs to another account")
    if grant.plan_code != plan_code:
        raise PurchaseConflictError("idempotency key already used for another plan")
    if grant.amount != amount or grant.currency != "RUB":
        raise PurchaseConflictError("idempotency key already used for another purchase amount")
    if grant.duration_days != duration_days:
        raise PurchaseConflictError("idempotency key already used for another purchase duration")


async def stage_wallet_plan_purchase(
    session: AsyncSession,
    *,
    account_id: UUID,
    plan_code: str,
    idempotency_key: str,
    amount_override: int | None = None,
    duration_days_override: int | None = None,
) -> SubscriptionGrant:
    normalized_idempotency_key = _normalize_required_reference_id(idempotency_key)
    plan = get_subscription_plan(plan_code)
    amount = plan.price_rub if amount_override is None else amount_override
    duration_days = plan.duration_days if duration_days_override is None else duration_days_override
    if amount <= 0:
        raise PurchaseConflictError("wallet purchase amount must be positive")
    if duration_days <= 0:
        raise PurchaseConflictError("wallet purchase duration must be positive")

    existing_grant = await get_subscription_grant_by_reference(
        session,
        purchase_source=PurchaseSource.WALLET,
        reference_type=WALLET_PURCHASE_REFERENCE_TYPE,
        reference_id=normalized_idempotency_key,
        for_update=True,
    )
    if existing_grant is not None:
        _validate_existing_wallet_grant(
            existing_grant,
            account_id=account_id,
            plan_code=plan.code,
            amount=amount,
            duration_days=duration_days,
        )
        return existing_grant

    await apply_debit_in_transaction(
        session,
        account_id=account_id,
        amount=amount,
        entry_type=LedgerEntryType.SUBSCRIPTION_DEBIT,
        reference_type=WALLET_PURCHASE_REFERENCE_TYPE,
        reference_id=normalized_idempotency_key,
        comment=f"Wallet purchase of plan {plan.code}",
        idempotency_key=f"wallet_purchase:{normalized_idempotency_key}:debit",
    )
    account = await load_purchase_account_for_update(session, account_id=account_id)
    base_expires_at, target_expires_at = compute_paid_plan_window(
        account,
        duration_days=duration_days,
    )

    grant = SubscriptionGrant(
        account_id=account_id,
        payment_id=None,
        purchase_source=PurchaseSource.WALLET.value,
        reference_type=WALLET_PURCHASE_REFERENCE_TYPE,
        reference_id=normalized_idempotency_key,
        plan_code=plan.code,
        amount=amount,
        currency="RUB",
        duration_days=duration_days,
        base_expires_at=base_expires_at,
        target_expires_at=target_expires_at,
    )
    session.add(grant)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        existing_grant = await get_subscription_grant_by_reference(
            session,
            purchase_source=PurchaseSource.WALLET,
            reference_type=WALLET_PURCHASE_REFERENCE_TYPE,
            reference_id=normalized_idempotency_key,
            for_update=True,
        )
        if existing_grant is not None:
            _validate_existing_wallet_grant(
                existing_grant,
                account_id=account_id,
                plan_code=plan.code,
                amount=amount,
                duration_days=duration_days,
            )
            return existing_grant
        raise PurchaseConflictError("wallet purchase staging failed") from exc

    await session.refresh(grant)
    return grant


async def finalize_wallet_plan_purchase(
    session: AsyncSession,
    *,
    account_id: UUID,
    idempotency_key: str,
    gateway_factory: GatewayFactory | None = None,
) -> Account:
    normalized_idempotency_key = _normalize_required_reference_id(idempotency_key)
    grant = await get_subscription_grant_by_reference(
        session,
        purchase_source=PurchaseSource.WALLET,
        reference_type=WALLET_PURCHASE_REFERENCE_TYPE,
        reference_id=normalized_idempotency_key,
        for_update=True,
    )
    if grant is None:
        raise PurchaseServiceError(f"Wallet purchase grant not found: {normalized_idempotency_key}")

    account = await load_purchase_account_for_update(session, account_id=account_id)
    if grant.account_id != account.id:
        raise PurchaseConflictError("wallet purchase grant belongs to another account")

    if grant.applied_at is not None:
        await session.refresh(account)
        return account

    try:
        await apply_paid_purchase(
            account,
            source=PurchaseSource.WALLET,
            target_expires_at=grant.target_expires_at,
            gateway_factory=gateway_factory,
        )
        await apply_first_referral_reward_for_grant(
            session,
            grant=grant,
        )
    except RemnawaveSyncError:
        await session.rollback()
        raise

    grant.applied_at = utcnow()
    await session.commit()
    await session.refresh(account)
    await clear_account_cache(account.id)
    return account


async def purchase_plan_with_wallet(
    session: AsyncSession,
    *,
    account_id: UUID,
    plan_code: str,
    idempotency_key: str,
    amount_override: int | None = None,
    duration_days_override: int | None = None,
    gateway_factory: GatewayFactory | None = None,
) -> Account:
    await stage_wallet_plan_purchase(
        session,
        account_id=account_id,
        plan_code=plan_code,
        idempotency_key=idempotency_key,
        amount_override=amount_override,
        duration_days_override=duration_days_override,
    )
    return await finalize_wallet_plan_purchase(
        session,
        account_id=account_id,
        idempotency_key=idempotency_key,
        gateway_factory=gateway_factory,
    )
