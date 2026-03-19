from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Account,
    AccountStatus,
    LedgerEntry,
    LedgerEntryType,
    PromoCampaign,
    PromoCampaignStatus,
    PromoCode,
    PromoEffectType,
    PromoRedemption,
    PromoRedemptionContext,
    PromoRedemptionStatus,
    SubscriptionGrant,
)
from app.services.ledger import apply_credit_in_transaction, clear_account_cache
from app.services.plans import SubscriptionPlan, SubscriptionPlanError, get_subscription_plan
from app.services.purchases import (
    PurchaseSource,
    RemnawaveSyncError,
    apply_paid_purchase,
    compute_paid_plan_window,
    load_purchase_account_for_update,
    utcnow,
)


PENDING_PROMO_REDEMPTION_STATUSES = (
    PromoRedemptionStatus.PENDING,
    PromoRedemptionStatus.APPLIED,
)
DIRECT_REDEEM_REFERENCE_TYPE = "direct_redeem"
PAYMENT_REFERENCE_TYPE = "payment"
WALLET_PURCHASE_REFERENCE_TYPE = "wallet_purchase"
PROMO_SUBSCRIPTION_PLAN_CODE = "promo_bonus"


class PromoServiceError(Exception):
    pass


class PromoCodeNotFoundError(PromoServiceError):
    pass


class PromoValidationError(PromoServiceError):
    pass


class PromoConflictError(PromoServiceError):
    pass


class PromoBlockedError(PromoServiceError):
    pass


@dataclass(slots=True)
class PromoPlanQuote:
    campaign: PromoCampaign
    promo_code: PromoCode
    plan: SubscriptionPlan
    original_amount: int
    final_amount: int
    currency: str
    discount_amount: int
    original_duration_days: int
    final_duration_days: int


@dataclass(slots=True)
class PromoDirectRedeemResult:
    account: Account
    redemption: PromoRedemption
    ledger_entry: LedgerEntry | None = None
    subscription_grant: SubscriptionGrant | None = None


def normalize_promo_code(raw_code: str) -> str:
    normalized = raw_code.strip().upper()
    if not normalized:
        raise PromoValidationError("promo code is required")
    return normalized


def _now() -> datetime:
    return datetime.now(UTC)


def _has_active_subscription(account: Account) -> bool:
    expires_at = account.subscription_expires_at
    if expires_at is None:
        return False
    comparable_expires_at = expires_at if expires_at.tzinfo is not None else expires_at.replace(tzinfo=UTC)
    return account.subscription_status == "ACTIVE" and comparable_expires_at > _now()


async def _get_promo_code_by_code(
    session: AsyncSession,
    *,
    code: str,
    for_update: bool = False,
) -> PromoCode | None:
    statement = select(PromoCode).where(PromoCode.code == code)
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def _get_promo_redemption_by_reference(
    session: AsyncSession,
    *,
    reference_type: str,
    reference_id: str,
    for_update: bool = False,
) -> PromoRedemption | None:
    statement = select(PromoRedemption).where(
        PromoRedemption.reference_type == reference_type,
        PromoRedemption.reference_id == reference_id,
    )
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def get_promo_redemption_by_reference(
    session: AsyncSession,
    *,
    reference_type: str,
    reference_id: str,
    for_update: bool = False,
) -> PromoRedemption | None:
    return await _get_promo_redemption_by_reference(
        session,
        reference_type=reference_type,
        reference_id=reference_id,
        for_update=for_update,
    )


async def _count_campaign_redemptions(
    session: AsyncSession,
    *,
    campaign_id: int,
    account_id: UUID | None = None,
    promo_code_id: int | None = None,
) -> int:
    filters = [
        PromoRedemption.campaign_id == campaign_id,
        PromoRedemption.status.in_(PENDING_PROMO_REDEMPTION_STATUSES),
    ]
    if account_id is not None:
        filters.append(PromoRedemption.account_id == account_id)
    if promo_code_id is not None:
        filters.append(PromoRedemption.promo_code_id == promo_code_id)
    return int(await session.scalar(select(func.count()).select_from(PromoRedemption).where(*filters)) or 0)


