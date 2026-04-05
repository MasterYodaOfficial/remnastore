"""Service for managing account linking tokens and operations."""

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Account,
    AccountStatus,
    AdminActionLog,
    AuthAccount,
    AuthLinkToken,
    AuthProvider,
    BroadcastDelivery,
    BroadcastDeliveryStatus,
    LoginSource,
    LinkType,
    Notification,
    Payment,
    PaymentEvent,
    ReferralAttribution,
    ReferralReward,
    SubscriptionGrant,
    TelegramReferralIntent,
    Withdrawal,
)
from app.integrations.remnawave import (
    RemnawaveConfigurationError,
    RemnawaveRequestError,
    RemnawaveUser,
    get_remnawave_gateway,
)
from app.services.account_events import append_account_event
from app.services.cache import get_cache
from app.services.i18n import translate
from app.services.ledger import transfer_balance_for_merge


class LinkTokenExpiredError(Exception):
    """Raised when link token has expired."""

    code = "token_expired"


class LinkTokenAlreadyConsumedError(Exception):
    """Raised when link token was already consumed."""

    code = "token_already_used"


class LinkTokenNotFoundError(Exception):
    """Raised when link token doesn't exist."""

    code = "token_not_found"


class LinkTokenTypeMismatchError(Exception):
    """Raised when link token type doesn't match the requested flow."""

    code = "token_type_invalid"


class AccountMergeConflictError(Exception):
    """Raised when accounts cannot be merged safely."""

    code = "merge_conflict"


def _linking_error(key: str) -> str:
    return translate(f"api.linking.errors.{key}")


def _utcnow() -> datetime:
    """Return an aware UTC datetime for DB timestamps and comparisons."""
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class SubscriptionSnapshotCandidate:
    remnawave_user_uuid: uuid.UUID | None
    subscription_url: str | None
    subscription_status: str | None
    subscription_expires_at: datetime | None
    subscription_last_synced_at: datetime | None
    subscription_is_trial: bool
    sort_bias: int = 0


@dataclass(slots=True)
class RemnawaveUserSelectionResult:
    keep_user: RemnawaveUser
    ranked_users: list[RemnawaveUser]
    reason: str


@dataclass(slots=True)
class RemnawaveReconcileResult:
    merged_user: RemnawaveUser
    audit_payload: dict[str, Any]


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _later_datetime(*values: datetime | None) -> datetime | None:
    normalized_values = [
        _normalize_datetime(value) for value in values if value is not None
    ]
    if not normalized_values:
        return None
    return max(normalized_values)


def _earlier_datetime(*values: datetime | None) -> datetime | None:
    normalized_values = [
        _normalize_datetime(value) for value in values if value is not None
    ]
    if not normalized_values:
        return None
    return min(normalized_values)


def _datetime_sort_value(value: datetime | None) -> float:
    normalized_value = _normalize_datetime(value)
    if normalized_value is None:
        return float("-inf")
    return normalized_value.timestamp()


def _account_has_remnawave_state(account: Account) -> bool:
    return any(
        (
            account.remnawave_user_uuid is not None,
            _normalize_optional_text(account.subscription_url) is not None,
            _normalize_optional_text(account.subscription_status) is not None,
            account.subscription_expires_at is not None,
            account.subscription_last_synced_at is not None,
            account.subscription_is_trial,
        )
    )


def _subscription_status_rank(
    status: str | None, *, expires_at: datetime | None
) -> int:
    normalized_status = _normalize_optional_text(status)
    if normalized_status is not None:
        normalized_status = normalized_status.upper()
    status_ranks = {
        "ACTIVE": 4,
        "LIMITED": 3,
        "DISABLED": 2,
        "EXPIRED": 1,
    }
    if normalized_status in status_ranks:
        return status_ranks[normalized_status]

    normalized_expires_at = _normalize_datetime(expires_at)
    now = _normalize_datetime(_utcnow()) or datetime.now(timezone.utc)
    if normalized_expires_at is not None and normalized_expires_at <= now:
        return status_ranks["EXPIRED"]
    return status_ranks["ACTIVE"]


def _subscription_candidate_sort_key(
    candidate: SubscriptionSnapshotCandidate,
) -> tuple[tuple[int, float, int], int, float, int]:
    normalized_expires_at = _normalize_datetime(candidate.subscription_expires_at)
    normalized_url = _normalize_optional_text(candidate.subscription_url)
    normalized_synced_at = _normalize_datetime(candidate.subscription_last_synced_at)
    return (
        _subscription_strength_sort_key(
            is_trial=candidate.subscription_is_trial,
            expires_at=normalized_expires_at,
            status=candidate.subscription_status,
        ),
        1 if normalized_url is not None else 0,
        _datetime_sort_value(normalized_synced_at),
        int(candidate.sort_bias),
    )


