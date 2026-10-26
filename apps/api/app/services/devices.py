from __future__ import annotations

from datetime import UTC, datetime, timedelta
from fractions import Fraction
from hashlib import sha256
from math import ceil
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import TokenError, create_access_token, decode_access_token
from app.db.models import (
    Account,
    AccountDeviceSettings,
    AccountStatus,
    DevicePrepayment,
    DevicePricingPeriod,
    DevicePurchase,
    LedgerEntryType,
    Payment,
    SubscriptionGrant,
    SubscriptionPlanRecord,
)
from app.domain.payments import PaymentFlowType, PaymentStatus
from app.integrations.remnawave import (
    RemnawaveConfigurationError,
    RemnawaveRequestError,
    get_remnawave_gateway,
)
from app.services.account_events import append_account_event
from app.services.ledger import (
    InsufficientFundsError,
    apply_credit_in_transaction,
    apply_debit_in_transaction,
    clear_account_cache,
)
from app.services.plans import SubscriptionPlan, resolve_plan_device_limit

MAX_EXTRA_DEVICES = 100
PENDING_STATUSES = (
    PaymentStatus.CREATED,
    PaymentStatus.PENDING,
    PaymentStatus.REQUIRES_ACTION,
)


class DeviceServiceError(Exception):
    def __init__(
        self,
        detail: str,
        code: str,
        status_code: int = 409,
        *,
        panel_limit: int | None = None,
    ):
        super().__init__(detail)
        self.code = code
        self.status_code = status_code
        self.panel_limit = panel_limit


def now_utc() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _seconds(delta: timedelta) -> int:
    return max(0, int(delta.total_seconds() * 1_000_000))


def _active(account: Account, now: datetime | None = None) -> bool:
    return bool(
        account.subscription_expires_at
        and aware(account.subscription_expires_at) > (now or now_utc())
        and account.subscription_status == "ACTIVE"
    )


def _check_account(account: Account) -> None:
    if account.status == AccountStatus.BLOCKED:
        raise DeviceServiceError("Аккаунт заблокирован.", "account_blocked", 403)


def _gateway(factory=None):
    try:
        return (factory or get_remnawave_gateway)()
    except RemnawaveConfigurationError as exc:
        raise DeviceServiceError(
            "Управление устройствами временно недоступно.", "devices_unavailable", 503
        ) from exc


async def _lock_account(
    session: AsyncSession, account_id: UUID, *, allow_blocked: bool = False
) -> Account:
    account = await session.scalar(
        select(Account).where(Account.id == account_id).with_for_update()
    )
    if account is None:
        raise DeviceServiceError("Аккаунт не найден.", "account_not_found", 404)
    if not allow_blocked:
        _check_account(account)
    return account


async def ensure_no_pending_device_purchase(
    session: AsyncSession, account_id: UUID
) -> None:
    pending = await session.scalar(
        select(DevicePurchase.id)
        .where(
            DevicePurchase.account_id == account_id,
            DevicePurchase.applied_at.is_(None),
            DevicePurchase.refunded_at.is_(None),
        )
        .limit(1)
    )
    if pending:
        raise DeviceServiceError(
            "Предыдущая покупка оплачена. Дождитесь обновления лимита.",
            "devices_sync_pending",
        )


async def ensure_no_pending_plan_purchase(
    session: AsyncSession, account_id: UUID
) -> None:
    pending = await session.scalar(
        select(Payment.id)
        .where(
            Payment.account_id == account_id,
            Payment.flow_type == PaymentFlowType.DIRECT_PLAN_PURCHASE,
            Payment.status.in_(PENDING_STATUSES),
        )
        .limit(1)
    )
    grant = await session.scalar(
        select(SubscriptionGrant.id)
        .where(
            SubscriptionGrant.account_id == account_id,
            SubscriptionGrant.applied_at.is_(None),
        )
        .limit(1)
    )
    if pending or grant:
        raise DeviceServiceError(
            "Сначала завершите или отмените оплату подписки.",
            "devices_plan_payment_pending",
        )


