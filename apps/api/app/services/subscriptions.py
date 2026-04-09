from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Account, AccountStatus, PromoCode
from app.integrations.remnawave import (
    RemnawaveConfigurationError,
    RemnawaveRequestError,
    RemnawaveUser,
    get_remnawave_gateway,
)
from app.schemas.subscription import SubscriptionStateResponse, TrialEligibilityResponse
from app.services.account_events import append_account_event
from app.services.cache import get_cache
from app.services.i18n import translate
from app.services.purchases import (
    resolve_trial_traffic_limit_bytes,
    resolve_trial_traffic_limit_strategy,
    PurchaseConflictError,
    RemnawaveSyncError,
    apply_remote_subscription_snapshot,
    apply_trial_purchase,
    clear_remote_subscription_snapshot,
    finalize_wallet_plan_purchase,
    get_subscription_grant_by_reference,
    purchase_plan_with_wallet,
    PurchaseSource,
    stage_wallet_plan_purchase,
    target_remnawave_user_uuid,
)
from app.services.promos import (
    WALLET_PURCHASE_REFERENCE_TYPE,
    get_promo_redemption_by_reference,
    mark_promo_redemption_applied,
    normalize_promo_code,
    quote_plan_promo,
    stage_promo_redemption,
)
from app.services.plans import get_subscription_plan


class SubscriptionServiceError(Exception):
    pass


class TrialEligibilityError(SubscriptionServiceError):
    def __init__(self, reason: str, *, status_code: int = 400):
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


class SubscriptionPurchaseBlockedError(SubscriptionServiceError):
    def __init__(self, detail: str, *, code: str | None = None) -> None:
        super().__init__(detail)
        self.code = code


@dataclass(slots=True)
class TrialEligibility:
    eligible: bool
    reason: Optional[str] = None


def _subscription_error(key: str) -> str:
    return translate(f"api.subscriptions.errors.{key}")


async def _clear_account_cache(account_id: UUID) -> None:
    cache = get_cache()
    await cache.delete(cache.account_response_key(str(account_id)))


