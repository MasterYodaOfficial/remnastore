from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.db.models import Account, LedgerEntryType, ReferralAttribution, ReferralReward, SubscriptionGrant
from app.services.ledger import apply_credit_in_transaction
from app.services.plans import get_subscription_plan
from app.services.withdrawals import get_withdrawal_availability


class ReferralServiceError(Exception):
    pass


class ReferralCodeNotFoundError(ReferralServiceError):
    pass


class ReferralSelfAttributionError(ReferralServiceError):
    pass


class ReferralAlreadyAttributedError(ReferralServiceError):
    pass


class ReferralAttributionWindowClosedError(ReferralServiceError):
    pass


@dataclass(slots=True)
class ReferralClaimResult:
    attribution: ReferralAttribution
    created: bool


@dataclass(slots=True)
class ReferralSummaryItem:
    referred_account_id: uuid.UUID
    display_name: str
    created_at: datetime
    reward_amount: int
    status: str


@dataclass(slots=True)
class ReferralSummary:
    referral_code: str
    referrals_count: int
    referral_earnings: int
    available_for_withdraw: int
    effective_reward_rate: float
    items: list[ReferralSummaryItem]


def _normalize_referral_code(referral_code: str) -> str:
    normalized = referral_code.strip()
    if not normalized:
        raise ReferralCodeNotFoundError("referral code is required")
    return normalized