async def prepare_device_checkout(session: AsyncSession, account_id: UUID) -> Account:
    account = await _lock_account(session, account_id)
    await ensure_no_pending_device_purchase(session, account_id)
    await ensure_no_pending_plan_purchase(session, account_id)
    return account


async def get_device_settings(
    session: AsyncSession,
    account: Account,
    *,
    gateway_factory=None,
    refresh_remote: bool = False,
    source: str = "api",
) -> AccountDeviceSettings:
    device_settings = await session.get(AccountDeviceSettings, account.id)
    if device_settings is not None and not refresh_remote:
        return device_settings
    gateway = _gateway(gateway_factory)
    try:
        remote = await gateway.get_user_by_uuid(
            account.remnawave_user_uuid or account.id
        )
    except RemnawaveRequestError as exc:
        raise DeviceServiceError(
            "Не удалось получить устройства. Попробуйте ещё раз.",
            "devices_unavailable",
            502,
        ) from exc
    if remote is None:
        raise DeviceServiceError(
            "Не удалось найти подписку в панели. Обновите данные или обратитесь в поддержку.",
            "devices_unavailable",
            502,
        )
    try:
        limit = (
            remote.hwid_device_limit
            if remote.hwid_device_limit is not None
            else await gateway.resolve_hwid_device_limit(remote)
        )
    except RemnawaveRequestError as exc:
        raise DeviceServiceError(
            "Не удалось обновить лимит устройств. Попробуйте ещё раз.",
            "devices_unavailable",
            502,
        ) from exc
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise DeviceServiceError(
            "Панель вернула некорректный лимит устройств.", "devices_unavailable", 502
        )
    if device_settings is not None:
        await apply_remote_device_limit(
            session,
            account=account,
            device_settings=device_settings,
            limit=limit,
            source=source,
        )
        return device_settings
    # Existing limits, including manual overrides and unlimited access, remain intact.
    device_settings = AccountDeviceSettings(
        account_id=account.id,
        base_limit=limit,
        extra_count=0,
        renewal_extra_count=0,
        revision=0,
    )
    session.add(device_settings)
    await session.flush()
    return device_settings


async def device_limit_sync_pending(session: AsyncSession, account_id: UUID) -> bool:
    purchase = await session.scalar(
        select(DevicePurchase.id)
        .where(
            DevicePurchase.account_id == account_id,
            DevicePurchase.applied_at.is_(None),
            DevicePurchase.refunded_at.is_(None),
        )
        .limit(1)
    )
    grant = await session.scalar(
        select(SubscriptionGrant.id)
        .where(
            SubscriptionGrant.account_id == account_id,
            SubscriptionGrant.applied_at.is_(None),
        )
        .limit(1)
    )
    return purchase is not None or grant is not None


async def apply_remote_device_limit(
    session: AsyncSession,
    *,
    account: Account,
    device_settings: AccountDeviceSettings,
    limit: int,
    source: str,
) -> None:
    # The panel stores a TOTAL, not a base quota. Never add paid seats twice.
    base = 0 if limit == 0 else limit - device_settings.extra_count
    if limit and base <= 0:
        raise DeviceServiceError(
            "Лимит в панели не вмещает базовую квоту и оплаченные дополнительные устройства. Обратитесь в поддержку.",
            "devices_limit_conflict",
            panel_limit=limit,
        )
    if base == device_settings.base_limit:
        return
    previous = device_settings.base_limit
    device_settings.base_limit = base
    device_settings.revision += 1
    await append_account_event(
        session,
        account_id=account.id,
        event_type="devices.limit_synced",
        source=source,
        payload={
            "old_base_limit": previous,
            "base_limit": base,
            "extra_count": device_settings.extra_count,
            "panel_limit": limit,
            "limit_source": "remnawave",
            "revision": device_settings.revision,
        },
    )


async def sync_existing_device_limit(
    session: AsyncSession,
    *,
    account: Account,
    source: str,
    gateway_factory=None,
) -> None:
    """Use fresh panel data; an old webhook body cannot revert a newer limit."""
    existing = await session.get(AccountDeviceSettings, account.id)
    if existing is None or await device_limit_sync_pending(session, account.id):
        return
    try:
        await get_device_settings(
            session,
            account,
            gateway_factory=gateway_factory,
            refresh_remote=True,
            source=source,
        )
    except DeviceServiceError as exc:
        await append_account_event(
            session,
            account_id=account.id,
            event_type="devices.limit_sync_failed",
            source=source,
            outcome="failure",
            payload={"error_code": exc.code, "panel_limit": exc.panel_limit},
        )


