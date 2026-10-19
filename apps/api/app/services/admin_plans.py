from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, PromoCampaign, SubscriptionGrant
from app.services.plans import (
    SubscriptionPlan,
    SubscriptionPlanError,
    create_subscription_plan,
    delete_subscription_plan,
    get_subscription_plans,
    update_subscription_plan,
)


async def list_admin_subscription_plans(
    session: AsyncSession,
) -> list[SubscriptionPlan]:
    return list(await get_subscription_plans(session))


async def create_admin_subscription_plan(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    price_rub: int,
    price_stars: int | None,
    duration_days: int,
    features: list[str],
    device_limit: int | None,
    popular: bool,
) -> SubscriptionPlan:
    plan = await create_subscription_plan(
        session,
        code=code,
        name=name,
        price_rub=price_rub,
        price_stars=price_stars,
        duration_days=duration_days,
        features=features,
        device_limit=device_limit,
        popular=popular,
    )
    await session.commit()
    return plan


async def update_admin_subscription_plan(
    session: AsyncSession,
    plan_code: str,
    *,
    name: str,
    price_rub: int,
    price_stars: int | None,
    duration_days: int,
    features: list[str],
    device_limit: int | None,
    popular: bool,
) -> SubscriptionPlan:
    plan = await update_subscription_plan(
        session,
        plan_code,
        name=name,
        price_rub=price_rub,
        price_stars=price_stars,
        duration_days=duration_days,
        features=features,
        device_limit=device_limit,
        popular=popular,
    )
    await session.commit()
    return plan


async def delete_admin_subscription_plan(
    session: AsyncSession,
    *,
    plan_code: str,
) -> None:
    payments_count = await session.scalar(
        select(func.count()).select_from(Payment).where(Payment.plan_code == plan_code)
    )
    if payments_count:
        raise SubscriptionPlanError(
            "plan is already used in payments",
            code="admin_plan_in_use",
        )

    grants_count = await session.scalar(
        select(func.count())
        .select_from(SubscriptionGrant)
        .where(SubscriptionGrant.plan_code == plan_code)
    )
    if grants_count:
        raise SubscriptionPlanError(
            "plan is already used in subscription grants",
            code="admin_plan_in_use",
        )

    promo_plan_rows = await session.execute(
        select(PromoCampaign.plan_codes).where(PromoCampaign.plan_codes.is_not(None))
    )
    for row in promo_plan_rows:
        plan_codes = row[0] or []
        if isinstance(plan_codes, list) and plan_code in plan_codes:
            raise SubscriptionPlanError(
                "plan is already used in promo campaigns",
                code="admin_plan_in_use",
            )

    await delete_subscription_plan(session, plan_code)
    await session.commit()
