from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN
import uuid
from typing import Literal

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.audit import log_audit_event
from app.core.config import settings
from app.db.models import (
    Account,
    LedgerEntryType,
    ReferralAttribution,
    ReferralReward,
    SubscriptionGrant,
    TelegramReferralIntent,
)
from app.services.account_events import append_account_event
from app.services.ledger import apply_credit_in_transaction
from app.services.i18n import translate
from app.services.notifications import notify_referral_reward_received
from app.services.plans import get_subscription_plan
from app.services.withdrawals import get_withdrawal_availability

PAID_REFERRAL_PURCHASE_SOURCES = ("wallet", "direct_payment")


class ReferralServiceError(Exception):
    default_code: str | None = None

    def __init__(self, detail: str, *, code: str | None = None) -> None:
        super().__init__(detail)
        self.code = code or self.default_code


class ReferralCodeNotFoundError(ReferralServiceError):
    default_code = "code_not_found"


class ReferralSelfAttributionError(ReferralServiceError):
    default_code = "self_referral"


class ReferralAlreadyAttributedError(ReferralServiceError):
    default_code = "already_claimed"


class ReferralAttributionWindowClosedError(ReferralServiceError):
    default_code = "window_closed"


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


ReferralFeedStatus = Literal["all", "active", "pending"]


@dataclass(slots=True)
class ReferralFeedPage:
    items: list[ReferralSummaryItem]
    total: int
    limit: int
    offset: int
    status_filter: ReferralFeedStatus


@dataclass(slots=True)
class TelegramReferralIntentResult:
    applied: bool
    created: bool
    reason: str | None = None


def _referral_error(key: str) -> str:
    return translate(f"api.referrals.errors.{key}")


def _normalize_referral_code(referral_code: str) -> str:
    normalized = referral_code.strip()
    if not normalized:
        raise ReferralCodeNotFoundError(_referral_error("code_required"))
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


def calculate_referral_reward_amount(
    *, purchase_amount_rub: int, reward_rate: Decimal
) -> int:
    if purchase_amount_rub <= 0 or reward_rate <= 0:
        return 0
    reward_amount = (
        Decimal(purchase_amount_rub) * reward_rate / Decimal("100")
    ).quantize(
        Decimal("1"),
        rounding=ROUND_DOWN,
    )
    return int(reward_amount)


def _display_name_for_referral(account: Account | None) -> str:
    if account is None:
        return translate("api.referrals.fallback_user_name")
    return (
        account.display_name
        or account.first_name
        or account.username
        or account.email
        or translate("api.referrals.fallback_user_name")
    )


def _normalize_referral_feed_status(
    status_filter: ReferralFeedStatus | None,
) -> ReferralFeedStatus:
    if status_filter in {"active", "pending"}:
        return status_filter
    return "all"