async def snapshot_device_pricing(
    session: AsyncSession,
    grant: SubscriptionGrant,
    plan: SubscriptionPlan | None = None,
) -> None:
    existing = await session.scalar(
        select(DevicePricingPeriod).where(DevicePricingPeriod.grant_id == grant.id)
    )
    if existing and existing.extra_device_price_rub is not None:
        return
    metadata = grant.device_metadata or {}
    if metadata.get("period_price_rub") is not None:
        price = metadata["period_price_rub"]
    elif plan is not None:
        price = getattr(plan, "extra_device_price_rub", None)
    else:
        record = await session.get(SubscriptionPlanRecord, grant.plan_code)
        price = record.extra_device_price_rub if record else None
        if record is None:
            previous = await session.scalar(
                select(DevicePricingPeriod)
                .where(
                    DevicePricingPeriod.account_id == grant.account_id,
                    DevicePricingPeriod.ends_at <= grant.base_expires_at,
                    DevicePricingPeriod.extra_device_price_rub.is_not(None),
                )
                .order_by(DevicePricingPeriod.ends_at.desc())
                .limit(1)
            )
            if previous is not None:
                price = ceil(
                    Fraction(
                        previous.extra_device_price_rub
                        * _seconds(
                            aware(grant.target_expires_at)
                            - aware(grant.base_expires_at)
                        ),
                        _seconds(aware(previous.ends_at) - aware(previous.starts_at)),
                    )
                )
    if existing:
        # A disabled price can be configured later; an actual quoted rate is immutable.
        existing.extra_device_price_rub = price
        await session.flush()
        return
    session.add(
        DevicePricingPeriod(
            account_id=grant.account_id,
            grant_id=grant.id,
            starts_at=grant.base_expires_at,
            ends_at=grant.target_expires_at,
            extra_device_price_rub=price,
        )
    )
    await session.flush()


async def _seed_pricing(session: AsyncSession, account: Account) -> None:
    grants = list(
        await session.scalars(
            select(SubscriptionGrant).where(
                SubscriptionGrant.account_id == account.id,
                SubscriptionGrant.applied_at.is_not(None),
                SubscriptionGrant.target_expires_at > now_utc(),
            )
        )
    )
    for grant in grants:
        await snapshot_device_pricing(session, grant)


async def _remaining_allocations(
    session: AsyncSession, account: Account, quantity: int, *, now: datetime
) -> list[dict]:
    if quantity <= 0 or not account.subscription_expires_at:
        return []
    end = aware(account.subscription_expires_at)
    if end <= now:
        return []
    await _seed_pricing(session, account)
    periods = list(
        await session.scalars(
            select(DevicePricingPeriod).where(
                DevicePricingPeriod.account_id == account.id,
                DevicePricingPeriod.ends_at > now,
            )
        )
    )
    boundaries = {now, end}
    for period in periods:
        boundaries.add(max(now, min(end, aware(period.starts_at))))
        boundaries.add(max(now, min(end, aware(period.ends_at))))
    points = sorted(boundaries)
    total = Fraction(0)
    result = []
    for start, finish in zip(points, points[1:]):
        candidates = [
            p
            for p in periods
            if aware(p.starts_at) <= start and aware(p.ends_at) >= finish
        ]
        period = (
            max(candidates, key=lambda p: (aware(p.starts_at), p.id))
            if candidates
            else None
        )
        if period is None or period.extra_device_price_rub is None:
            raise DeviceServiceError(
                "Для этого периода ещё не настроена стоимость дополнительных устройств.",
                "devices_pricing_unavailable",
            )
        previous = ceil(total)
        total += Fraction(
            period.extra_device_price_rub * quantity * _seconds(finish - start),
            _seconds(aware(period.ends_at) - aware(period.starts_at)),
        )
        result.append(
            {
                "starts_at": start.isoformat(),
                "ends_at": finish.isoformat(),
                "quantity": quantity,
                "amount_rub": ceil(total) - previous,
            }
        )
    return result