async def _account_has_paid_purchase(
    session: AsyncSession,
    *,
    account_id: UUID,
) -> bool:
    paid_purchase_count = await session.scalar(
        select(func.count())
        .select_from(SubscriptionGrant)
        .where(
            SubscriptionGrant.account_id == account_id,
            SubscriptionGrant.purchase_source.in_(
                (
                    PurchaseSource.WALLET.value,
                    PurchaseSource.DIRECT_PAYMENT.value,
                )
            ),
        )
    )
    return int(paid_purchase_count or 0) > 0


async def _load_validated_promo_for_context(
    session: AsyncSession,
    *,
    account: Account,
    code: str,
    context: PromoRedemptionContext,
    plan_code: str | None = None,
    for_update: bool = False,
) -> tuple[PromoCampaign, PromoCode]:
    normalized_code = normalize_promo_code(code)
    promo_code = await _get_promo_code_by_code(session, code=normalized_code, for_update=for_update)
    if promo_code is None:
        raise PromoCodeNotFoundError("promo code not found")
    if not promo_code.is_active:
        raise PromoValidationError("promo code is disabled")

    campaign = await session.get(PromoCampaign, promo_code.campaign_id)
    if campaign is None:
        raise PromoCodeNotFoundError("promo campaign not found")
    if campaign.status != PromoCampaignStatus.ACTIVE:
        raise PromoValidationError("promo campaign is not active")

    now = _now()
    if campaign.starts_at is not None:
        starts_at = campaign.starts_at if campaign.starts_at.tzinfo is not None else campaign.starts_at.replace(tzinfo=UTC)
        if starts_at > now:
            raise PromoValidationError("promo campaign has not started yet")
    if campaign.ends_at is not None:
        ends_at = campaign.ends_at if campaign.ends_at.tzinfo is not None else campaign.ends_at.replace(tzinfo=UTC)
        if ends_at <= now:
            raise PromoValidationError("promo campaign has already ended")

    if account.status == AccountStatus.BLOCKED:
        raise PromoBlockedError("blocked accounts cannot redeem promo codes")

    if promo_code.assigned_account_id is not None and promo_code.assigned_account_id != account.id:
        raise PromoValidationError("promo code belongs to another account")

    if campaign.plan_codes and plan_code is None:
        raise PromoValidationError("promo code can be used only for selected plans")
    if plan_code is not None and campaign.plan_codes and plan_code not in set(campaign.plan_codes):
        raise PromoValidationError("promo code is not available for this plan")

    if campaign.first_purchase_only and await _account_has_paid_purchase(session, account_id=account.id):
        raise PromoValidationError("promo code is available only for the first paid purchase")

    has_active_subscription = _has_active_subscription(account)
    if campaign.requires_active_subscription and not has_active_subscription:
        raise PromoValidationError("promo code requires an active subscription")
    if campaign.requires_no_active_subscription and has_active_subscription:
        raise PromoValidationError("promo code requires no active subscription")

    if campaign.total_redemptions_limit is not None:
        total_redemptions = await _count_campaign_redemptions(session, campaign_id=campaign.id)
        if total_redemptions >= campaign.total_redemptions_limit:
            raise PromoValidationError("promo campaign redemption limit reached")

    if campaign.per_account_redemptions_limit is not None:
        account_redemptions = await _count_campaign_redemptions(
            session,
            campaign_id=campaign.id,
            account_id=account.id,
        )
        if account_redemptions >= campaign.per_account_redemptions_limit:
            raise PromoValidationError("promo code redemption limit reached for this account")

    if promo_code.max_redemptions is not None:
        code_redemptions = await _count_campaign_redemptions(
            session,
            campaign_id=campaign.id,
            promo_code_id=promo_code.id,
        )
        if code_redemptions >= promo_code.max_redemptions:
            raise PromoValidationError("promo code redemption limit reached")

    if context == PromoRedemptionContext.PLAN_PURCHASE and campaign.effect_type not in (
        PromoEffectType.PERCENT_DISCOUNT,
        PromoEffectType.FIXED_DISCOUNT,
        PromoEffectType.FIXED_PRICE,
        PromoEffectType.EXTRA_DAYS,
    ):
        raise PromoValidationError("promo code cannot be used for plan purchase")

    if context == PromoRedemptionContext.DIRECT and campaign.effect_type not in (
        PromoEffectType.FREE_DAYS,
        PromoEffectType.EXTRA_DAYS,
        PromoEffectType.BALANCE_CREDIT,
    ):
        raise PromoValidationError("promo code cannot be redeemed directly")

    return campaign, promo_code


