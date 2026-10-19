from fastapi import APIRouter, Depends
from app.api.errors import api_error_from_exception
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_account
from app.db.models import Account
from app.db.session import get_session
from app.schemas.device import (
    DevicePlanQuoteRequest,
    DevicePurchaseRequest,
    DeviceQuantityRequest,
    DeviceRemoveRequest,
    DeviceRenewalRequest,
    DevicesStateResponse,
)
from app.services.devices import (
    build_renewal_device_quote,
    change_renewal_extra_count,
    get_devices_state,
    purchase_extra_devices,
    quote_device_purchase,
    remove_device,
    _lock_account,
)
from app.services.plans import get_subscription_plan, SubscriptionPlanError
from app.services.promos import quote_plan_promo, PromoServiceError
from app.services.purchases import compute_paid_plan_window

router = APIRouter()


@router.get("", response_model=DevicesStateResponse)
async def read_devices(
    session: AsyncSession = Depends(get_session),
    account: Account = Depends(get_current_account),
):
    return await get_devices_state(session, account=account)


@router.post("/quote")
async def quote_devices(
    payload: DeviceQuantityRequest,
    session: AsyncSession = Depends(get_session),
    account: Account = Depends(get_current_account),
):
    return await quote_device_purchase(
        session, account=account, quantity=payload.quantity
    )


@router.post("/purchase")
async def buy_devices(
    payload: DevicePurchaseRequest,
    session: AsyncSession = Depends(get_session),
    account: Account = Depends(get_current_account),
):
    purchase = await purchase_extra_devices(
        session,
        account=account,
        quote_token=payload.quote_token,
        idempotency_key=payload.idempotency_key,
    )
    return {
        "purchase_id": str(purchase.id),
        "amount_rub": purchase.amount,
        "applied": purchase.applied_at is not None,
        "refunded": purchase.refunded_at is not None,
    }


@router.put("/renewal", status_code=204)
async def set_device_renewal(
    payload: DeviceRenewalRequest,
    session: AsyncSession = Depends(get_session),
    account: Account = Depends(get_current_account),
) -> None:
    await change_renewal_extra_count(
        session, account=account, extra_count=payload.extra_count
    )


@router.post("/remove", status_code=204)
async def delete_device(
    payload: DeviceRemoveRequest,
    session: AsyncSession = Depends(get_session),
    account: Account = Depends(get_current_account),
) -> None:
    await remove_device(session, account=account, hwid=payload.hwid)


@router.post("/reset", status_code=204)
async def reset_devices(
    session: AsyncSession = Depends(get_session),
    account: Account = Depends(get_current_account),
) -> None:
    await remove_device(session, account=account, reset=True)


@router.post("/plans/{plan_code}/quote")
async def quote_plan_devices(
    plan_code: str,
    payload: DevicePlanQuoteRequest,
    session: AsyncSession = Depends(get_session),
    account: Account = Depends(get_current_account),
):
    account = await _lock_account(session, account.id)
    try:
        plan = await get_subscription_plan(session, plan_code)
    except SubscriptionPlanError as exc:
        raise api_error_from_exception(404, exc) from exc
    base_amount, duration_days = plan.price_rub, plan.duration_days
    if payload.promo_code:
        try:
            promo = await quote_plan_promo(
                session,
                account=account,
                plan_code=plan_code,
                base_amount=base_amount,
                currency="RUB",
                code=payload.promo_code,
            )
        except PromoServiceError as exc:
            raise api_error_from_exception(400, exc) from exc
        base_amount, duration_days = promo.final_amount, promo.final_duration_days
    quote = await build_renewal_device_quote(
        session,
        account=account,
        plan=plan,
        extra_devices=payload.extra_devices,
        duration_days=duration_days,
    )
    _, expires_at = compute_paid_plan_window(account, duration_days=duration_days)
    await session.commit()
    return {
        "extra_devices": quote["extra_count"],
        "extra_device_price_rub": plan.extra_device_price_rub,
        "extra_amount_rub": quote["extra_amount_rub"],
        "base_amount_rub": base_amount,
        "total_amount_rub": base_amount + quote["extra_amount_rub"],
        "refund_rub": quote["refund_rub"],
        "expires_at": expires_at,
        "base_limit": quote["base_limit"],
        "limit": 0
        if quote["base_limit"] == 0
        else quote["base_limit"] + quote["extra_count"],
    }