async def _refund_allocations(
    session: AsyncSession, account_id: UUID, target_count: int, *, now: datetime
) -> list[dict]:
    result = []
    lots = await session.scalars(
        select(DevicePrepayment)
        .where(
            DevicePrepayment.account_id == account_id,
            DevicePrepayment.ends_at > now,
            DevicePrepayment.active_quantity > 0,
        )
        .with_for_update()
    )
    for lot in lots:
        removed = min(
            max(0, lot.first_extra + lot.active_quantity - 1 - target_count),
            lot.active_quantity,
        )
        if not removed:
            continue
        start, end = aware(lot.starts_at), aware(lot.ends_at)
        remaining = _seconds(end - max(start, now))
        amount = min(
            lot.amount_rub - lot.credited_rub,
            int(
                Fraction(
                    lot.amount_rub * removed * remaining,
                    lot.quantity * _seconds(end - start),
                )
            ),
        )
        result.append({"id": lot.id, "quantity": removed, "amount_rub": amount})
    return result


async def build_renewal_device_quote(
    session: AsyncSession,
    *,
    account: Account,
    plan: SubscriptionPlan,
    currency: str = "RUB",
    extra_devices: int | None = None,
    expected_refund_rub: int | None = None,
    duration_days: int | None = None,
) -> dict:
    _check_account(account)
    device_settings = await session.get(AccountDeviceSettings, account.id)
    if device_settings is not None:
        await ensure_no_pending_device_purchase(session, account.id)
        if await device_limit_sync_pending(session, account.id):
            raise DeviceServiceError(
                "Дождитесь завершения обновления подписки.", "devices_sync_pending"
            )
        device_settings = await get_device_settings(
            session, account, refresh_remote=True
        )
    current = device_settings.extra_count if device_settings and _active(account) else 0
    wanted = (
        extra_devices
        if extra_devices is not None
        else (device_settings.renewal_extra_count if device_settings else 0)
    )
    if extra_devices is None and getattr(plan, "extra_device_price_rub", None) is None:
        wanted = 0
    if wanted and device_settings is None:
        device_settings = await get_device_settings(session, account)
    if wanted < 0 or wanted > MAX_EXTRA_DEVICES:
        raise DeviceServiceError(
            "Укажите допустимое количество дополнительных устройств.",
            "devices_count_invalid",
            422,
        )
    base_limit = (
        device_settings.base_limit
        if device_settings and not account.subscription_is_trial
        else resolve_plan_device_limit(plan)
    )
    if base_limit == 0 and extra_devices is None:
        # An unlimited manual override must not force another paid seat renewal.
        wanted = 0
    if wanted and (
        base_limit == 0 or getattr(plan, "extra_device_price_rub", None) is None
    ):
        raise DeviceServiceError(
            "Для выбранного тарифа дополнительные устройства недоступны.",
            "devices_pricing_unavailable",
        )
    if wanted and currency != "RUB":
        raise DeviceServiceError(
            "Продление с дополнительными устройствами доступно с баланса или картой.",
            "devices_rub_only",
        )
    now = now_utc()
    additions = (
        await _remaining_allocations(
            session, account, max(0, wanted - current), now=now
        )
        if current or wanted
        else []
    )
    refunds = (
        await _refund_allocations(session, account.id, wanted, now=now)
        if current > wanted
        else []
    )
    unit_price = getattr(plan, "extra_device_price_rub", None)
    if expected_refund_rub is not None and expected_refund_rub != sum(
        item["amount_rub"] for item in refunds
    ):
        raise DeviceServiceError(
            "Сумма перерасчёта изменилась. Обновите расчёт перед оплатой.",
            "devices_quote_changed",
        )
    for allocation in additions:
        allocation["first_extra"] = current + 1
    if current > wanted and base_limit:
        try:
            registered = await _gateway().get_hwid_devices(
                account.remnawave_user_uuid or account.id
            )
        except RemnawaveRequestError as exc:
            raise DeviceServiceError(
                "Не удалось проверить устройства. Попробуйте ещё раз.",
                "devices_unavailable",
                502,
            ) from exc
        if len(registered) > base_limit + wanted:
            raise DeviceServiceError(
                "Удалите лишние устройства в настройках, чтобы уменьшить лимит.",
                "devices_remove_excess",
            )
    return {
        "version": 1,
        "revision": device_settings.revision if device_settings else 0,
        "managed": device_settings is not None or wanted > 0,
        "base_limit": base_limit,
        "old_extra_count": current,
        "extra_count": wanted,
        "period_price_rub": unit_price,
        "duration_days": duration_days or plan.duration_days,
        "extra_amount_rub": wanted * (unit_price or 0)
        + sum(p["amount_rub"] for p in additions),
        "refund_rub": sum(p["amount_rub"] for p in refunds),
        "additions": additions,
        "refunds": refunds,
        "quoted_at": now.isoformat(),
    }