def _subscription_strength_sort_key(
    *,
    is_trial: bool,
    expires_at: datetime | None,
    status: str | None,
) -> tuple[int, float, int]:
    normalized_expires_at = _normalize_datetime(expires_at)
    return (
        0 if is_trial else 1,
        _datetime_sort_value(normalized_expires_at),
        _subscription_status_rank(status, expires_at=normalized_expires_at),
    )


def _remnawave_traffic_sort_key(user: RemnawaveUser) -> tuple[int, int, int, int]:
    used_traffic_bytes = int(user.used_traffic_bytes or 0)
    lifetime_used_traffic_bytes = int(user.lifetime_used_traffic_bytes or 0)
    max_traffic_bytes = max(used_traffic_bytes, lifetime_used_traffic_bytes)
    return (
        1 if max_traffic_bytes > 0 else 0,
        max_traffic_bytes,
        lifetime_used_traffic_bytes,
        used_traffic_bytes,
    )


def _remnawave_user_sort_key(
    user: RemnawaveUser,
) -> tuple[int, float, int, float, int, int, int, int, float, int, str]:
    return (
        1 if _normalize_datetime(user.online_at) is not None else 0,
        _datetime_sort_value(user.online_at),
        1 if _normalize_datetime(user.first_connected_at) is not None else 0,
        _datetime_sort_value(user.first_connected_at),
        *_remnawave_traffic_sort_key(user),
        *_subscription_strength_sort_key(
            is_trial=user.tag == "TRIAL",
            expires_at=user.expire_at,
            status=user.status,
        ),
        user.uuid.hex,
    )


def _select_remnawave_user_reason(
    *,
    winner: RemnawaveUser,
    runner_up: RemnawaveUser | None,
) -> str:
    if runner_up is None:
        return "single_remote_user"

    if _normalize_datetime(winner.online_at) != _normalize_datetime(
        runner_up.online_at
    ):
        return "latest_online_at"
    if _normalize_datetime(winner.first_connected_at) != _normalize_datetime(
        runner_up.first_connected_at
    ):
        return "latest_first_connected_at"
    if _remnawave_traffic_sort_key(winner) != _remnawave_traffic_sort_key(runner_up):
        return "higher_traffic_usage"

    winner_subscription_key = _subscription_strength_sort_key(
        is_trial=winner.tag == "TRIAL",
        expires_at=winner.expire_at,
        status=winner.status,
    )
    runner_subscription_key = _subscription_strength_sort_key(
        is_trial=runner_up.tag == "TRIAL",
        expires_at=runner_up.expire_at,
        status=runner_up.status,
    )
    if winner_subscription_key[0] != runner_subscription_key[0]:
        return "paid_over_trial"
    if winner_subscription_key[1] != runner_subscription_key[1]:
        return "latest_expires_at"
    if winner_subscription_key[2] != runner_subscription_key[2]:
        return "stronger_status"
    return "deterministic_uuid_tie_breaker"


def _serialize_remnawave_user_snapshot(user: RemnawaveUser) -> dict[str, Any]:
    return {
        "uuid": user.uuid,
        "status": user.status,
        "expire_at": _normalize_datetime(user.expire_at),
        "subscription_url": _normalize_optional_text(user.subscription_url),
        "telegram_id": user.telegram_id,
        "email": _normalize_optional_text(user.email),
        "tag": _normalize_optional_text(user.tag),
        "used_traffic_bytes": int(user.used_traffic_bytes or 0),
        "lifetime_used_traffic_bytes": int(user.lifetime_used_traffic_bytes or 0),
        "online_at": _normalize_datetime(user.online_at),
        "first_connected_at": _normalize_datetime(user.first_connected_at),
    }


def _account_snapshot_candidate(
    account: Account, *, sort_bias: int
) -> SubscriptionSnapshotCandidate | None:
    if not _account_has_remnawave_state(account):
        return None
    return SubscriptionSnapshotCandidate(
        remnawave_user_uuid=account.remnawave_user_uuid,
        subscription_url=_normalize_optional_text(account.subscription_url),
        subscription_status=_normalize_optional_text(account.subscription_status),
        subscription_expires_at=_normalize_datetime(account.subscription_expires_at),
        subscription_last_synced_at=_normalize_datetime(
            account.subscription_last_synced_at
        ),
        subscription_is_trial=bool(account.subscription_is_trial),
        sort_bias=sort_bias,
    )


def _remote_snapshot_candidate(
    remote_user: RemnawaveUser,
    *,
    sort_bias: int,
) -> SubscriptionSnapshotCandidate:
    return SubscriptionSnapshotCandidate(
        remnawave_user_uuid=remote_user.uuid,
        subscription_url=_normalize_optional_text(remote_user.subscription_url),
        subscription_status=_normalize_optional_text(remote_user.status),
        subscription_expires_at=_normalize_datetime(remote_user.expire_at),
        subscription_last_synced_at=None,
        subscription_is_trial=remote_user.tag == "TRIAL",
        sort_bias=sort_bias,
    )