async def _load_account_for_update(
    session: AsyncSession, account_id: uuid.UUID
) -> Account:
    result = await session.execute(
        select(Account).where(Account.id == account_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise ReferralServiceError(_referral_error("account_not_found"))
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
            SubscriptionGrant.purchase_source.in_(PAID_REFERRAL_PURCHASE_SOURCES),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _get_telegram_referral_intent_by_telegram_id(
    session: AsyncSession,
    telegram_id: int,
    *,
    for_update: bool = False,
) -> TelegramReferralIntent | None:
    statement: Select[tuple[TelegramReferralIntent]] = select(
        TelegramReferralIntent
    ).where(TelegramReferralIntent.telegram_id == telegram_id)
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def _append_referral_claim_events(
    session: AsyncSession,
    *,
    referred_account_id: uuid.UUID,
    referrer_account_id: uuid.UUID,
    referral_code: str,
    created: bool,
) -> None:
    await append_account_event(
        session,
        account_id=referred_account_id,
        actor_account_id=referred_account_id,
        event_type="referral.claim",
        source="api",
        payload={
            "referrer_account_id": referrer_account_id,
            "referral_code": referral_code,
            "created": created,
        },
    )
    if created:
        await append_account_event(
            session,
            account_id=referrer_account_id,
            actor_account_id=referred_account_id,
            event_type="referral.attributed",
            source="api",
            payload={
                "referred_account_id": referred_account_id,
                "referral_code": referral_code,
            },
        )


async def claim_referral_code(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    referral_code: str,
) -> ReferralClaimResult:
    normalized_referral_code = _normalize_referral_code(referral_code)
    referrer_account = await _get_account_by_referral_code(
        session, normalized_referral_code
    )
    if referrer_account is None:
        raise ReferralCodeNotFoundError(_referral_error("code_not_found"))

    referred_account = await _load_account_for_update(session, account_id)
    if referrer_account.id == referred_account.id:
        raise ReferralSelfAttributionError(_referral_error("self_referral"))

    existing_attribution = await _get_referral_attribution_by_referred_account_id(
        session,
        referred_account.id,
        for_update=True,
    )
    if existing_attribution is not None:
        if existing_attribution.referrer_account_id == referrer_account.id:
            if referred_account.referred_by_account_id is None:
                referred_account.referred_by_account_id = referrer_account.id
            await _append_referral_claim_events(
                session,
                referred_account_id=referred_account.id,
                referrer_account_id=referrer_account.id,
                referral_code=normalized_referral_code,
                created=False,
            )
            return ReferralClaimResult(attribution=existing_attribution, created=False)
        raise ReferralAlreadyAttributedError(_referral_error("already_claimed"))

    if referred_account.referred_by_account_id is not None:
        if referred_account.referred_by_account_id == referrer_account.id:
            attribution = ReferralAttribution(
                referrer_account_id=referrer_account.id,
                referred_account_id=referred_account.id,
                referral_code=normalized_referral_code,
            )
            session.add(attribution)
            await session.flush()
            await _append_referral_claim_events(
                session,
                referred_account_id=referred_account.id,
                referrer_account_id=referrer_account.id,
                referral_code=normalized_referral_code,
                created=False,
            )
            return ReferralClaimResult(attribution=attribution, created=False)
        raise ReferralAlreadyAttributedError(_referral_error("already_claimed"))

    if await _has_completed_paid_purchase(session, referred_account.id):
        raise ReferralAttributionWindowClosedError(_referral_error("window_closed"))

    locked_referrer_account = await _load_account_for_update(
        session, referrer_account.id
    )
    attribution = ReferralAttribution(
        referrer_account_id=locked_referrer_account.id,
        referred_account_id=referred_account.id,
        referral_code=normalized_referral_code,
    )
    referred_account.referred_by_account_id = locked_referrer_account.id
    locked_referrer_account.referrals_count = (
        int(locked_referrer_account.referrals_count) + 1
    )
    session.add(attribution)
    await session.flush()
    await _append_referral_claim_events(
        session,
        referred_account_id=referred_account.id,
        referrer_account_id=locked_referrer_account.id,
        referral_code=normalized_referral_code,
        created=True,
    )
    return ReferralClaimResult(attribution=attribution, created=True)


async def record_telegram_referral_intent(
    session: AsyncSession,
    *,
    telegram_id: int,
    referral_code: str,
) -> TelegramReferralIntent:
    normalized_referral_code = _normalize_referral_code(referral_code)
    if await _get_account_by_referral_code(session, normalized_referral_code) is None:
        log_audit_event(
            "referral.intent.record",
            outcome="failure",
            category="business",
            telegram_id=telegram_id,
            referral_code=normalized_referral_code,
            reason="referral_code_not_found",
        )
        raise ReferralCodeNotFoundError(_referral_error("code_not_found"))

    intent = await _get_telegram_referral_intent_by_telegram_id(
        session,
        telegram_id,
        for_update=True,
    )
    if intent is None:
        intent = TelegramReferralIntent(
            telegram_id=telegram_id,
            referral_code=normalized_referral_code,
            status="pending",
        )
        session.add(intent)
    else:
        intent.referral_code = normalized_referral_code
        intent.status = "pending"
        intent.result_reason = None
        intent.account_id = None
        intent.consumed_at = None
        intent.updated_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(intent)
    log_audit_event(
        "referral.intent.record",
        outcome="success",
        category="business",
        telegram_id=telegram_id,
        referral_code=normalized_referral_code,
        status=intent.status,
    )
    return intent


async def apply_telegram_referral_intent(
    session: AsyncSession,
    *,
    telegram_id: int,
    account_id: uuid.UUID,
) -> TelegramReferralIntentResult | None:
    intent = await _get_telegram_referral_intent_by_telegram_id(
        session,
        telegram_id,
        for_update=True,
    )
    if intent is None or intent.status != "pending":
        return None

    intent.account_id = account_id
    intent.consumed_at = datetime.now(UTC)

    try:
        claim_result = await claim_referral_code(
            session,
            account_id=account_id,
            referral_code=intent.referral_code,
        )
    except ReferralCodeNotFoundError:
        intent.status = "rejected"
        intent.result_reason = "referral_code_not_found"
        await append_account_event(
            session,
            account_id=account_id,
            actor_account_id=account_id,
            event_type="referral.intent.apply",
            outcome="failure",
            source="api",
            payload={
                "telegram_id": telegram_id,
                "referral_code": intent.referral_code,
                "reason": intent.result_reason,
            },
        )
        await session.commit()
        log_audit_event(
            "referral.intent.apply",
            outcome="failure",
            category="business",
            telegram_id=telegram_id,
            account_id=account_id,
            referral_code=intent.referral_code,
            reason=intent.result_reason,
        )
        return TelegramReferralIntentResult(
            applied=False, created=False, reason=intent.result_reason
        )
    except ReferralSelfAttributionError:
        intent.status = "rejected"
        intent.result_reason = "self_referral"
        await append_account_event(
            session,
            account_id=account_id,
            actor_account_id=account_id,
            event_type="referral.intent.apply",
            outcome="failure",
            source="api",
            payload={
                "telegram_id": telegram_id,
                "referral_code": intent.referral_code,
                "reason": intent.result_reason,
            },
        )
        await session.commit()
        log_audit_event(
            "referral.intent.apply",
            outcome="failure",
            category="business",
            telegram_id=telegram_id,
            account_id=account_id,
            referral_code=intent.referral_code,
            reason=intent.result_reason,
        )
        return TelegramReferralIntentResult(
            applied=False, created=False, reason=intent.result_reason
        )
    except ReferralAlreadyAttributedError:
        intent.status = "rejected"
        intent.result_reason = "already_claimed"
        await append_account_event(
            session,
            account_id=account_id,
            actor_account_id=account_id,
            event_type="referral.intent.apply",
            outcome="failure",
            source="api",
            payload={
                "telegram_id": telegram_id,
                "referral_code": intent.referral_code,
                "reason": intent.result_reason,
            },
        )
        await session.commit()
        log_audit_event(
            "referral.intent.apply",
            outcome="failure",
            category="business",
            telegram_id=telegram_id,
            account_id=account_id,
            referral_code=intent.referral_code,
            reason=intent.result_reason,
        )
        return TelegramReferralIntentResult(
            applied=False, created=False, reason=intent.result_reason
        )
    except ReferralAttributionWindowClosedError:
        intent.status = "rejected"
        intent.result_reason = "window_closed"
        await append_account_event(
            session,
            account_id=account_id,
            actor_account_id=account_id,
            event_type="referral.intent.apply",
            outcome="failure",
            source="api",
            payload={
                "telegram_id": telegram_id,
                "referral_code": intent.referral_code,
                "reason": intent.result_reason,
            },
        )
        await session.commit()
        log_audit_event(
            "referral.intent.apply",
            outcome="failure",
            category="business",
            telegram_id=telegram_id,
            account_id=account_id,
            referral_code=intent.referral_code,
            reason=intent.result_reason,
        )
        return TelegramReferralIntentResult(
            applied=False, created=False, reason=intent.result_reason
        )

    intent.status = "applied" if claim_result.created else "noop"
    intent.result_reason = None if claim_result.created else "already_applied"
    await append_account_event(
        session,
        account_id=account_id,
        actor_account_id=account_id,
        event_type="referral.intent.apply",
        source="api",
        payload={
            "telegram_id": telegram_id,
            "referral_code": intent.referral_code,
            "applied": claim_result.created,
            "created": claim_result.created,
            "reason": intent.result_reason,
            "referrer_account_id": claim_result.attribution.referrer_account_id,
        },
    )
    await session.commit()
    log_audit_event(
        "referral.intent.apply",
        outcome="success",
        category="business",
        telegram_id=telegram_id,
        account_id=account_id,
        referral_code=intent.referral_code,
        applied=claim_result.created,
        created=claim_result.created,
        reason=intent.result_reason,
        referrer_account_id=claim_result.attribution.referrer_account_id,
    )
    return TelegramReferralIntentResult(
        applied=claim_result.created,
        created=claim_result.created,
        reason=intent.result_reason,
    )


async def apply_first_referral_reward_for_grant(
    session: AsyncSession,
    *,
    grant: SubscriptionGrant,
) -> ReferralReward | None:
    if grant.purchase_source not in PAID_REFERRAL_PURCHASE_SOURCES:
        return None

    if grant.id is None:
        raise ReferralServiceError(
            "subscription grant must be flushed before referral reward"
        )

    existing_reward = await _get_referral_reward_by_grant_id(
        session, grant.id, for_update=True
    )
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

    referrer_account = await _load_account_for_update(
        session, attribution.referrer_account_id
    )
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
    referrer_account.referral_earnings = (
        int(referrer_account.referral_earnings) + reward_amount
    )

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
    await append_account_event(
        session,
        account_id=referrer_account.id,
        actor_account_id=grant.account_id,
        event_type="referral.reward.granted",
        source="system",
        payload={
            "reward_id": reward.id,
            "referred_account_id": grant.account_id,
            "subscription_grant_id": grant.id,
            "reward_amount": reward_amount,
            "purchase_amount_rub": purchase_amount_rub,
            "reward_rate": float(reward_rate),
        },
    )
    await notify_referral_reward_received(session, reward=reward)
    return reward


async def get_referral_summary(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
) -> ReferralSummary:
    account = await session.get(Account, account_id)
    if account is None:
        raise ReferralServiceError(_referral_error("account_not_found"))

    return ReferralSummary(
        referral_code=account.referral_code or "",
        referrals_count=int(account.referrals_count),
        referral_earnings=int(account.referral_earnings),
        available_for_withdraw=(
            await get_withdrawal_availability(session, account=account)
        ).available_for_withdraw,
        effective_reward_rate=float(get_effective_referral_reward_rate(account)),
    )


def _build_referral_feed_filters(
    *,
    account_id: uuid.UUID,
    status_filter: ReferralFeedStatus,
) -> list[object]:
    filters: list[object] = [ReferralAttribution.referrer_account_id == account_id]
    if status_filter == "active":
        filters.append(ReferralReward.id.is_not(None))
    elif status_filter == "pending":
        filters.append(ReferralReward.id.is_(None))
    return filters


def _referral_feed_order_by(status_filter: ReferralFeedStatus) -> tuple[object, ...]:
    if status_filter == "active":
        return (
            ReferralReward.created_at.desc(),
            ReferralAttribution.created_at.desc(),
            ReferralAttribution.id.desc(),
        )
    return (
        ReferralAttribution.created_at.desc(),
        ReferralAttribution.id.desc(),
    )


async def get_referral_feed(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    limit: int,
    offset: int,
    status_filter: ReferralFeedStatus | None = None,
) -> ReferralFeedPage:
    account = await session.get(Account, account_id)
    if account is None:
        raise ReferralServiceError(_referral_error("account_not_found"))

    resolved_status_filter = _normalize_referral_feed_status(status_filter)
    filters = _build_referral_feed_filters(
        account_id=account.id,
        status_filter=resolved_status_filter,
    )

    total = await session.scalar(
        select(func.count(ReferralAttribution.id))
        .select_from(ReferralAttribution)
        .outerjoin(
            ReferralReward, ReferralReward.attribution_id == ReferralAttribution.id
        )
        .where(*filters)
    )

    referred_account = aliased(Account)
    result = await session.execute(
        select(ReferralAttribution, referred_account, ReferralReward)
        .outerjoin(
            referred_account,
            referred_account.id == ReferralAttribution.referred_account_id,
        )
        .outerjoin(
            ReferralReward, ReferralReward.attribution_id == ReferralAttribution.id
        )
        .where(*filters)
        .order_by(*_referral_feed_order_by(resolved_status_filter))
        .limit(limit)
        .offset(offset)
    )

    items = [
        ReferralSummaryItem(
            referred_account_id=attribution.referred_account_id,
            display_name=_display_name_for_referral(referred),
            created_at=attribution.created_at,
            reward_amount=0 if reward is None else int(reward.reward_amount),
            status="pending" if reward is None else "active",
        )
        for attribution, referred, reward in result.all()
    ]

    return ReferralFeedPage(
        items=items,
        total=int(total or 0),
        limit=limit,
        offset=offset,
        status_filter=resolved_status_filter,
    )