async def _add_prepayments(
    session: AsyncSession, account_id: UUID, reference: str, allocations: list[dict]
) -> None:
    for index, item in enumerate(allocations):
        session.add(
            DevicePrepayment(
                account_id=account_id,
                reference=f"{reference}:{index}",
                starts_at=datetime.fromisoformat(item["starts_at"]),
                ends_at=datetime.fromisoformat(item["ends_at"]),
                quantity=item["quantity"],
                active_quantity=item["quantity"],
                first_extra=item.get("first_extra", 1),
                amount_rub=item["amount_rub"],
                credited_rub=0,
            )
        )
    await session.flush()


async def apply_grant_device_entitlements(
    session: AsyncSession,
    *,
    account: Account,
    grant: SubscriptionGrant,
    gateway_factory=None,
) -> None:
    """Called inside the existing durable subscription grant transaction."""
    await snapshot_device_pricing(session, grant)
    quote = grant.device_metadata or {}
    device_settings = await session.get(AccountDeviceSettings, account.id)
    if not quote.get("managed"):
        return
    if device_settings is None:
        device_settings = AccountDeviceSettings(
            account_id=account.id,
            base_limit=quote["base_limit"],
            extra_count=0,
            renewal_extra_count=0,
            revision=0,
        )
        session.add(device_settings)
        await session.flush()
    if device_settings.revision != quote["revision"]:
        raise DeviceServiceError(
            "Параметры устройств изменились. Требуется повторная синхронизация.",
            "devices_quote_changed",
        )
    wanted = quote["extra_count"]
    gateway = _gateway(gateway_factory)
    try:
        total_limit = 0 if quote["base_limit"] == 0 else quote["base_limit"] + wanted
        if wanted < device_settings.extra_count:
            devices = await gateway.get_hwid_devices(
                account.remnawave_user_uuid or account.id
            )
            if total_limit and len(devices) > total_limit:
                raise DeviceServiceError(
                    "Удалите лишние устройства в настройках, чтобы уменьшить лимит.",
                    "devices_remove_excess",
                )
        await gateway.set_hwid_device_limit(
            account.remnawave_user_uuid or account.id, total_limit
        )
    except RemnawaveRequestError as exc:
        raise DeviceServiceError(
            "Оплата получена. Обновляем лимит устройств.", "devices_sync_pending", 502
        ) from exc
    for item in quote["refunds"]:
        lot = await session.get(DevicePrepayment, item["id"])
        lot.active_quantity -= item["quantity"]
        lot.credited_rub += item["amount_rub"]
    if quote["refund_rub"]:
        await apply_credit_in_transaction(
            session,
            account_id=account.id,
            amount=quote["refund_rub"],
            entry_type=LedgerEntryType.REFUND,
            reference_type="device_renewal",
            reference_id=str(grant.id),
            comment="Перерасчёт дополнительных устройств",
            idempotency_key=f"device-renewal:{grant.id}:refund",
        )
    allocations = list(quote["additions"])
    if wanted and quote["period_price_rub"]:
        allocations.append(
            {
                "starts_at": aware(grant.base_expires_at).isoformat(),
                "ends_at": aware(grant.target_expires_at).isoformat(),
                "quantity": wanted,
                "amount_rub": wanted * quote["period_price_rub"],
            }
        )
    await _add_prepayments(session, account.id, f"grant:{grant.id}", allocations)
    device_settings.extra_count = wanted
    device_settings.base_limit = quote["base_limit"]
    device_settings.renewal_extra_count = wanted
    device_settings.revision += 1
    await append_account_event(
        session,
        account_id=account.id,
        event_type="devices.subscription_updated",
        source="api",
        payload={
            "extra_count": wanted,
            "limit": total_limit,
            "refund_rub": quote["refund_rub"],
            "grant_id": grant.id,
        },
    )


