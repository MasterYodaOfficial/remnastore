from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Awaitable, Callable
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, Notification, NotificationType
from app.integrations.remnawave.models import RemnawaveWebhookEnvelope, RemnawaveWebhookUserData
from app.services.ledger import clear_account_cache
from app.services.notifications import notify_subscription_expired, notify_subscription_expiring
from app.services.purchases import clear_remote_subscription_snapshot, normalize_datetime, utcnow


USER_EXPIRING_EVENT_DAYS = {
    "user.expires_in_72_hours": 3,
    "user.expires_in_48_hours": 2,
    "user.expires_in_24_hours": 1,
}
USER_EXPIRED_EVENT = "user.expired"
USER_DELETED_EVENT = "user.deleted"


class RemnawaveWebhookError(Exception):
    pass


class RemnawaveWebhookPayloadError(RemnawaveWebhookError):
    pass


@dataclass(slots=True)
class RemnawaveWebhookProcessResult:
    event: str
    scope: str | None
    handled: bool
    processed: bool
    account_id: UUID | None = None
    notification_types: tuple[NotificationType, ...] = ()


UserWebhookHandler = Callable[
    [AsyncSession, Account, RemnawaveWebhookUserData, RemnawaveWebhookEnvelope],
    Awaitable[list[Notification]],
]


def parse_remnawave_webhook_payload(raw_body: bytes) -> RemnawaveWebhookEnvelope:
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RemnawaveWebhookPayloadError("invalid JSON payload") from exc

    try:
        envelope = RemnawaveWebhookEnvelope.model_validate(payload)
    except ValidationError as exc:
        raise RemnawaveWebhookPayloadError("invalid Remnawave webhook payload") from exc

    if not envelope.event.strip():
        raise RemnawaveWebhookPayloadError("invalid Remnawave webhook event")
    return envelope


def parse_remnawave_webhook_user_data(envelope: RemnawaveWebhookEnvelope) -> RemnawaveWebhookUserData:
    data = envelope.data
    if isinstance(data, str):
        try:
            return RemnawaveWebhookUserData(uuid=UUID(data))
        except ValueError as exc:
            raise RemnawaveWebhookPayloadError("invalid Remnawave user uuid") from exc

    if not isinstance(data, dict):
        raise RemnawaveWebhookPayloadError("invalid Remnawave webhook payload")

    try:
        return RemnawaveWebhookUserData.model_validate(data)
    except ValidationError as exc:
        raise RemnawaveWebhookPayloadError("invalid Remnawave webhook payload") from exc


async def _load_account_by_remnawave_user_uuid(
    session: AsyncSession,
    *,
    remnawave_user_uuid: UUID,
) -> Account | None:
    result = await session.execute(
        select(Account)
        .where(
            or_(
                Account.remnawave_user_uuid == remnawave_user_uuid,
                Account.id == remnawave_user_uuid,
            )
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _apply_user_webhook_snapshot(
    account: Account,
    *,
    user: RemnawaveWebhookUserData,
) -> None:
    account.remnawave_user_uuid = user.uuid
    if user.status is not None:
        account.subscription_status = user.status
    if user.expire_at is not None:
        account.subscription_expires_at = normalize_datetime(user.expire_at)

    subscription_url = _normalize_optional_text(user.subscription_url)
    if subscription_url is not None:
        account.subscription_url = subscription_url

    if "tag" in user.model_fields_set:
        account.subscription_is_trial = user.tag == "TRIAL"
    if not account.email and user.email:
        account.email = user.email
    if account.telegram_id is None and user.telegram_id is not None:
        account.telegram_id = user.telegram_id
    account.subscription_last_synced_at = utcnow()


def _resolve_subscription_expires_at(
    account: Account,
    *,
    user: RemnawaveWebhookUserData,
) -> datetime | None:
    if user.expire_at is not None:
        return normalize_datetime(user.expire_at)
    return normalize_datetime(account.subscription_expires_at)


async def _handle_subscription_expiring_event(
    session: AsyncSession,
    account: Account,
    user: RemnawaveWebhookUserData,
    envelope: RemnawaveWebhookEnvelope,
) -> list[Notification]:
    notification = await notify_subscription_expiring(
        session,
        account=account,
        days_left=USER_EXPIRING_EVENT_DAYS[envelope.event],
        expires_at=_resolve_subscription_expires_at(account, user=user),
        remnawave_event=envelope.event,
    )
    return [notification] if notification is not None else []


async def _handle_subscription_expired_event(
    session: AsyncSession,
    account: Account,
    user: RemnawaveWebhookUserData,
    envelope: RemnawaveWebhookEnvelope,
) -> list[Notification]:
    notification = await notify_subscription_expired(
        session,
        account=account,
        expires_at=_resolve_subscription_expires_at(account, user=user),
        remnawave_event=envelope.event,
    )
    return [notification] if notification is not None else []


USER_EVENT_HANDLERS: dict[str, UserWebhookHandler] = {
    **{
        event: _handle_subscription_expiring_event
        for event in USER_EXPIRING_EVENT_DAYS
    },
    USER_EXPIRED_EVENT: _handle_subscription_expired_event,
}


async def process_remnawave_webhook(
    session: AsyncSession,
    *,
    raw_body: bytes,
) -> RemnawaveWebhookProcessResult:
    envelope = parse_remnawave_webhook_payload(raw_body)
    scope = envelope.resolved_scope
    if scope != "user":
        return RemnawaveWebhookProcessResult(
            event=envelope.event,
            scope=scope,
            handled=False,
            processed=False,
        )

    user = parse_remnawave_webhook_user_data(envelope)
    account = await _load_account_by_remnawave_user_uuid(
        session,
        remnawave_user_uuid=user.uuid,
    )
    if account is None:
        return RemnawaveWebhookProcessResult(
            event=envelope.event,
            scope=scope,
            handled=True,
            processed=False,
        )

    notifications: list[Notification] = []
    if envelope.event == USER_DELETED_EVENT:
        clear_remote_subscription_snapshot(account)
    else:
        _apply_user_webhook_snapshot(account, user=user)
        handler = USER_EVENT_HANDLERS.get(envelope.event)
        if handler is not None:
            notifications = await handler(session, account, user, envelope)

    await session.commit()
    await session.refresh(account)
    await clear_account_cache(account.id)
    return RemnawaveWebhookProcessResult(
        event=envelope.event,
        scope=scope,
        handled=True,
        processed=True,
        account_id=account.id,
        notification_types=tuple(notification.type for notification in notifications),
    )
