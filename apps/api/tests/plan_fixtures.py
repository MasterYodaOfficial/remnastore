from dataclasses import asdict

from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.models import SubscriptionPlanRecord
from app.services.plans import SubscriptionPlan

TEST_PLANS = (
    SubscriptionPlan("plan_1w", "1 неделя", 99, 49, 7, ("Доступ ко всем серверам",)),
    SubscriptionPlan("plan_1m", "1 месяц", 199, 99, 30, ("Полный доступ",)),
    SubscriptionPlan("plan_3m", "3 месяца", 560, 279, 90, ("Экономия",), popular=True),
    SubscriptionPlan("plan_6m", "6 месяцев", 990, 499, 180, ("Полный доступ",)),
    SubscriptionPlan("plan_12m", "12 месяцев", 1990, 999, 365, ("Год доступа",)),
)
PLAN_1M = TEST_PLANS[1]


async def seed_subscription_plans(
    connection: AsyncConnection, plans: tuple[SubscriptionPlan, ...] = TEST_PLANS
) -> None:
    await connection.execute(
        SubscriptionPlanRecord.__table__.insert(),
        [
            {**asdict(plan), "features": list(plan.features), "sort_order": index}
            for index, plan in enumerate(plans)
        ],
    )
