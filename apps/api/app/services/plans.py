from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class SubscriptionPlanError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SubscriptionPlan:
    code: str
    name: str
    price_rub: int
    price_stars: int | None
    duration_days: int
    features: tuple[str, ...]
    popular: bool = False


SUBSCRIPTION_PLANS_FILE = Path(__file__).resolve().parent.parent / "config" / "subscription-plans.json"


def _validate_plan_payload(item: object, *, index: int) -> SubscriptionPlan:
    if not isinstance(item, dict):
        raise SubscriptionPlanError(f"subscription plan #{index + 1} must be an object")

    code = item.get("code")
    name = item.get("name")
    price_rub = item.get("price_rub")
    price_stars = item.get("price_stars")
    duration_days = item.get("duration_days")
    features = item.get("features")
    popular = bool(item.get("popular", False))

    if not isinstance(code, str) or not code.strip():
        raise SubscriptionPlanError(f"subscription plan #{index + 1} has invalid code")
    if not isinstance(name, str) or not name.strip():
        raise SubscriptionPlanError(f"subscription plan {code!r} has invalid name")
    if not isinstance(price_rub, int) or price_rub <= 0:
        raise SubscriptionPlanError(f"subscription plan {code!r} has invalid price_rub")
    if price_stars is not None and (not isinstance(price_stars, int) or price_stars <= 0):
        raise SubscriptionPlanError(f"subscription plan {code!r} has invalid price_stars")
    if not isinstance(duration_days, int) or duration_days <= 0:
        raise SubscriptionPlanError(f"subscription plan {code!r} has invalid duration_days")
    if not isinstance(features, list) or not features or not all(
        isinstance(feature, str) and feature.strip() for feature in features
    ):
        raise SubscriptionPlanError(f"subscription plan {code!r} has invalid features")

    return SubscriptionPlan(
        code=code.strip(),
        name=name.strip(),
        price_rub=price_rub,
        price_stars=price_stars,
        duration_days=duration_days,
        features=tuple(feature.strip() for feature in features),
        popular=popular,
    )


def get_subscription_plans() -> tuple[SubscriptionPlan, ...]:
    try:
        raw_json = SUBSCRIPTION_PLANS_FILE.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SubscriptionPlanError(f"subscription plans file not found: {SUBSCRIPTION_PLANS_FILE}") from exc
    except OSError as exc:
        raise SubscriptionPlanError(f"failed to read subscription plans file: {SUBSCRIPTION_PLANS_FILE}") from exc

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise SubscriptionPlanError(f"subscription plans file contains invalid JSON: {SUBSCRIPTION_PLANS_FILE}") from exc

    if not isinstance(payload, list) or not payload:
        raise SubscriptionPlanError("subscription plans file must contain a non-empty array")

    plans = tuple(_validate_plan_payload(item, index=index) for index, item in enumerate(payload))
    codes = {plan.code for plan in plans}
    if len(codes) != len(plans):
        raise SubscriptionPlanError("subscription plans file contains duplicate plan codes")
    return plans


def get_subscription_plan(plan_code: str) -> SubscriptionPlan:
    for plan in get_subscription_plans():
        if plan.code == plan_code:
            return plan
    raise SubscriptionPlanError(f"Unknown subscription plan: {plan_code}")
