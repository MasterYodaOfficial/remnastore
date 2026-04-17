from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin
from app.api.errors import api_error_from_exception
from app.db.models import Admin
from app.db.session import get_session
from app.schemas.admin import (
    AdminSubscriptionPlanCreateRequest,
    AdminSubscriptionPlanResponse,
    AdminSubscriptionPlanUpdateRequest,
)
from app.services.admin_plans import (
    create_admin_subscription_plan,
    delete_admin_subscription_plan,
    list_admin_subscription_plans,
    update_admin_subscription_plan,
)
from app.services.plans import SubscriptionPlanError

router = APIRouter()


def _serialize_subscription_plan(plan) -> AdminSubscriptionPlanResponse:
    return AdminSubscriptionPlanResponse(
        code=plan.code,
        name=plan.name,
        price_rub=plan.price_rub,
        price_stars=plan.price_stars,
        duration_days=plan.duration_days,
        features=list(plan.features),
        device_limit=plan.device_limit,
        popular=plan.popular,
    )


@router.get("", response_model=list[AdminSubscriptionPlanResponse])
async def list_subscription_plans(
    _: Admin = Depends(get_current_admin),
) -> list[AdminSubscriptionPlanResponse]:
    plans = await list_admin_subscription_plans()
    return [_serialize_subscription_plan(plan) for plan in plans]


@router.post("", response_model=AdminSubscriptionPlanResponse)
async def create_subscription_plan(
    payload: AdminSubscriptionPlanCreateRequest,
    _: Admin = Depends(get_current_admin),
) -> AdminSubscriptionPlanResponse:
    try:
        plan = await create_admin_subscription_plan(
            code=payload.code,
            name=payload.name,
            price_rub=payload.price_rub,
            price_stars=payload.price_stars,
            duration_days=payload.duration_days,
            features=payload.features,
            device_limit=payload.device_limit,
            popular=payload.popular,
        )
    except SubscriptionPlanError as exc:
        if exc.code == "admin_plan_validation_failed":
            raise api_error_from_exception(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                exc,
            ) from exc
        raise api_error_from_exception(status.HTTP_409_CONFLICT, exc) from exc
    return _serialize_subscription_plan(plan)


@router.put("/{plan_code}", response_model=AdminSubscriptionPlanResponse)
async def update_subscription_plan(
    payload: AdminSubscriptionPlanUpdateRequest,
    plan_code: str = Path(..., min_length=1, max_length=64),
    _: Admin = Depends(get_current_admin),
) -> AdminSubscriptionPlanResponse:
    try:
        plan = await update_admin_subscription_plan(
            plan_code,
            name=payload.name,
            price_rub=payload.price_rub,
            price_stars=payload.price_stars,
            duration_days=payload.duration_days,
            features=payload.features,
            device_limit=payload.device_limit,
            popular=payload.popular,
        )
    except SubscriptionPlanError as exc:
        if exc.code == "admin_plan_not_found":
            raise api_error_from_exception(
                status.HTTP_404_NOT_FOUND,
                exc,
            ) from exc
        if exc.code == "admin_plan_validation_failed":
            raise api_error_from_exception(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                exc,
            ) from exc
        raise api_error_from_exception(status.HTTP_409_CONFLICT, exc) from exc
    return _serialize_subscription_plan(plan)


@router.delete("/{plan_code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription_plan(
    plan_code: str = Path(..., min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> None:
    try:
        await delete_admin_subscription_plan(session, plan_code=plan_code)
    except SubscriptionPlanError as exc:
        if exc.code == "admin_plan_not_found":
            raise api_error_from_exception(
                status.HTTP_404_NOT_FOUND,
                exc,
            ) from exc
        raise api_error_from_exception(status.HTTP_409_CONFLICT, exc) from exc
