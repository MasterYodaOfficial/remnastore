from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
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


SUBSCRIPTION_PLANS_FILE = (
    Path(__file__).resolve().parent.parent / "config" / "subscription-plans.json"
)


def _plan_error(key: str) -> str:
    return translate(f"api.plans.errors.{key}")


def _plan_exception(key: str) -> SubscriptionPlanError:
    return SubscriptionPlanError(_plan_error(key), code=key)


def _validate_plan_payload(item: object, *, index: int) -> SubscriptionPlan:
    if not isinstance(item, dict):
        raise _plan_exception("config_unavailable")

    code = item.get("code")
    name = item.get("name")
    price_rub = item.get("price_rub")
    price_stars = item.get("price_stars")
    duration_days = item.get("duration_days")
    features = item.get("features")
    device_limit = item.get("device_limit")
    popular = bool(item.get("popular", False))

    if not isinstance(code, str) or not code.strip():
        raise _plan_exception("config_unavailable")
    if not isinstance(name, str) or not name.strip():
        raise _plan_exception("config_unavailable")
    if not isinstance(price_rub, int) or price_rub <= 0:
        raise _plan_exception("config_unavailable")
    if price_stars is not None and (
        not isinstance(price_stars, int) or price_stars <= 0
    ):
        raise _plan_exception("config_unavailable")
    if not isinstance(duration_days, int) or duration_days <= 0:
        raise _plan_exception("config_unavailable")
    if (
        not isinstance(features, list)
        or not features
        or not all(isinstance(feature, str) and feature.strip() for feature in features)
    ):
        raise _plan_exception("config_unavailable")
    if device_limit is not None and (
        not isinstance(device_limit, int) or device_limit < 0
    ):
        raise _plan_exception("config_unavailable")

    return SubscriptionPlan(
        code=code.strip(),
        name=name.strip(),
        price_rub=price_rub,
        price_stars=price_stars,
        duration_days=duration_days,
        features=tuple(feature.strip() for feature in features),
        device_limit=device_limit,
        popular=popular,
    )


def get_subscription_plans() -> tuple[SubscriptionPlan, ...]:
    try:
        raw_json = SUBSCRIPTION_PLANS_FILE.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise _plan_exception("config_unavailable") from exc
    except OSError as exc:
        raise _plan_exception("config_unavailable") from exc

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise _plan_exception("config_unavailable") from exc

    if not isinstance(payload, list) or not payload:
        raise _plan_exception("config_unavailable")

    plans = tuple(
        _validate_plan_payload(item, index=index) for index, item in enumerate(payload)
    )
    codes = {plan.code for plan in plans}
    if len(codes) != len(plans):
        raise _plan_exception("config_unavailable")
    return plans


def get_subscription_plan(plan_code: str) -> SubscriptionPlan:
    for plan in get_subscription_plans():
        if plan.code == plan_code:
            return plan
    raise _plan_exception("unknown_plan")


def resolve_plan_device_limit(plan: SubscriptionPlan | None) -> int:
    if plan is not None and plan.device_limit is not None:
        return plan.device_limit
    return settings.default_subscription_device_limit