async def get_devices_state(
    session: AsyncSession, *, account: Account, gateway_factory=None
) -> dict:
    account = await _lock_account(session, account.id)
    pending = await device_limit_sync_pending(session, account.id)
    device_settings = await session.get(AccountDeviceSettings, account.id)
    sync_status = "pending" if pending else "synced"
    panel_limit = None
    gateway = None
    try:
        device_settings = await get_device_settings(
            session,
            account,
            gateway_factory=gateway_factory,
            refresh_remote=not pending,
            source="web",
        )
        if not pending:
            panel_limit = (
                0
                if device_settings.base_limit == 0
                else device_settings.base_limit + device_settings.extra_count
            )
    except DeviceServiceError as exc:
        if device_settings is None:
            raise
        sync_status = (
            "conflict" if exc.code == "devices_limit_conflict" else "unavailable"
        )
        panel_limit = exc.panel_limit
    try:
        gateway = _gateway(gateway_factory)
        devices = (
            await gateway.get_hwid_devices(account.remnawave_user_uuid or account.id)
            if account.remnawave_user_uuid
            else []
        )
    except (RemnawaveRequestError, DeviceServiceError):
        devices = None
        if sync_status == "synced":
            sync_status = "unavailable"
    active = _active(account)
    extra = device_settings.extra_count if active else 0
    available = False
    if active and not account.subscription_is_trial and device_settings.base_limit > 0:
        try:
            await _remaining_allocations(session, account, 1, now=now_utc())
            available = True
        except DeviceServiceError:
            pass
    await session.commit()
    return {
        "base_limit": device_settings.base_limit,
        "extra_count": extra,
        "renewal_extra_count": device_settings.renewal_extra_count,
        "limit": 0
        if device_settings.base_limit == 0
        else device_settings.base_limit + extra,
        "devices": devices,
        "expires_at": account.subscription_expires_at,
        "can_purchase": available
        and sync_status == "synced"
        and extra < MAX_EXTRA_DEVICES,
        "sync_pending": bool(pending),
        "limit_sync_status": sync_status,
        "panel_limit": panel_limit,
        "is_active": active,
    }


async def change_renewal_extra_count(
    session: AsyncSession, *, account: Account, extra_count: int, gateway_factory=None
) -> None:
    account = await _lock_account(session, account.id)
    await ensure_no_pending_device_purchase(session, account.id)
    await ensure_no_pending_plan_purchase(session, account.id)
    device_settings = await get_device_settings(
        session, account, gateway_factory=gateway_factory, refresh_remote=True
    )
    if not 0 <= extra_count <= device_settings.extra_count:
        raise DeviceServiceError(
            "Увеличить лимит можно после оплаты дополнительных устройств.",
            "devices_count_invalid",
            422,
        )
    device_settings.renewal_extra_count = extra_count
    device_settings.revision += 1
    await session.commit()


async def remove_device(
    session: AsyncSession,
    *,
    account: Account,
    hwid: str | None = None,
    reset: bool = False,
    gateway_factory=None,
) -> None:
    account = await _lock_account(session, account.id)
    gateway = _gateway(gateway_factory)
    user_uuid = account.remnawave_user_uuid or account.id
    try:
        if reset:
            await gateway.reset_hwid_devices(user_uuid)
        else:
            devices = await gateway.get_hwid_devices(user_uuid)
            if not any(device["hwid"] == hwid for device in devices):
                raise DeviceServiceError(
                    "Устройство не найдено.", "device_not_found", 404
                )
            await gateway.delete_hwid_device(user_uuid, hwid)
    except RemnawaveRequestError as exc:
        raise DeviceServiceError(
            "Не удалось удалить устройство. Попробуйте ещё раз.",
            "devices_unavailable",
            502,
        ) from exc
    await append_account_event(
        session,
        account_id=account.id,
        actor_account_id=account.id,
        event_type="devices.reset" if reset else "devices.removed",
        source="web",
        payload={},
    )
    await session.commit()


