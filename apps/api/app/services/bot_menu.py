from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.bot import (
    BotDashboardAccountSummary,
    BotDashboardReferralSummary,
    BotDashboardResponse,
    BotPlanPaymentResponse,
    BotPlanListResponse,
)
from app.schemas.payment import SubscriptionPlanResponse
from app.services.accounts import get_account_by_telegram_id
from app.services.payments import (
    create_telegram_stars_plan_purchase_payment,
    create_yookassa_plan_purchase_payment,
)
from app.services.plans import get_subscription_plans
from app.services.referrals import get_referral_summary
from app.services.subscriptions import activate_trial, get_current_subscription, get_trial_eligibility


class BotMenuServiceError(Exception):
    pass


class BotMenuAccountNotFoundError(BotMenuServiceError):
    pass


@dataclass(frozen=True, slots=True)
class BotMenuContext:
    telegram_id: int


def _build_telegram_bot_return_url() -> str | None:
    username = settings.telegram_bot_username.strip().removeprefix("@")
    if not username:
        return None
    return f"https://t.me/{username}"


async def get_bot_dashboard(
    session: AsyncSession,
    *,
    telegram_id: int,
) -> BotDashboardResponse:
    account = await get_account_by_telegram_id(session, telegram_id=telegram_id)
    if account is None:
        return BotDashboardResponse(
            telegram_id=telegram_id,
            exists=False,
            account=None,
            subscription=None,
            trial_eligibility=None,
            referral=None,
        )

    subscription = await get_current_subscription(account)
    trial_eligibility = await get_trial_eligibility(session, account=account)
    referral_summary = await get_referral_summary(session, account_id=account.id)

    return BotDashboardResponse(
        telegram_id=telegram_id,
        exists=True,
        account=BotDashboardAccountSummary(
            telegram_id=telegram_id,
            display_name=account.display_name or account.first_name or account.username,
            locale=account.locale,
            balance=int(account.balance),
        ),
        subscription=subscription,
        trial_eligibility=trial_eligibility,
        referral=BotDashboardReferralSummary(
            referral_code=referral_summary.referral_code,
            referrals_count=referral_summary.referrals_count,
            referral_earnings=referral_summary.referral_earnings,
            available_for_withdraw=referral_summary.available_for_withdraw,
            effective_reward_rate=referral_summary.effective_reward_rate,
        ),
    )


def get_bot_plans() -> BotPlanListResponse:
    return BotPlanListResponse(
        items=[
            SubscriptionPlanResponse(
                code=plan.code,
                name=plan.name,
                price_rub=plan.price_rub,
                price_stars=plan.price_stars,
                duration_days=plan.duration_days,
                features=list(plan.features),
                popular=plan.popular,
            )
            for plan in get_subscription_plans()
        ]
    )


async def activate_trial_for_telegram_account(
    session: AsyncSession,
    *,
    telegram_id: int,
):
    account = await get_account_by_telegram_id(session, telegram_id=telegram_id)
    if account is None:
        raise BotMenuAccountNotFoundError(f"telegram account not found: {telegram_id}")
    return await activate_trial(session, account=account, source="bot")


async def create_telegram_stars_plan_payment_for_telegram_account(
    session: AsyncSession,
    *,
    telegram_id: int,
    plan_code: str,
    idempotency_key: str | None = None,
) -> BotPlanPaymentResponse:
    account = await get_account_by_telegram_id(session, telegram_id=telegram_id)
    if account is None:
        raise BotMenuAccountNotFoundError(f"telegram account not found: {telegram_id}")

    snapshot = await create_telegram_stars_plan_purchase_payment(
        session,
        account=account,
        plan_code=plan_code,
        idempotency_key=idempotency_key,
        source="bot",
    )

    if not snapshot.confirmation_url:
        raise BotMenuServiceError("payment intent does not contain confirmation_url")

    return BotPlanPaymentResponse(
        provider=snapshot.provider,
        plan_code=plan_code,
        provider_payment_id=snapshot.provider_payment_id,
        confirmation_url=snapshot.confirmation_url,
        amount=snapshot.amount,
        currency=snapshot.currency,
        created_at=datetime.now(UTC),
    )


async def create_yookassa_plan_payment_for_telegram_account(
    session: AsyncSession,
    *,
    telegram_id: int,
    plan_code: str,
    success_url: str | None,
    cancel_url: str | None,
    idempotency_key: str | None = None,
) -> BotPlanPaymentResponse:
    account = await get_account_by_telegram_id(session, telegram_id=telegram_id)
    if account is None:
        raise BotMenuAccountNotFoundError(f"telegram account not found: {telegram_id}")

    resolved_success_url = success_url or _build_telegram_bot_return_url()
    snapshot = await create_yookassa_plan_purchase_payment(
        session,
        account=account,
        plan_code=plan_code,
        success_url=resolved_success_url,
        cancel_url=cancel_url,
        idempotency_key=idempotency_key,
        source="bot",
    )

    if not snapshot.confirmation_url:
        raise BotMenuServiceError("payment intent does not contain confirmation_url")

    return BotPlanPaymentResponse(
        provider=snapshot.provider,
        plan_code=plan_code,
        provider_payment_id=snapshot.provider_payment_id,
        confirmation_url=snapshot.confirmation_url,
        amount=snapshot.amount,
        currency=snapshot.currency,
        created_at=datetime.now(UTC),
    )