async def _load_managed_account(session: AsyncSession, account_id: UUID) -> Account:
    result = await session.execute(
        select(Account).where(Account.id == account_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise SubscriptionServiceError(_subscription_error("account_not_found"))
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
                and_(
                    Account.remnawave_user_uuid.is_(None),
                    Account.id == remnawave_user_uuid,
                ),
            )
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def get_current_subscription(account: Account) -> SubscriptionStateResponse:
    return SubscriptionStateResponse.from_account(account)


async def _find_remnawave_identity_conflict(
    account: Account,
    gateway,
) -> RemnawaveUser | None:
    target_uuid = target_remnawave_user_uuid(account)

    if account.email:
        users_with_email = await gateway.get_users_by_email(account.email)
        for remote_user in users_with_email:
            if remote_user.uuid != target_uuid:
                return remote_user

    if account.telegram_id is not None:
        users_with_telegram = await gateway.get_users_by_telegram_id(
            account.telegram_id
        )
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
        raise RemnawaveSyncError(
            translate("api.purchases.errors.remnawave_not_configured")
        ) from exc

    try:
        remote_user = await gateway.get_user_by_uuid(
            target_remnawave_user_uuid(account)
        )
    except RemnawaveRequestError as exc:
        raise RemnawaveSyncError(
            translate("api.purchases.errors.remnawave_unavailable")
        ) from exc

    if remote_user is None:
        clear_remote_subscription_snapshot(account)
    else:
        apply_remote_subscription_snapshot(account, remote_user)

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
            eligibility = TrialEligibility(
                eligible=False, reason="remnawave_not_configured"
            )
        else:
            try:
                remote_user = await gateway.get_user_by_uuid(
                    target_remnawave_user_uuid(account)
                )
            except RemnawaveRequestError:
                eligibility = TrialEligibility(
                    eligible=False, reason="remnawave_unavailable"
                )
            else:
                if remote_user is not None:
                    apply_remote_subscription_snapshot(account, remote_user)
                    await session.commit()
                    await session.refresh(account)
                    await _clear_account_cache(account.id)
                    eligibility = TrialEligibility(
                        eligible=False, reason="subscription_exists"
                    )
                else:
                    try:
                        identity_conflict = await _find_remnawave_identity_conflict(
                            account, gateway
                        )
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
                        elif (
                            account.subscription_url
                            or account.subscription_expires_at is not None
                        ):
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
    source: str = "api",
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
        raise TrialEligibilityError(
            eligibility.reason or "trial_not_eligible", status_code=status_code
        )

    purchase_result = await apply_trial_purchase(
        account,
        trial_duration_days=settings.trial_duration_days,
        gateway_factory=get_remnawave_gateway,
    )
    await append_account_event(
        session,
        account_id=account.id,
        actor_account_id=account.id,
        event_type="subscription.trial.activated",
        source=source,
        payload={
            "target_expires_at": purchase_result.target_expires_at.isoformat(),
            "trial_used_at": None
            if purchase_result.trial_used_at is None
            else purchase_result.trial_used_at.isoformat(),
            "trial_ends_at": None
            if purchase_result.trial_ends_at is None
            else purchase_result.trial_ends_at.isoformat(),
            "duration_days": settings.trial_duration_days,
            "traffic_limit_bytes": resolve_trial_traffic_limit_bytes(),
            "traffic_limit_strategy": resolve_trial_traffic_limit_strategy(),
            "hwid_device_limit": settings.trial_device_limit,
        },
    )

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
        raise RemnawaveSyncError(
            translate("api.purchases.errors.remnawave_not_configured")
        ) from exc

    try:
        remote_user = await gateway.get_user_by_uuid(remnawave_user_uuid)
    except RemnawaveRequestError as exc:
        raise RemnawaveSyncError(
            translate("api.purchases.errors.remnawave_unavailable")
        ) from exc

    if remote_user is None:
        clear_remote_subscription_snapshot(account)
    else:
        apply_remote_subscription_snapshot(account, remote_user)

    await session.commit()
    await session.refresh(account)
    await _clear_account_cache(account.id)
    return account


async def purchase_subscription_with_wallet(
    session: AsyncSession,
    *,
    account: Account,
    plan_code: str,
    idempotency_key: str,
    promo_code: str | None = None,
) -> SubscriptionStateResponse:
    if account.status == AccountStatus.BLOCKED:
        raise SubscriptionPurchaseBlockedError(
            _subscription_error("account_blocked_purchase"),
            code="account_blocked_purchase",
        )

    if promo_code is None:
        account = await purchase_plan_with_wallet(
            session,
            account_id=account.id,
            plan_code=plan_code,
            idempotency_key=idempotency_key,
            gateway_factory=get_remnawave_gateway,
        )
        return SubscriptionStateResponse.from_account(account)

    existing_grant = await get_subscription_grant_by_reference(
        session,
        purchase_source=PurchaseSource.WALLET,
        reference_type=WALLET_PURCHASE_REFERENCE_TYPE,
        reference_id=idempotency_key,
    )
    if existing_grant is not None:
        existing_redemption = await get_promo_redemption_by_reference(
            session,
            reference_type=WALLET_PURCHASE_REFERENCE_TYPE,
            reference_id=idempotency_key,
        )
        if existing_redemption is not None:
            existing_promo_code = await session.get(
                PromoCode, existing_redemption.promo_code_id
            )
            if (
                existing_promo_code is None
                or existing_promo_code.code != normalize_promo_code(promo_code)
            ):
                raise PurchaseConflictError(
                    _subscription_error("idempotency_promo_conflict"),
                    code="idempotency_promo_conflict",
                )
            account = await finalize_wallet_plan_purchase(
                session,
                account_id=account.id,
                idempotency_key=idempotency_key,
                gateway_factory=get_remnawave_gateway,
            )
            await mark_promo_redemption_applied(
                session,
                reference_type=WALLET_PURCHASE_REFERENCE_TYPE,
                reference_id=idempotency_key,
                subscription_grant_id=existing_grant.id,
            )
            await session.commit()
            await session.refresh(account)
            return SubscriptionStateResponse.from_account(account)

    plan = get_subscription_plan(plan_code)
    quote = await quote_plan_promo(
        session,
        account=account,
        plan_code=plan.code,
        base_amount=plan.price_rub,
        currency="RUB",
        code=promo_code,
    )
    grant = await stage_wallet_plan_purchase(
        session,
        account_id=account.id,
        plan_code=plan.code,
        idempotency_key=idempotency_key,
        amount_override=quote.final_amount,
        duration_days_override=quote.final_duration_days,
    )
    resolved_reference_id = str(grant.reference_id or idempotency_key)
    if resolved_reference_id != idempotency_key:
        existing_redemption = await get_promo_redemption_by_reference(
            session,
            reference_type=WALLET_PURCHASE_REFERENCE_TYPE,
            reference_id=resolved_reference_id,
        )
        if existing_redemption is None:
            raise PurchaseConflictError(
                translate("api.purchases.errors.wallet_pending_purchase"),
                code="wallet_pending_purchase",
            )
        existing_promo_code = await session.get(
            PromoCode, existing_redemption.promo_code_id
        )
        if (
            existing_promo_code is None
            or existing_promo_code.code != normalize_promo_code(promo_code)
        ):
            raise PurchaseConflictError(
                _subscription_error("idempotency_promo_conflict"),
                code="idempotency_promo_conflict",
            )
    await stage_promo_redemption(
        session,
        account_id=account.id,
        quote=quote,
        reference_type=WALLET_PURCHASE_REFERENCE_TYPE,
        reference_id=resolved_reference_id,
        subscription_grant_id=grant.id,
    )
    account = await finalize_wallet_plan_purchase(
        session,
        account_id=account.id,
        idempotency_key=resolved_reference_id,
        gateway_factory=get_remnawave_gateway,
    )
    await mark_promo_redemption_applied(
        session,
        reference_type=WALLET_PURCHASE_REFERENCE_TYPE,
        reference_id=resolved_reference_id,
        subscription_grant_id=grant.id,
    )
    await session.commit()
    await session.refresh(account)
    return SubscriptionStateResponse.from_account(account)
