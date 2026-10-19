from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import SubscriptionPlanRecord
from app.services.i18n import translate


class SubscriptionPlanError(Exception):
    def __init__(self, detail: str, *, code: str | None = None) -> None:
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True, slots=True)
class SubscriptionPlan:
    code: str
    name: str
    price_rub: int
    price_stars: int | None
    duration_days: int
    features: tuple[str, ...]
    device_limit: int | None = None
    popular: bool = False
    extra_device_price_rub: int | None = None


def _plan_error(key: str) -> str:
    return translate(f"api.plans.errors.{key}")


def _plan_exception(key: str) -> SubscriptionPlanError:
    return SubscriptionPlanError(_plan_error(key), code=key)


def _validate_plan_code(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 64:
        raise SubscriptionPlanError(
            "plan code is required and must be at most 64 characters",
            code="admin_plan_validation_failed",
        )
    allowed_chars = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    )
    if any(char not in allowed_chars for char in normalized):
        raise SubscriptionPlanError(
            "plan code may contain only letters, digits, hyphen, and underscore",
            code="admin_plan_validation_failed",
        )
    return normalized


def _validate_plan_name(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 255:
        raise SubscriptionPlanError(
            "plan name is required and must be at most 255 characters",
            code="admin_plan_validation_failed",
        )
    return normalized


def _validate_plan_features(features: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_feature in features:
        feature = raw_feature.strip()
        if not feature:
            continue
        if len(feature) > 255:
            raise SubscriptionPlanError(
                "plan feature is too long",
                code="admin_plan_validation_failed",
            )
        if feature in seen:
            continue
        normalized.append(feature)
        seen.add(feature)
    if not normalized:
        raise SubscriptionPlanError(
            "plan must contain at least one feature",
            code="admin_plan_validation_failed",
        )
    return tuple(normalized)


def _to_plan(record: SubscriptionPlanRecord) -> SubscriptionPlan:
    return SubscriptionPlan(
        code=record.code,
        name=record.name,
        price_rub=record.price_rub,
        price_stars=record.price_stars,
        duration_days=record.duration_days,
        features=tuple(record.features),
        device_limit=record.device_limit,
        popular=record.popular,
        extra_device_price_rub=record.extra_device_price_rub,
    )


async def get_subscription_plans(session: AsyncSession) -> tuple[SubscriptionPlan, ...]:
    records = await session.scalars(
        select(SubscriptionPlanRecord).order_by(
            SubscriptionPlanRecord.sort_order, SubscriptionPlanRecord.code
        )
    )
    return tuple(_to_plan(record) for record in records)


async def get_subscription_plan(
    session: AsyncSession, plan_code: str
) -> SubscriptionPlan:
    record = await session.scalar(
        select(SubscriptionPlanRecord).where(SubscriptionPlanRecord.code == plan_code)
    )
    if record is None:
        raise _plan_exception("unknown_plan")
    return _to_plan(record)


async def create_subscription_plan(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    price_rub: int,
    price_stars: int | None,
    duration_days: int,
    features: Sequence[str],
    device_limit: int | None,
    popular: bool,
    extra_device_price_rub: int | None = None,
) -> SubscriptionPlan:
    normalized_code = _validate_plan_code(code)
    if extra_device_price_rub is not None and extra_device_price_rub <= 0:
        raise SubscriptionPlanError("extra device price must be positive", code="admin_plan_validation_failed")
    normalized_name = _validate_plan_name(name)
    normalized_features = _validate_plan_features(features)
    if price_rub <= 0:
        raise SubscriptionPlanError(
            "plan price in rubles must be positive",
            code="admin_plan_validation_failed",
        )
    if price_stars is not None and price_stars <= 0:
        raise SubscriptionPlanError(
            "plan price in stars must be positive",
            code="admin_plan_validation_failed",
        )
    if duration_days <= 0:
        raise SubscriptionPlanError(
            "plan duration must be positive",
            code="admin_plan_validation_failed",
        )
    if device_limit is not None and device_limit < 0:
        raise SubscriptionPlanError(
            "device limit must be zero or positive",
            code="admin_plan_validation_failed",
        )

    new_plan = SubscriptionPlan(
        code=normalized_code,
        name=normalized_name,
        price_rub=price_rub,
        price_stars=price_stars,
        duration_days=duration_days,
        features=normalized_features,
        device_limit=device_limit,
        popular=popular,
        extra_device_price_rub=extra_device_price_rub,
    )
    sort_order = await session.scalar(
        select(func.max(SubscriptionPlanRecord.sort_order))
    )
    record = SubscriptionPlanRecord(
        code=new_plan.code,
        name=new_plan.name,
        price_rub=new_plan.price_rub,
        price_stars=new_plan.price_stars,
        duration_days=new_plan.duration_days,
        features=list(new_plan.features),
        device_limit=new_plan.device_limit,
        popular=new_plan.popular,
        extra_device_price_rub=new_plan.extra_device_price_rub,
        sort_order=0 if sort_order is None else sort_order + 1,
    )
    try:
        async with session.begin_nested():
            session.add(record)
            await session.flush()
    except IntegrityError as exc:
        raise SubscriptionPlanError(
            "plan with this code already exists", code="admin_plan_conflict"
        ) from exc
    return new_plan


async def update_subscription_plan(
    session: AsyncSession,
    plan_code: str,
    *,
    name: str,
    price_rub: int,
    price_stars: int | None,
    duration_days: int,
    features: Sequence[str],
    device_limit: int | None,
    popular: bool,
    extra_device_price_rub: int | None = None,
) -> SubscriptionPlan:
    if extra_device_price_rub is not None and extra_device_price_rub <= 0:
        raise SubscriptionPlanError("extra device price must be positive", code="admin_plan_validation_failed")
    normalized_name = _validate_plan_name(name)
    normalized_features = _validate_plan_features(features)
    if price_rub <= 0:
        raise SubscriptionPlanError(
            "plan price in rubles must be positive",
            code="admin_plan_validation_failed",
        )
    if price_stars is not None and price_stars <= 0:
        raise SubscriptionPlanError(
            "plan price in stars must be positive",
            code="admin_plan_validation_failed",
        )
    if duration_days <= 0:
        raise SubscriptionPlanError(
            "plan duration must be positive",
            code="admin_plan_validation_failed",
        )
    if device_limit is not None and device_limit < 0:
        raise SubscriptionPlanError(
            "device limit must be zero or positive",
            code="admin_plan_validation_failed",
        )

    record = await session.scalar(
        select(SubscriptionPlanRecord)
        .where(SubscriptionPlanRecord.code == plan_code)
        .with_for_update()
    )
    if record is None:
        raise SubscriptionPlanError("plan not found", code="admin_plan_not_found")
    record.name = normalized_name
    record.price_rub = price_rub
    record.price_stars = price_stars
    record.duration_days = duration_days
    record.features = list(normalized_features)
    record.device_limit = device_limit
    record.popular = popular
    record.extra_device_price_rub = extra_device_price_rub
    await session.flush()
    return _to_plan(record)


async def delete_subscription_plan(session: AsyncSession, plan_code: str) -> None:
    records = list(
        await session.scalars(
            select(SubscriptionPlanRecord)
            .order_by(SubscriptionPlanRecord.code)
            .with_for_update()
        )
    )
    record = next((item for item in records if item.code == plan_code), None)
    if record is None:
        raise SubscriptionPlanError("plan not found", code="admin_plan_not_found")
    if len(records) == 1:
        raise SubscriptionPlanError(
            "at least one plan must remain in the catalog", code="admin_plan_in_use"
        )
    await session.delete(record)
    await session.flush()


def resolve_plan_device_limit(plan: SubscriptionPlan | None) -> int:
    if plan is not None and plan.device_limit is not None:
        return plan.device_limit
    return settings.default_subscription_device_limit