def _compute_discounted_amount(
    *,
    effect_type: PromoEffectType,
    effect_value: int,
    base_amount: int,
    currency: str,
    campaign_currency: str,
) -> tuple[int, int]:
    if effect_type == PromoEffectType.PERCENT_DISCOUNT:
        discount_amount = min(base_amount, (base_amount * effect_value) // 100)
        return base_amount - discount_amount, discount_amount

    if campaign_currency != currency:
        raise PromoValidationError("promo code currency does not match selected payment method")

    if effect_type == PromoEffectType.FIXED_DISCOUNT:
        discount_amount = min(base_amount, effect_value)
        return base_amount - discount_amount, discount_amount

    if effect_type == PromoEffectType.FIXED_PRICE:
        if effect_value >= base_amount:
            raise PromoValidationError("promo code does not improve the selected plan price")
        return effect_value, base_amount - effect_value

    raise PromoValidationError("unsupported discount effect")


async def quote_plan_promo(
    session: AsyncSession,
    *,
    account: Account,
    plan_code: str,
    base_amount: int,
    currency: str,
    code: str,
) -> PromoPlanQuote:
    plan = get_subscription_plan(plan_code)
    campaign, promo_code = await _load_validated_promo_for_context(
        session,
        account=account,
        code=code,
        context=PromoRedemptionContext.PLAN_PURCHASE,
        plan_code=plan.code,
    )

    final_amount = base_amount
    discount_amount = 0
    final_duration_days = plan.duration_days
    if campaign.effect_type in (
        PromoEffectType.PERCENT_DISCOUNT,
        PromoEffectType.FIXED_DISCOUNT,
        PromoEffectType.FIXED_PRICE,
    ):
        final_amount, discount_amount = _compute_discounted_amount(
            effect_type=campaign.effect_type,
            effect_value=campaign.effect_value,
            base_amount=base_amount,
            currency=currency,
            campaign_currency=campaign.currency,
        )
        if final_amount <= 0:
            raise PromoValidationError("promo code reduces payment amount to zero; use direct redemption instead")
    elif campaign.effect_type == PromoEffectType.EXTRA_DAYS:
        final_duration_days += campaign.effect_value

    return PromoPlanQuote(
        campaign=campaign,
        promo_code=promo_code,
        plan=plan,
        original_amount=base_amount,
        final_amount=final_amount,
        currency=currency,
        discount_amount=discount_amount,
        original_duration_days=plan.duration_days,
        final_duration_days=final_duration_days,
    )


def _validate_existing_redemption(
    redemption: PromoRedemption,
    *,
    account_id: UUID,
    promo_code_id: int,
    plan_code: str | None,
    effect_type: PromoEffectType,
    effect_value: int,
    original_amount: int | None,
    discount_amount: int | None,
    final_amount: int | None,
    granted_duration_days: int | None,
) -> None:
    if redemption.account_id != account_id:
        raise PromoConflictError("idempotency key already belongs to another account")
    if redemption.promo_code_id != promo_code_id:
        raise PromoConflictError("idempotency key already used for another promo code")
    if redemption.plan_code != plan_code:
        raise PromoConflictError("idempotency key already used for another plan")
    if redemption.effect_type != effect_type or redemption.effect_value != effect_value:
        raise PromoConflictError("idempotency key already used for another promo effect")
    if redemption.original_amount != original_amount:
        raise PromoConflictError("idempotency key already used for another original amount")
    if redemption.discount_amount != discount_amount:
        raise PromoConflictError("idempotency key already used for another discount amount")
    if redemption.final_amount != final_amount:
        raise PromoConflictError("idempotency key already used for another final amount")
    if redemption.granted_duration_days != granted_duration_days:
        raise PromoConflictError("idempotency key already used for another duration")


async def stage_promo_redemption(
    session: AsyncSession,
    *,
    account_id: UUID,
    quote: PromoPlanQuote,
    reference_type: str,
    reference_id: str,
    payment_id: int | None = None,
    subscription_grant_id: int | None = None,
) -> PromoRedemption:
    existing = await _get_promo_redemption_by_reference(
        session,
        reference_type=reference_type,
        reference_id=reference_id,
        for_update=True,
    )
    if existing is not None:
        _validate_existing_redemption(
            existing,
            account_id=account_id,
            promo_code_id=quote.promo_code.id,
            plan_code=quote.plan.code,
            effect_type=quote.campaign.effect_type,
            effect_value=quote.campaign.effect_value,
            original_amount=quote.original_amount,
            discount_amount=quote.discount_amount or None,
            final_amount=quote.final_amount,
            granted_duration_days=quote.final_duration_days,
        )
        return existing

    redemption = PromoRedemption(
        campaign_id=quote.campaign.id,
        promo_code_id=quote.promo_code.id,
        account_id=account_id,
        status=PromoRedemptionStatus.PENDING,
        redemption_context=PromoRedemptionContext.PLAN_PURCHASE,
        plan_code=quote.plan.code,
        effect_type=quote.campaign.effect_type,
        effect_value=quote.campaign.effect_value,
        currency=quote.currency,
        original_amount=quote.original_amount,
        discount_amount=quote.discount_amount or None,
        final_amount=quote.final_amount,
        granted_duration_days=quote.final_duration_days,
        payment_id=payment_id,
        subscription_grant_id=subscription_grant_id,
        reference_type=reference_type,
        reference_id=reference_id,
    )
    session.add(redemption)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        existing = await _get_promo_redemption_by_reference(
            session,
            reference_type=reference_type,
            reference_id=reference_id,
            for_update=True,
        )
        if existing is not None:
            _validate_existing_redemption(
                existing,
                account_id=account_id,
                promo_code_id=quote.promo_code.id,
                plan_code=quote.plan.code,
                effect_type=quote.campaign.effect_type,
                effect_value=quote.campaign.effect_value,
                original_amount=quote.original_amount,
                discount_amount=quote.discount_amount or None,
                final_amount=quote.final_amount,
                granted_duration_days=quote.final_duration_days,
            )
            return existing
        raise PromoConflictError("promo redemption staging failed") from exc

    await session.refresh(redemption)
    return redemption


async def mark_promo_redemption_applied(
    session: AsyncSession,
    *,
    reference_type: str,
    reference_id: str,
    payment_id: int | None = None,
    subscription_grant_id: int | None = None,
    ledger_entry_id: int | None = None,
) -> PromoRedemption | None:
    redemption = await _get_promo_redemption_by_reference(
        session,
        reference_type=reference_type,
        reference_id=reference_id,
        for_update=True,
    )
    if redemption is None:
        return None

    if redemption.payment_id is not None and payment_id is not None and redemption.payment_id != payment_id:
        raise PromoConflictError("promo redemption already belongs to another payment")
    if redemption.subscription_grant_id is not None and subscription_grant_id is not None:
        if redemption.subscription_grant_id != subscription_grant_id:
            raise PromoConflictError("promo redemption already belongs to another subscription grant")
    if redemption.ledger_entry_id is not None and ledger_entry_id is not None and redemption.ledger_entry_id != ledger_entry_id:
        raise PromoConflictError("promo redemption already belongs to another ledger entry")

    redemption.payment_id = payment_id if payment_id is not None else redemption.payment_id
    redemption.subscription_grant_id = (
        subscription_grant_id if subscription_grant_id is not None else redemption.subscription_grant_id
    )
    redemption.ledger_entry_id = ledger_entry_id if ledger_entry_id is not None else redemption.ledger_entry_id
    if redemption.status != PromoRedemptionStatus.APPLIED:
        redemption.status = PromoRedemptionStatus.APPLIED
        redemption.applied_at = utcnow()
    return redemption


async def redeem_promo_code(
    session: AsyncSession,
    *,
    account: Account,
    code: str,
    idempotency_key: str,
    gateway_factory=None,
) -> PromoDirectRedeemResult:
    normalized_idempotency_key = idempotency_key.strip()
    if not normalized_idempotency_key:
        raise PromoValidationError("idempotency_key is required")

    existing = await _get_promo_redemption_by_reference(
        session,
        reference_type=DIRECT_REDEEM_REFERENCE_TYPE,
        reference_id=normalized_idempotency_key,
        for_update=True,
    )
    if existing is not None:
        normalized_code = normalize_promo_code(code)
        if existing.account_id != account.id:
            raise PromoConflictError("idempotency key already belongs to another account")
        if existing.status == PromoRedemptionStatus.APPLIED:
            promo_code = await session.get(PromoCode, existing.promo_code_id)
            if promo_code is None or promo_code.code != normalized_code:
                raise PromoConflictError("idempotency key already used for another promo code")
            refreshed_account = await load_purchase_account_for_update(session, account_id=account.id)
            ledger_entry = None if existing.ledger_entry_id is None else await session.get(LedgerEntry, existing.ledger_entry_id)
            subscription_grant = (
                None
                if existing.subscription_grant_id is None
                else await session.get(SubscriptionGrant, existing.subscription_grant_id)
            )
            return PromoDirectRedeemResult(
                account=refreshed_account,
                redemption=existing,
                ledger_entry=ledger_entry,
                subscription_grant=subscription_grant,
            )
        raise PromoConflictError("promo redemption is already in progress")

    managed_account = await load_purchase_account_for_update(session, account_id=account.id)
    campaign, promo_code = await _load_validated_promo_for_context(
        session,
        account=managed_account,
        code=code,
        context=PromoRedemptionContext.DIRECT,
        for_update=True,
    )

    redemption = PromoRedemption(
        campaign_id=campaign.id,
        promo_code_id=promo_code.id,
        account_id=managed_account.id,
        status=PromoRedemptionStatus.PENDING,
        redemption_context=PromoRedemptionContext.DIRECT,
        effect_type=campaign.effect_type,
        effect_value=campaign.effect_value,
        currency=campaign.currency,
        reference_type=DIRECT_REDEEM_REFERENCE_TYPE,
        reference_id=normalized_idempotency_key,
    )
    session.add(redemption)
    await session.flush()

    ledger_entry: LedgerEntry | None = None
    subscription_grant: SubscriptionGrant | None = None
    try:
        if campaign.effect_type == PromoEffectType.BALANCE_CREDIT:
            ledger_entry = await apply_credit_in_transaction(
                session,
                account_id=managed_account.id,
                amount=campaign.effect_value,
                entry_type=LedgerEntryType.PROMO_CREDIT,
                reference_type="promo_redemption",
                reference_id=str(redemption.id),
                comment=f"Promo code {promo_code.code}",
                idempotency_key=f"promo_redemption:{redemption.id}:credit",
            )
            redemption.balance_credit_amount = campaign.effect_value
            redemption.ledger_entry_id = ledger_entry.id
        else:
            base_expires_at, target_expires_at = compute_paid_plan_window(
                managed_account,
                duration_days=campaign.effect_value,
            )
            subscription_grant = SubscriptionGrant(
                account_id=managed_account.id,
                payment_id=None,
                purchase_source=PurchaseSource.PROMO.value,
                reference_type="promo_redemption",
                reference_id=str(redemption.id),
                plan_code=PROMO_SUBSCRIPTION_PLAN_CODE,
                amount=0,
                currency="RUB",
                duration_days=campaign.effect_value,
                base_expires_at=base_expires_at,
                target_expires_at=target_expires_at,
            )
            session.add(subscription_grant)
            await session.flush()
            await apply_paid_purchase(
                managed_account,
                source=PurchaseSource.PROMO,
                target_expires_at=target_expires_at,
                gateway_factory=gateway_factory,
            )
            subscription_grant.applied_at = utcnow()
            redemption.subscription_grant_id = subscription_grant.id
            redemption.granted_duration_days = campaign.effect_value
    except RemnawaveSyncError:
        await session.rollback()
        raise

    redemption.status = PromoRedemptionStatus.APPLIED
    redemption.applied_at = utcnow()
    await session.commit()
    await session.refresh(managed_account)
    await clear_account_cache(managed_account.id)
    return PromoDirectRedeemResult(
        account=managed_account,
        redemption=redemption,
        ledger_entry=ledger_entry,
        subscription_grant=subscription_grant,
    )


def resolve_plan_checkout_amount(*, plan_code: str, currency: str) -> int:
    plan = get_subscription_plan(plan_code)
    if currency == "RUB":
        return plan.price_rub
    if currency == "XTR":
        if plan.price_stars is None:
            raise SubscriptionPlanError(f"Telegram Stars price is not configured for plan {plan.code}")
        return plan.price_stars
    raise PromoValidationError(f"unsupported checkout currency: {currency}")