async def quote_device_purchase(
    session: AsyncSession, *, account: Account, quantity: int, gateway_factory=None
) -> dict:
    account = await _lock_account(session, account.id)
    if not _active(account) or account.subscription_is_trial:
        raise DeviceServiceError(
            "Дополнительные устройства доступны с активной платной подпиской.",
            "devices_paid_subscription_required",
        )
    await ensure_no_pending_device_purchase(session, account.id)
    await ensure_no_pending_plan_purchase(session, account.id)
    device_settings = await get_device_settings(
        session, account, gateway_factory=gateway_factory, refresh_remote=True
    )
    if (
        device_settings.base_limit == 0
        or not 1 <= quantity <= MAX_EXTRA_DEVICES - device_settings.extra_count
    ):
        raise DeviceServiceError(
            "Укажите допустимое количество дополнительных устройств.",
            "devices_count_invalid",
            422,
        )
    now = now_utc()
    allocations = await _remaining_allocations(session, account, quantity, now=now)
    payload = {
        "purpose": "device_purchase",
        "account_id": str(account.id),
        "revision": device_settings.revision,
        "quantity": quantity,
        "target_extra_count": device_settings.extra_count + quantity,
        "amount_rub": sum(p["amount_rub"] for p in allocations),
        "allocations": allocations,
        "expires_at": aware(account.subscription_expires_at).isoformat(),
    }
    token = create_access_token(
        payload, secret=f"{settings.jwt_secret}:devices", expires_in_seconds=300
    )
    await session.commit()
    return {
        "quantity": quantity,
        "amount_rub": payload["amount_rub"],
        "limit": device_settings.base_limit + payload["target_extra_count"],
        "expires_at": account.subscription_expires_at,
        "quote_token": token,
    }


async def purchase_extra_devices(
    session: AsyncSession,
    *,
    account: Account,
    quote_token: str,
    idempotency_key: str,
    gateway_factory=None,
) -> DevicePurchase:
    account = await _lock_account(session, account.id)
    existing = await session.scalar(
        select(DevicePurchase).where(DevicePurchase.idempotency_key == idempotency_key)
    )
    if existing is not None:
        if (
            existing.account_id != account.id
            or existing.quote_hash != sha256(quote_token.encode()).hexdigest()
        ):
            raise DeviceServiceError(
                "Ключ покупки уже использован.", "devices_idempotency_conflict"
            )
        return await finalize_device_purchase(
            session, purchase_id=existing.id, gateway_factory=gateway_factory
        )
    try:
        quote = decode_access_token(
            quote_token, secret=f"{settings.jwt_secret}:devices"
        )
    except TokenError as exc:
        raise DeviceServiceError(
            "Расчёт устарел. Рассчитайте стоимость ещё раз.", "devices_quote_expired"
        ) from exc
    if quote.get("purpose") != "device_purchase" or quote.get("account_id") != str(
        account.id
    ):
        raise DeviceServiceError(
            "Недействительный расчёт покупки.", "devices_quote_invalid", 403
        )
    await ensure_no_pending_device_purchase(session, account.id)
    await ensure_no_pending_plan_purchase(session, account.id)
    device_settings = await get_device_settings(
        session, account, gateway_factory=gateway_factory, refresh_remote=True
    )
    if (
        not _active(account)
        or account.subscription_is_trial
        or device_settings.revision != quote["revision"]
        or aware(account.subscription_expires_at).isoformat() != quote["expires_at"]
    ):
        raise DeviceServiceError(
            "Подписка изменилась. Рассчитайте стоимость ещё раз.",
            "devices_quote_changed",
        )
    purchase = DevicePurchase(
        account_id=account.id,
        idempotency_key=idempotency_key,
        quote_hash=sha256(quote_token.encode()).hexdigest(),
        quantity=quote["quantity"],
        target_extra_count=quote["target_extra_count"],
        amount=quote["amount_rub"],
        allocations=quote["allocations"],
        subscription_expires_at=datetime.fromisoformat(quote["expires_at"]),
    )
    session.add(purchase)
    for allocation in purchase.allocations:
        allocation["first_extra"] = purchase.target_extra_count - purchase.quantity + 1
    await session.flush()
    if purchase.amount:
        try:
            await apply_debit_in_transaction(
                session,
                account_id=account.id,
                amount=purchase.amount,
                entry_type=LedgerEntryType.DEVICE_DEBIT,
                reference_type="device_purchase",
                reference_id=str(purchase.id),
                comment="Дополнительные устройства",
                idempotency_key=f"device:{purchase.id}:debit",
            )
        except InsufficientFundsError as exc:
            raise DeviceServiceError(str(exc), "insufficient_funds") from exc
    await session.commit()
    await clear_account_cache(account.id)
    return await finalize_device_purchase(
        session, purchase_id=purchase.id, gateway_factory=gateway_factory
    )


