from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

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
_PLAN_FILE_LOCK = Lock()


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


def _serialize_plan(plan: SubscriptionPlan) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": plan.code,
        "name": plan.name,
        "price_rub": plan.price_rub,
        "price_stars": plan.price_stars,
        "duration_days": plan.duration_days,
        "features": list(plan.features),
    }
    if plan.device_limit is not None:
        payload["device_limit"] = plan.device_limit
    if plan.popular:
        payload["popular"] = True
    return payload


def _validate_plan_payload(item: object, *, index: int) -> SubscriptionPlan:
    del index
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


def _read_subscription_plan_catalog() -> list[SubscriptionPlan]:
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

    plans = [
        _validate_plan_payload(item, index=index) for index, item in enumerate(payload)
    ]
    codes = {plan.code for plan in plans}
    if len(codes) != len(plans):
        raise _plan_exception("config_unavailable")
    return plans


def _write_subscription_plan_catalog(plans: Sequence[SubscriptionPlan]) -> None:
    payload = [_serialize_plan(plan) for plan in plans]
    try:
        SUBSCRIPTION_PLANS_FILE.write_text(
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise _plan_exception("config_unavailable") from exc


def get_subscription_plans() -> tuple[SubscriptionPlan, ...]:
    with _PLAN_FILE_LOCK:
        return tuple(_read_subscription_plan_catalog())


def get_subscription_plan(plan_code: str) -> SubscriptionPlan:
    for plan in get_subscription_plans():
        if plan.code == plan_code:
            return plan
    raise _plan_exception("unknown_plan")


def create_subscription_plan(
    *,
    code: str,
    name: str,
    price_rub: int,
    price_stars: int | None,
    duration_days: int,
    features: Sequence[str],
    device_limit: int | None,
    popular: bool,
) -> SubscriptionPlan:
    normalized_code = _validate_plan_code(code)
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
    )
    with _PLAN_FILE_LOCK:
        plans = _read_subscription_plan_catalog()
        if any(plan.code == normalized_code for plan in plans):
            raise SubscriptionPlanError(
                "plan with this code already exists",
                code="admin_plan_conflict",
            )
        plans.append(new_plan)
        _write_subscription_plan_catalog(plans)
    return new_plan


def update_subscription_plan(
    plan_code: str,
    *,
    name: str,
    price_rub: int,
    price_stars: int | None,
    duration_days: int,
    features: Sequence[str],
    device_limit: int | None,
    popular: bool,
) -> SubscriptionPlan:
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

    with _PLAN_FILE_LOCK:
        plans = _read_subscription_plan_catalog()
        updated_plan: SubscriptionPlan | None = None
        next_plans: list[SubscriptionPlan] = []
        for plan in plans:
            if plan.code != plan_code:
                next_plans.append(plan)
                continue
            updated_plan = SubscriptionPlan(
                code=plan.code,
                name=normalized_name,
                price_rub=price_rub,
                price_stars=price_stars,
                duration_days=duration_days,
                features=normalized_features,
                device_limit=device_limit,
                popular=popular,
            )
            next_plans.append(updated_plan)
        if updated_plan is None:
            raise SubscriptionPlanError(
                "plan not found",
                code="admin_plan_not_found",
            )
        _write_subscription_plan_catalog(next_plans)
    return updated_plan


def delete_subscription_plan(plan_code: str) -> None:
    with _PLAN_FILE_LOCK:
        plans = _read_subscription_plan_catalog()
        next_plans = [plan for plan in plans if plan.code != plan_code]
        if len(next_plans) == len(plans):
            raise SubscriptionPlanError(
                "plan not found",
                code="admin_plan_not_found",
            )
        if not next_plans:
            raise SubscriptionPlanError(
                "at least one plan must remain in the catalog",
                code="admin_plan_in_use",
            )
        _write_subscription_plan_catalog(next_plans)


def resolve_plan_device_limit(plan: SubscriptionPlan | None) -> int:
    if plan is not None and plan.device_limit is not None:
        return plan.device_limit
    return settings.default_subscription_device_limit
