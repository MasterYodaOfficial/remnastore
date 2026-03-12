from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from app.core.config import settings
from app.db.models import Account
from app.integrations.remnawave import (
    RemnawaveConfigurationError,
    RemnawaveRequestError,
    RemnawaveSubscriptionAccess,
    get_remnawave_gateway,
)
from app.schemas.subscription import SubscriptionStateResponse
from app.schemas.subscription_access import SubscriptionAccessResponse
from app.services.cache import get_cache
from app.services.purchases import target_remnawave_user_uuid


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_available(
    *,
    subscription_url: str | None,
    links: list[str],
    ssconf_links: dict[str, str],
) -> bool:
    return bool(subscription_url or links or ssconf_links)


def _from_remote(
    snapshot: RemnawaveSubscriptionAccess,
    *,
    source: Literal["remote", "cache"],
) -> SubscriptionAccessResponse:
    refreshed_at = _utcnow()
    return SubscriptionAccessResponse(
        available=_is_available(
            subscription_url=snapshot.subscription_url,
            links=snapshot.links,
            ssconf_links=snapshot.ssconf_links,
        ),
        source=source,
        remnawave_user_uuid=snapshot.user_uuid,
        short_uuid=snapshot.short_uuid,
        username=snapshot.username,
        status=snapshot.user_status or snapshot.status,
        expires_at=_normalize_datetime(snapshot.expires_at),
        is_active=snapshot.is_active,
        days_left=snapshot.days_left,
        subscription_url=snapshot.subscription_url,
        links=list(snapshot.links),
        ssconf_links=dict(snapshot.ssconf_links),
        traffic_used_bytes=snapshot.traffic_used_bytes,
        traffic_limit_bytes=snapshot.traffic_limit_bytes,
        lifetime_traffic_used_bytes=snapshot.lifetime_traffic_used_bytes,
        refreshed_at=refreshed_at,
    )


def _from_account(account: Account) -> SubscriptionAccessResponse:
    subscription_state = SubscriptionStateResponse.from_account(account)
    refreshed_at = _utcnow()
    subscription_url = account.subscription_url.strip() if account.subscription_url else None
    return SubscriptionAccessResponse(
        available=bool(subscription_url),
        source="local_fallback" if subscription_url else "none",
        remnawave_user_uuid=account.remnawave_user_uuid,
        status=subscription_state.status,
        expires_at=_normalize_datetime(subscription_state.expires_at),
        is_active=subscription_state.is_active,
        days_left=subscription_state.days_left,
        subscription_url=subscription_url,
        refreshed_at=refreshed_at,
    )


async def get_subscription_access(account: Account) -> SubscriptionAccessResponse:
    cache = get_cache()
    cache_key = cache.subscription_access_key(str(account.id))
    cached_payload = await cache.get_json(cache_key)
    cached_snapshot = None
    if isinstance(cached_payload, dict):
        try:
            cached_snapshot = SubscriptionAccessResponse.model_validate(cached_payload)
        except Exception:
            cached_snapshot = None

    try:
        gateway = get_remnawave_gateway()
    except RemnawaveConfigurationError:
        if cached_snapshot is not None:
            return cached_snapshot.model_copy(update={"source": "cache", "refreshed_at": _utcnow()})
        return _from_account(account)

    try:
        remote_snapshot = await gateway.get_subscription_access_by_uuid(target_remnawave_user_uuid(account))
    except RemnawaveRequestError:
        if cached_snapshot is not None:
            return cached_snapshot.model_copy(update={"source": "cache", "refreshed_at": _utcnow()})
        return _from_account(account)

    if remote_snapshot is None:
        await cache.delete(cache_key)
        return _from_account(account)

    response = _from_remote(remote_snapshot, source="remote")
    await cache.set_json(
        cache_key,
        response.model_dump(mode="json"),
        ttl_seconds=max(1, settings.subscription_access_cache_ttl_seconds),
    )
    return response