def _select_preferred_subscription_candidate(
    *,
    target_account: Account,
    source_account: Account,
    remote_users: list[RemnawaveUser],
) -> SubscriptionSnapshotCandidate | None:
    candidates = [
        _account_snapshot_candidate(target_account, sort_bias=20),
        _account_snapshot_candidate(source_account, sort_bias=10),
    ]
    candidates.extend(
        _remote_snapshot_candidate(user, sort_bias=0) for user in remote_users
    )
    resolved_candidates = [
        candidate for candidate in candidates if candidate is not None
    ]
    if not resolved_candidates:
        return None
    return max(resolved_candidates, key=_subscription_candidate_sort_key)


def _apply_subscription_candidate(
    target_account: Account,
    *,
    candidate: SubscriptionSnapshotCandidate | None,
    remnawave_user_uuid: uuid.UUID | None,
) -> None:
    merged_last_synced_at = _later_datetime(
        target_account.subscription_last_synced_at,
        None if candidate is None else candidate.subscription_last_synced_at,
    )
    target_account.remnawave_user_uuid = (
        remnawave_user_uuid
        or (None if candidate is None else candidate.remnawave_user_uuid)
        or target_account.remnawave_user_uuid
    )
    target_account.subscription_url = (
        None if candidate is None else candidate.subscription_url
    )
    target_account.subscription_status = (
        None if candidate is None else candidate.subscription_status
    )
    target_account.subscription_expires_at = (
        None if candidate is None else candidate.subscription_expires_at
    )
    target_account.subscription_last_synced_at = merged_last_synced_at
    target_account.subscription_is_trial = (
        False if candidate is None else candidate.subscription_is_trial
    )


def _merge_trial_metadata(target_account: Account, source_account: Account) -> None:
    target_account.trial_used_at = _earlier_datetime(
        target_account.trial_used_at,
        source_account.trial_used_at,
    )
    target_account.trial_ends_at = _later_datetime(
        target_account.trial_ends_at,
        source_account.trial_ends_at,
    )


async def create_telegram_link_token(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    ttl_seconds: int = 3600,
) -> tuple[str, str]:
    """
    Create a link token for Telegram account linking from browser.

    Returns:
        (link_token, telegram_link_url)
        Example URL: https://t.me/bot_username?start=link_ABC123
    """
    link_token = f"link_{secrets.token_urlsafe(16)}"
    expires_at = _utcnow() + timedelta(seconds=ttl_seconds)

    token = AuthLinkToken(
        account_id=account_id,
        link_token=link_token,
        provider=AuthProvider.SUPABASE,  # Marker for browser OAuth linking
        provider_uid="telegram_link",  # Marker value
        link_type=LinkType.TELEGRAM_FROM_BROWSER,
        expires_at=expires_at,
    )

    session.add(token)
    await session.flush()
    await append_account_event(
        session,
        account_id=account_id,
        actor_account_id=account_id,
        event_type="account.link.telegram_token.created",
        source="api",
        payload={
            "token_id": token.id,
            "link_type": token.link_type.value if token.link_type is not None else None,
            "expires_at": token.expires_at.isoformat(),
        },
    )

    # Return token and URL template (bot username will be set in config)
    return link_token, f"https://t.me/{{bot_username}}?start={link_token}"


async def create_browser_link_token(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    webapp_url: str,
    ttl_seconds: int = 3600,
) -> tuple[str, str]:
    """
    Create a link token for browser OAuth linking from Telegram.

    Returns:
        (link_token, browser_link_url)
        Example: https://app.example.com/?link_token=link_XYZ789_BROWSER&link_flow=browser
    """
    link_token = f"link_{secrets.token_urlsafe(16)}_BROWSER"
    expires_at = _utcnow() + timedelta(seconds=ttl_seconds)

    token = AuthLinkToken(
        account_id=account_id,
        link_token=link_token,
        provider=AuthProvider.SUPABASE,
        provider_uid="browser_link",
        link_type=LinkType.BROWSER_FROM_TELEGRAM,
        expires_at=expires_at,
    )

    session.add(token)
    await session.flush()
    await append_account_event(
        session,
        account_id=account_id,
        actor_account_id=account_id,
        event_type="account.link.browser_token.created",
        source="api",
        payload={
            "token_id": token.id,
            "link_type": token.link_type.value if token.link_type is not None else None,
            "expires_at": token.expires_at.isoformat(),
        },
    )

    webapp_base_url = webapp_url.rstrip("/")
    return (
        link_token,
        f"{webapp_base_url}/?link_token={link_token}&link_flow=browser",
    )