async def finalize_device_purchase(
    session: AsyncSession, *, purchase_id: UUID, gateway_factory=None
) -> DevicePurchase:
    purchase = await session.get(DevicePurchase, purchase_id)
    if purchase is None:
        raise DeviceServiceError(
            "Покупка не найдена.", "device_purchase_not_found", 404
        )
    account = await _lock_account(session, purchase.account_id, allow_blocked=True)
    await session.refresh(purchase)
    if purchase.applied_at or purchase.refunded_at:
        return purchase
    if (
        not _active(account)
        or account.status == AccountStatus.BLOCKED
        or aware(account.subscription_expires_at)
        != aware(purchase.subscription_expires_at)
    ):
        if purchase.amount:
            await apply_credit_in_transaction(
                session,
                account_id=account.id,
                amount=purchase.amount,
                entry_type=LedgerEntryType.REFUND,
                reference_type="device_purchase",
                reference_id=str(purchase.id),
                comment="Возврат за неприменённый лимит устройств",
                idempotency_key=f"device:{purchase.id}:refund",
            )
        purchase.refunded_at = now_utc()
        await session.commit()
        await clear_account_cache(account.id)
        return purchase
    device_settings = await get_device_settings(
        session, account, gateway_factory=gateway_factory
    )
    try:
        await _gateway(gateway_factory).set_hwid_device_limit(
            account.remnawave_user_uuid or account.id,
            device_settings.base_limit + purchase.target_extra_count,
        )
    except (RemnawaveRequestError, DeviceServiceError):
        await session.rollback()
        return await session.get(DevicePurchase, purchase_id)
    await _add_prepayments(
        session, account.id, f"purchase:{purchase.id}", purchase.allocations
    )
    device_settings.extra_count = purchase.target_extra_count
    device_settings.renewal_extra_count = purchase.target_extra_count
    device_settings.revision += 1
    purchase.applied_at = now_utc()
    await append_account_event(
        session,
        account_id=account.id,
        event_type="devices.purchased",
        source="web",
        payload={
            "quantity": purchase.quantity,
            "amount_rub": purchase.amount,
            "purchase_id": str(purchase.id),
        },
    )
    await session.commit()
    await clear_account_cache(account.id)
    return purchase


async def reconcile_device_purchases(
    session: AsyncSession, *, limit: int = 100, gateway_factory=None
) -> int:
    ids = list(
        await session.scalars(
            select(DevicePurchase.id)
            .where(
                DevicePurchase.applied_at.is_(None),
                DevicePurchase.refunded_at.is_(None),
            )
            .order_by(DevicePurchase.created_at)
            .limit(limit)
        )
    )
    applied = 0
    for purchase_id in ids:
        purchase = await finalize_device_purchase(
            session, purchase_id=purchase_id, gateway_factory=gateway_factory
        )
        applied += bool(purchase.applied_at or purchase.refunded_at)
    return applied