def _to_decimal_rate(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def get_effective_referral_reward_rate(account: Account) -> Decimal:
    account_rate = _to_decimal_rate(account.referral_reward_rate)
    if account_rate > 0:
        return account_rate
    return _to_decimal_rate(settings.default_referral_reward_rate)


def calculate_referral_reward_amount(*, purchase_amount_rub: int, reward_rate: Decimal) -> int:
    if purchase_amount_rub <= 0 or reward_rate <= 0:
        return 0
    reward_amount = (Decimal(purchase_amount_rub) * reward_rate / Decimal("100")).quantize(
        Decimal("1"),
        rounding=ROUND_DOWN,
    )
    return int(reward_amount)


def _display_name_for_referral(account: Account | None) -> str:
    if account is None:
        return "Пользователь"
    return (
        account.display_name
        or account.first_name
        or account.username
        or account.email
        or "Пользователь"
    )


async def _load_account_for_update(session: AsyncSession, account_id: uuid.UUID) -> Account:
    result = await session.execute(
        select(Account).where(Account.id == account_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise ReferralServiceError(f"account not found: {account_id}")
    return account


async def _get_account_by_referral_code(
    session: AsyncSession,
    referral_code: str,
) -> Account | None:
    result = await session.execute(
        select(Account).where(Account.referral_code == referral_code)
    )
    return result.scalar_one_or_none()


async def _get_referral_attribution_by_referred_account_id(
    session: AsyncSession,
    referred_account_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> ReferralAttribution | None:
    statement: Select[tuple[ReferralAttribution]] = select(ReferralAttribution).where(
        ReferralAttribution.referred_account_id == referred_account_id
    )
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def _get_referral_reward_by_referred_account_id(
    session: AsyncSession,
    referred_account_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> ReferralReward | None:
    statement: Select[tuple[ReferralReward]] = select(ReferralReward).where(
        ReferralReward.referred_account_id == referred_account_id
    )
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def _get_referral_reward_by_grant_id(
    session: AsyncSession,
    subscription_grant_id: int,
    *,
    for_update: bool = False,
) -> ReferralReward | None:
    statement: Select[tuple[ReferralReward]] = select(ReferralReward).where(
        ReferralReward.subscription_grant_id == subscription_grant_id
    )
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def _has_completed_paid_purchase(
    session: AsyncSession,
    account_id: uuid.UUID,
) -> bool:
    result = await session.execute(
        select(SubscriptionGrant.id)
        .where(
            SubscriptionGrant.account_id == account_id,
            SubscriptionGrant.applied_at.is_not(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def claim_referral_code(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    referral_code: str,
) -> ReferralClaimResult:
    normalized_referral_code = _normalize_referral_code(referral_code)
    referrer_account = await _get_account_by_referral_code(session, normalized_referral_code)
    if referrer_account is None:
        raise ReferralCodeNotFoundError("referral code not found")

    referred_account = await _load_account_for_update(session, account_id)
    if referrer_account.id == referred_account.id:
        raise ReferralSelfAttributionError("self referral is not allowed")

    existing_attribution = await _get_referral_attribution_by_referred_account_id(
        session,
        referred_account.id,
        for_update=True,
    )
    if existing_attribution is not None:
        if existing_attribution.referrer_account_id == referrer_account.id:
            if referred_account.referred_by_account_id is None:
                referred_account.referred_by_account_id = referrer_account.id
            return ReferralClaimResult(attribution=existing_attribution, created=False)
        raise ReferralAlreadyAttributedError("referral already claimed")

    if referred_account.referred_by_account_id is not None:
        if referred_account.referred_by_account_id == referrer_account.id:
            attribution = ReferralAttribution(
                referrer_account_id=referrer_account.id,
                referred_account_id=referred_account.id,
                referral_code=normalized_referral_code,
            )
            session.add(attribution)
            await session.flush()
            return ReferralClaimResult(attribution=attribution, created=False)
        raise ReferralAlreadyAttributedError("referral already claimed")

    if await _has_completed_paid_purchase(session, referred_account.id):
        raise ReferralAttributionWindowClosedError(
            "referral attribution is closed after the first paid purchase"
        )

    locked_referrer_account = await _load_account_for_update(session, referrer_account.id)
    attribution = ReferralAttribution(
        referrer_account_id=locked_referrer_account.id,
        referred_account_id=referred_account.id,
        referral_code=normalized_referral_code,
    )
    referred_account.referred_by_account_id = locked_referrer_account.id
    locked_referrer_account.referrals_count = int(locked_referrer_account.referrals_count) + 1
    session.add(attribution)
    await session.flush()
    return ReferralClaimResult(attribution=attribution, created=True)


async def apply_first_referral_reward_for_grant(
    session: AsyncSession,
    *,
    grant: SubscriptionGrant,
) -> ReferralReward | None:
    if grant.id is None:
        raise ReferralServiceError("subscription grant must be flushed before referral reward")

    existing_reward = await _get_referral_reward_by_grant_id(session, grant.id, for_update=True)
    if existing_reward is not None:
        return existing_reward

    attribution = await _get_referral_attribution_by_referred_account_id(
        session,
        grant.account_id,
        for_update=True,
    )
    if attribution is None:
        return None

    existing_referred_reward = await _get_referral_reward_by_referred_account_id(
        session,
        grant.account_id,
        for_update=True,
    )
    if existing_referred_reward is not None:
        return existing_referred_reward

    referrer_account = await _load_account_for_update(session, attribution.referrer_account_id)
    plan = get_subscription_plan(grant.plan_code)
    reward_rate = get_effective_referral_reward_rate(referrer_account)
    purchase_amount_rub = int(plan.price_rub)
    reward_amount = calculate_referral_reward_amount(
        purchase_amount_rub=purchase_amount_rub,
        reward_rate=reward_rate,
    )
    if reward_amount <= 0:
        return None

    ledger_entry = await apply_credit_in_transaction(
        session,
        account_id=referrer_account.id,
        amount=reward_amount,
        entry_type=LedgerEntryType.REFERRAL_REWARD,
        reference_type="referral_reward",
        reference_id=str(grant.id),
        comment=f"Referral reward for first paid purchase of {grant.account_id}",
        idempotency_key=f"referral_reward:grant:{grant.id}",
    )
    referrer_account.referral_earnings = int(referrer_account.referral_earnings) + reward_amount

    reward = ReferralReward(
        attribution_id=attribution.id,
        referrer_account_id=referrer_account.id,
        referred_account_id=grant.account_id,
        subscription_grant_id=grant.id,
        ledger_entry_id=ledger_entry.id,
        purchase_amount_rub=purchase_amount_rub,
        reward_amount=reward_amount,
        reward_rate=float(reward_rate),
        currency="RUB",
    )
    session.add(reward)
    await session.flush()
    return reward


async def get_referral_summary(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
) -> ReferralSummary:
    account = await session.get(Account, account_id)
    if account is None:
        raise ReferralServiceError(f"account not found: {account_id}")

    referred_account = aliased(Account)
    result = await session.execute(
        select(ReferralAttribution, referred_account, ReferralReward)
        .outerjoin(referred_account, referred_account.id == ReferralAttribution.referred_account_id)
        .outerjoin(ReferralReward, ReferralReward.attribution_id == ReferralAttribution.id)
        .where(ReferralAttribution.referrer_account_id == account.id)
        .order_by(ReferralAttribution.created_at.desc())
    )

    items: list[ReferralSummaryItem] = []
    for attribution, referred, reward in result.all():
        items.append(
            ReferralSummaryItem(
                referred_account_id=attribution.referred_account_id,
                display_name=_display_name_for_referral(referred),
                created_at=attribution.created_at,
                reward_amount=0 if reward is None else int(reward.reward_amount),
                status="pending" if reward is None else "active",
            )
        )

    return ReferralSummary(
        referral_code=account.referral_code or "",
        referrals_count=int(account.referrals_count),
        referral_earnings=int(account.referral_earnings),
        available_for_withdraw=(await get_withdrawal_availability(session, account=account)).available_for_withdraw,
        effective_reward_rate=float(get_effective_referral_reward_rate(account)),
        items=items,
    )