async def get_link_token(
    session: AsyncSession,
    *,
    link_token: str,
    expected_link_type: Optional[LinkType] = None,
) -> AuthLinkToken:
    """
    Lock and validate a link token.

    Args:
        link_token: The token to consume
        expected_link_type: Optional flow guard

    Raises:
        LinkTokenNotFoundError: Token doesn't exist
        LinkTokenExpiredError: Token has expired
        LinkTokenAlreadyConsumedError: Token was already consumed
        LinkTokenTypeMismatchError: Token belongs to a different linking flow
    """
    result = await session.execute(
        select(AuthLinkToken)
        .where(AuthLinkToken.link_token == link_token)
        .with_for_update()
    )
    token = result.scalar_one_or_none()

    if token is None:
        raise LinkTokenNotFoundError(_linking_error("token_not_found"))

    if token.consumed_at is not None:
        raise LinkTokenAlreadyConsumedError(_linking_error("token_already_used"))

    if _utcnow() >= token.expires_at:
        raise LinkTokenExpiredError(_linking_error("token_expired"))

    if expected_link_type is not None and token.link_type != expected_link_type:
        raise LinkTokenTypeMismatchError(_linking_error("token_type_invalid"))

    return token


def mark_link_token_consumed(token: AuthLinkToken) -> None:
    """Mark a link token as consumed after a successful linking operation."""
    token.consumed_at = _utcnow()


async def _load_account_for_update(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
) -> Account:
    result = await session.execute(
        select(Account).where(Account.id == account_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise ValueError(_linking_error("account_not_found"))
    return account


def _ensure_no_scalar_conflicts(target: Account, source: Account) -> None:
    conflict_fields = (
        ("telegram_id", target.telegram_id, source.telegram_id),
        ("email", target.email, source.email),
        (
            "referred_by_account_id",
            target.referred_by_account_id,
            source.referred_by_account_id,
        ),
    )
    for field_name, target_value, source_value in conflict_fields:
        if source_value is None or target_value is None:
            continue
        if target_value != source_value:
            raise AccountMergeConflictError(_linking_error("merge_conflict"))


async def _move_auth_accounts(
    session: AsyncSession,
    *,
    source_account_id: uuid.UUID,
    target_account_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(AuthAccount).where(AuthAccount.account_id == source_account_id)
    )
    source_auth_accounts = result.scalars().all()

    result = await session.execute(
        select(AuthAccount).where(AuthAccount.account_id == target_account_id)
    )
    target_auth_accounts = {
        (auth.provider, auth.provider_uid): auth for auth in result.scalars().all()
    }

    for auth_account in source_auth_accounts:
        key = (auth_account.provider, auth_account.provider_uid)
        existing = target_auth_accounts.get(key)
        if existing is None:
            auth_account.account_id = target_account_id
            target_auth_accounts[key] = auth_account
            continue

        existing.email = existing.email or auth_account.email
        existing.display_name = existing.display_name or auth_account.display_name
        await session.delete(auth_account)


async def _clear_account_cache(*account_ids: uuid.UUID) -> None:
    cache = get_cache()
    cache_keys = [
        cache.account_response_key(str(account_id)) for account_id in account_ids
    ]
    await cache.delete(*cache_keys)


async def _merge_referral_records(
    session: AsyncSession,
    *,
    source_account: Account,
    target_account: Account,
) -> None:
    source_attribution = await session.scalar(
        select(ReferralAttribution)
        .where(ReferralAttribution.referred_account_id == source_account.id)
        .with_for_update()
    )
    target_attribution = await session.scalar(
        select(ReferralAttribution)
        .where(ReferralAttribution.referred_account_id == target_account.id)
        .with_for_update()
    )
    if source_attribution is not None:
        if target_attribution is None:
            source_attribution.referred_account_id = target_account.id
        else:
            await session.delete(source_attribution)

    result = await session.execute(
        select(ReferralAttribution)
        .where(ReferralAttribution.referrer_account_id == source_account.id)
        .with_for_update()
    )
    for attribution in result.scalars().all():
        attribution.referrer_account_id = target_account.id

    source_reward = await session.scalar(
        select(ReferralReward)
        .where(ReferralReward.referred_account_id == source_account.id)
        .with_for_update()
    )
    target_reward = await session.scalar(
        select(ReferralReward)
        .where(ReferralReward.referred_account_id == target_account.id)
        .with_for_update()
    )
    if source_reward is not None:
        if target_reward is None:
            source_reward.referred_account_id = target_account.id
        else:
            await session.delete(source_reward)

    result = await session.execute(
        select(ReferralReward)
        .where(ReferralReward.referrer_account_id == source_account.id)
        .with_for_update()
    )
    for reward in result.scalars().all():
        reward.referrer_account_id = target_account.id


async def _move_withdrawals(
    session: AsyncSession,
    *,
    source_account_id: uuid.UUID,
    target_account_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(Withdrawal)
        .where(Withdrawal.account_id == source_account_id)
        .with_for_update()
    )
    for withdrawal in result.scalars().all():
        withdrawal.account_id = target_account_id


async def _move_payments(
    session: AsyncSession,
    *,
    source_account_id: uuid.UUID,
    target_account_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(Payment).where(Payment.account_id == source_account_id).with_for_update()
    )
    for payment in result.scalars().all():
        payment.account_id = target_account_id


async def _move_payment_events(
    session: AsyncSession,
    *,
    source_account_id: uuid.UUID,
    target_account_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(PaymentEvent)
        .where(PaymentEvent.account_id == source_account_id)
        .with_for_update()
    )
    for event in result.scalars().all():
        event.account_id = target_account_id


async def _move_subscription_grants(
    session: AsyncSession,
    *,
    source_account_id: uuid.UUID,
    target_account_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(SubscriptionGrant)
        .where(SubscriptionGrant.account_id == source_account_id)
        .with_for_update()
    )
    for grant in result.scalars().all():
        grant.account_id = target_account_id


async def _move_notifications(
    session: AsyncSession,
    *,
    source_account_id: uuid.UUID,
    target_account_id: uuid.UUID,
) -> None:
    target_notifications_result = await session.execute(
        select(Notification)
        .where(Notification.account_id == target_account_id)
        .with_for_update()
    )
    target_dedupe_keys = {
        notification.dedupe_key
        for notification in target_notifications_result.scalars().all()
        if _normalize_optional_text(notification.dedupe_key) is not None
    }

    source_notifications_result = await session.execute(
        select(Notification)
        .where(Notification.account_id == source_account_id)
        .with_for_update()
    )
    for notification in source_notifications_result.scalars().all():
        normalized_dedupe_key = _normalize_optional_text(notification.dedupe_key)
        if (
            normalized_dedupe_key is not None
            and normalized_dedupe_key in target_dedupe_keys
        ):
            notification.dedupe_key = None
        notification.account_id = target_account_id


_BROADCAST_DELIVERY_STATUS_PRIORITY = {
    BroadcastDeliveryStatus.DELIVERED: 4,
    BroadcastDeliveryStatus.PENDING: 3,
    BroadcastDeliveryStatus.FAILED: 2,
    BroadcastDeliveryStatus.SKIPPED: 1,
}


def _merge_broadcast_delivery_rows(
    *,
    target_delivery: BroadcastDelivery,
    source_delivery: BroadcastDelivery,
) -> None:
    target_priority = _BROADCAST_DELIVERY_STATUS_PRIORITY[target_delivery.status]
    source_priority = _BROADCAST_DELIVERY_STATUS_PRIORITY[source_delivery.status]

    if source_priority > target_priority:
        target_delivery.status = source_delivery.status
        target_delivery.provider_message_id = (
            source_delivery.provider_message_id or target_delivery.provider_message_id
        )
        target_delivery.notification_id = (
            source_delivery.notification_id or target_delivery.notification_id
        )
        target_delivery.delivered_at = _later_datetime(
            source_delivery.delivered_at,
            target_delivery.delivered_at,
        )
        target_delivery.error_code = source_delivery.error_code
        target_delivery.error_message = source_delivery.error_message
    else:
        target_delivery.provider_message_id = (
            target_delivery.provider_message_id or source_delivery.provider_message_id
        )
        target_delivery.notification_id = (
            target_delivery.notification_id or source_delivery.notification_id
        )
        target_delivery.delivered_at = _later_datetime(
            target_delivery.delivered_at,
            source_delivery.delivered_at,
        )
        target_delivery.error_code = (
            target_delivery.error_code or source_delivery.error_code
        )
        target_delivery.error_message = (
            target_delivery.error_message or source_delivery.error_message
        )

    target_delivery.attempts_count = max(
        int(target_delivery.attempts_count or 0),
        int(source_delivery.attempts_count or 0),
    )
    target_delivery.last_attempt_at = _later_datetime(
        target_delivery.last_attempt_at,
        source_delivery.last_attempt_at,
    )

    if target_delivery.status == BroadcastDeliveryStatus.PENDING:
        target_delivery.next_retry_at = _earlier_datetime(
            target_delivery.next_retry_at,
            source_delivery.next_retry_at,
        )
        target_delivery.error_code = (
            target_delivery.error_code or source_delivery.error_code
        )
        target_delivery.error_message = (
            target_delivery.error_message or source_delivery.error_message
        )
    elif target_delivery.status == BroadcastDeliveryStatus.DELIVERED:
        target_delivery.next_retry_at = None
        target_delivery.error_code = None
        target_delivery.error_message = None
    else:
        target_delivery.next_retry_at = None


async def _move_broadcast_deliveries(
    session: AsyncSession,
    *,
    source_account_id: uuid.UUID,
    target_account_id: uuid.UUID,
) -> None:
    target_result = await session.execute(
        select(BroadcastDelivery)
        .where(BroadcastDelivery.account_id == target_account_id)
        .with_for_update()
    )
    target_deliveries = {
        (delivery.run_id, delivery.channel): delivery
        for delivery in target_result.scalars().all()
    }

    source_result = await session.execute(
        select(BroadcastDelivery)
        .where(BroadcastDelivery.account_id == source_account_id)
        .with_for_update()
    )
    for delivery in source_result.scalars().all():
        key = (delivery.run_id, delivery.channel)
        existing_delivery = target_deliveries.get(key)
        if existing_delivery is None:
            delivery.account_id = target_account_id
            target_deliveries[key] = delivery
            continue

        _merge_broadcast_delivery_rows(
            target_delivery=existing_delivery,
            source_delivery=delivery,
        )
        await session.delete(delivery)


async def _move_telegram_referral_intents(
    session: AsyncSession,
    *,
    source_account_id: uuid.UUID,
    target_account_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(TelegramReferralIntent)
        .where(TelegramReferralIntent.account_id == source_account_id)
        .with_for_update()
    )
    for intent in result.scalars().all():
        intent.account_id = target_account_id


async def _move_admin_action_logs(
    session: AsyncSession,
    *,
    source_account_id: uuid.UUID,
    target_account_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(AdminActionLog)
        .where(AdminActionLog.target_account_id == source_account_id)
        .with_for_update()
    )
    for action_log in result.scalars().all():
        action_log.target_account_id = target_account_id


async def _collect_remnawave_users_for_merge(
    *,
    target_account: Account,
    source_account: Account,
):
    should_reconcile_remnawave = _account_has_remnawave_state(
        target_account
    ) or _account_has_remnawave_state(source_account)
    if not should_reconcile_remnawave:
        return None, []

    try:
        gateway = get_remnawave_gateway()
    except RemnawaveConfigurationError as exc:
        raise AccountMergeConflictError(
            _linking_error("remnawave_merge_failed")
        ) from exc

    candidates: dict[uuid.UUID, RemnawaveUser] = {}
    uuids_to_probe: set[uuid.UUID] = set()
    for account in (target_account, source_account):
        if account.remnawave_user_uuid is not None:
            uuids_to_probe.add(account.remnawave_user_uuid)
        elif _account_has_remnawave_state(account):
            uuids_to_probe.add(account.id)

    try:
        for user_uuid in uuids_to_probe:
            remote_user = await gateway.get_user_by_uuid(user_uuid)
            if remote_user is not None:
                candidates[remote_user.uuid] = remote_user

        for email in {
            account.email
            for account in (target_account, source_account)
            if _normalize_optional_text(account.email) is not None
        }:
            assert email is not None
            for remote_user in await gateway.get_users_by_email(email):
                candidates[remote_user.uuid] = remote_user

        for telegram_id in {
            account.telegram_id
            for account in (target_account, source_account)
            if account.telegram_id is not None
        }:
            assert telegram_id is not None
            for remote_user in await gateway.get_users_by_telegram_id(telegram_id):
                candidates[remote_user.uuid] = remote_user
    except RemnawaveRequestError as exc:
        raise AccountMergeConflictError(
            _linking_error("remnawave_merge_failed")
        ) from exc

    return gateway, list(candidates.values())


def _select_remnawave_user_to_keep(
    *,
    remote_users: list[RemnawaveUser],
) -> RemnawaveUserSelectionResult:
    ranked_users = sorted(remote_users, key=_remnawave_user_sort_key, reverse=True)
    keep_user = ranked_users[0]
    runner_up = ranked_users[1] if len(ranked_users) > 1 else None
    return RemnawaveUserSelectionResult(
        keep_user=keep_user,
        ranked_users=ranked_users,
        reason=_select_remnawave_user_reason(
            winner=keep_user,
            runner_up=runner_up,
        ),
    )


async def _reconcile_remnawave_users(
    *,
    gateway,
    target_account: Account,
    source_account: Account,
    remote_users: list[RemnawaveUser],
) -> RemnawaveReconcileResult:
    selection = _select_remnawave_user_to_keep(
        remote_users=remote_users,
    )
    keep_user = selection.keep_user
    preferred_candidate = _select_preferred_subscription_candidate(
        target_account=target_account,
        source_account=source_account,
        remote_users=remote_users,
    )
    resolved_expires_at = (
        keep_user.expire_at
        if preferred_candidate is None
        or preferred_candidate.subscription_expires_at is None
        else preferred_candidate.subscription_expires_at
    )
    resolved_status = (
        keep_user.status
        if preferred_candidate is None
        else preferred_candidate.subscription_status or keep_user.status
    )
    resolved_is_trial = (
        keep_user.tag == "TRIAL"
        if preferred_candidate is None
        else preferred_candidate.subscription_is_trial
    )

    try:
        merged_user = await gateway.upsert_user(
            user_uuid=keep_user.uuid,
            expire_at=resolved_expires_at,
            email=target_account.email,
            telegram_id=target_account.telegram_id,
            status=resolved_status,
            is_trial=resolved_is_trial,
        )
        deleted_user_uuids: list[uuid.UUID] = []
        for remote_user in selection.ranked_users:
            if remote_user.uuid == keep_user.uuid:
                continue
            await gateway.delete_user(remote_user.uuid)
            deleted_user_uuids.append(remote_user.uuid)
    except RemnawaveRequestError as exc:
        raise AccountMergeConflictError(
            _linking_error("remnawave_merge_failed")
        ) from exc

    return RemnawaveReconcileResult(
        merged_user=merged_user,
        audit_payload={
            "kept_user_uuid": keep_user.uuid,
            "deleted_user_uuids": deleted_user_uuids,
            "selection_reason": selection.reason,
            "subscription_candidate_user_uuid": None
            if preferred_candidate is None
            else preferred_candidate.remnawave_user_uuid,
            "ranked_remote_users": [
                _serialize_remnawave_user_snapshot(user)
                for user in selection.ranked_users
            ],
            "merged_user": _serialize_remnawave_user_snapshot(merged_user),
        },
    )


async def merge_accounts(
    session: AsyncSession,
    *,
    source_account_id: uuid.UUID,
    target_account_id: uuid.UUID,
    last_login_source: LoginSource,
) -> Account:
    """Merge source account into target account and return target."""
    target_account = await _load_account_for_update(
        session, account_id=target_account_id
    )

    if source_account_id == target_account_id:
        target_account.last_login_source = last_login_source
        target_account.last_seen_at = _utcnow()
        await session.flush()
        await _clear_account_cache(target_account.id)
        return target_account

    source_account = await _load_account_for_update(
        session, account_id=source_account_id
    )
    _ensure_no_scalar_conflicts(target_account, source_account)
    remnawave_gateway, remote_users = await _collect_remnawave_users_for_merge(
        target_account=target_account,
        source_account=source_account,
    )

    moved_telegram_id = (
        source_account.telegram_id if target_account.telegram_id is None else None
    )

    # Flush source unique values away before target takes them to avoid transient unique violations.
    if moved_telegram_id is not None:
        source_account.telegram_id = None
        await session.flush()

    target_account.email = target_account.email or source_account.email
    target_account.display_name = (
        target_account.display_name or source_account.display_name
    )
    target_account.telegram_id = target_account.telegram_id or moved_telegram_id
    target_account.username = target_account.username or source_account.username
    target_account.first_name = target_account.first_name or source_account.first_name
    target_account.last_name = target_account.last_name or source_account.last_name
    target_account.is_premium = target_account.is_premium or source_account.is_premium
    target_account.locale = target_account.locale or source_account.locale
    target_account.referred_by_account_id = (
        target_account.referred_by_account_id or source_account.referred_by_account_id
    )
    if (
        target_account.status == AccountStatus.BLOCKED
        or source_account.status == AccountStatus.BLOCKED
    ):
        target_account.status = AccountStatus.BLOCKED
    _merge_trial_metadata(target_account, source_account)

    if remnawave_gateway is not None and remote_users:
        remnawave_reconcile_result = await _reconcile_remnawave_users(
            gateway=remnawave_gateway,
            target_account=target_account,
            source_account=source_account,
            remote_users=remote_users,
        )
        merged_remote_user = remnawave_reconcile_result.merged_user
        _apply_subscription_candidate(
            target_account,
            candidate=_remote_snapshot_candidate(merged_remote_user, sort_bias=100),
            remnawave_user_uuid=merged_remote_user.uuid,
        )
        target_account.subscription_last_synced_at = _utcnow()
    else:
        preferred_subscription_candidate = _select_preferred_subscription_candidate(
            target_account=target_account,
            source_account=source_account,
            remote_users=[],
        )
        _apply_subscription_candidate(
            target_account,
            candidate=preferred_subscription_candidate,
            remnawave_user_uuid=(
                None
                if preferred_subscription_candidate is None
                else preferred_subscription_candidate.remnawave_user_uuid
            ),
        )

    if source_account.balance > 0:
        await transfer_balance_for_merge(
            session,
            source_account=source_account,
            target_account=target_account,
            amount=source_account.balance,
            reference_id=uuid.uuid4().hex,
        )
    target_account.referral_earnings += source_account.referral_earnings
    target_account.referrals_count += source_account.referrals_count
    target_account.referral_reward_rate = max(
        float(target_account.referral_reward_rate or 0),
        float(source_account.referral_reward_rate or 0),
    )
    target_account.last_login_source = last_login_source
    target_account.last_seen_at = _utcnow()

    merge_audit_payload: dict[str, Any] = {
        "source_account_id": source_account.id,
        "target_account_id": target_account.id,
    }
    if remnawave_gateway is not None and remote_users:
        merge_audit_payload["remnawave_reconcile"] = (
            remnawave_reconcile_result.audit_payload
        )

    await _move_auth_accounts(
        session,
        source_account_id=source_account.id,
        target_account_id=target_account.id,
    )
    await _merge_referral_records(
        session,
        source_account=source_account,
        target_account=target_account,
    )
    await _move_withdrawals(
        session,
        source_account_id=source_account.id,
        target_account_id=target_account.id,
    )
    await _move_payments(
        session,
        source_account_id=source_account.id,
        target_account_id=target_account.id,
    )
    await _move_payment_events(
        session,
        source_account_id=source_account.id,
        target_account_id=target_account.id,
    )
    await _move_subscription_grants(
        session,
        source_account_id=source_account.id,
        target_account_id=target_account.id,
    )
    await _move_notifications(
        session,
        source_account_id=source_account.id,
        target_account_id=target_account.id,
    )
    await _move_broadcast_deliveries(
        session,
        source_account_id=source_account.id,
        target_account_id=target_account.id,
    )
    await _move_telegram_referral_intents(
        session,
        source_account_id=source_account.id,
        target_account_id=target_account.id,
    )
    await _move_admin_action_logs(
        session,
        source_account_id=source_account.id,
        target_account_id=target_account.id,
    )
    await append_account_event(
        session,
        account_id=target_account.id,
        event_type="account.merge.completed",
        source="api",
        payload=merge_audit_payload,
    )
    await session.flush()
    await session.delete(source_account)
    await session.flush()
    await _clear_account_cache(source_account.id, target_account.id)
    return target_account


async def link_telegram_to_account(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    is_premium: bool = False,
) -> Account:
    """
    Link a Telegram account to an existing browser OAuth account.
    """
    account = await _load_account_for_update(session, account_id=account_id)

    result = await session.execute(
        select(Account).where(Account.telegram_id == telegram_id).with_for_update()
    )
    telegram_account = result.scalar_one_or_none()
    merged_account_id: uuid.UUID | None = None

    if telegram_account is not None and telegram_account.id != account.id:
        merged_account_id = telegram_account.id
        account = await merge_accounts(
            session,
            source_account_id=telegram_account.id,
            target_account_id=account.id,
            last_login_source=LoginSource.BROWSER_OAUTH,
        )

    account.telegram_id = telegram_id
    account.username = username or account.username
    account.first_name = first_name or account.first_name
    account.last_name = last_name or account.last_name
    account.is_premium = account.is_premium or is_premium
    account.last_login_source = LoginSource.BROWSER_OAUTH
    account.last_seen_at = _utcnow()

    await session.flush()
    await append_account_event(
        session,
        account_id=account.id,
        actor_account_id=account.id,
        event_type="account.link.telegram_confirmed",
        source="api",
        payload={
            "telegram_id": telegram_id,
            "merged_account_id": merged_account_id,
        },
    )
    await _clear_account_cache(account.id)
    return account


async def link_browser_oauth_to_telegram_account(
    session: AsyncSession,
    *,
    telegram_account_id: uuid.UUID,
    browser_account_id: uuid.UUID,
) -> Account:
    """
    Merge a browser OAuth account into an existing Telegram account.
    """
    account = await merge_accounts(
        session,
        source_account_id=browser_account_id,
        target_account_id=telegram_account_id,
        last_login_source=LoginSource.BROWSER_OAUTH,
    )
    await session.flush()
    await append_account_event(
        session,
        account_id=account.id,
        actor_account_id=browser_account_id,
        event_type="account.link.browser_completed",
        source="api",
        payload={
            "merged_account_id": browser_account_id,
        },
    )
    return account


async def get_valid_link_token(
    session: AsyncSession,
    link_token: str,
) -> Optional[AuthLinkToken]:
    """Get a non-expired, non-consumed link token."""
    result = await session.execute(
        select(AuthLinkToken).where(
            and_(
                AuthLinkToken.link_token == link_token,
                AuthLinkToken.consumed_at.is_(None),
                AuthLinkToken.expires_at > _utcnow(),
            )
        )
    )
    return result.scalar_one_or_none()
