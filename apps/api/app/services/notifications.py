from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
import uuid

import httpx
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Account,
    Notification,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationPriority,
    NotificationType,
    Payment,
    ReferralReward,
    Withdrawal,
)
from app.domain.payments import PaymentFlowType, PaymentProvider, PaymentStatus
from app.core.config import settings
from app.services.accounts import mark_telegram_bot_blocked
from app.services.i18n import translate
from app.services.plans import SubscriptionPlanError, get_subscription_plan

logger = logging.getLogger(__name__)


class NotificationServiceError(Exception):
    pass


class NotificationNotFoundError(NotificationServiceError):
    code = "notification_not_found"


class TelegramNotificationConfigurationError(NotificationServiceError):
    pass


class TelegramNotificationDeliveryError(NotificationServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        retryable: bool,
        retry_after_seconds: int | None = None,
        mark_telegram_bot_blocked: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.mark_telegram_bot_blocked = mark_telegram_bot_blocked


FINAL_FAILED_PAYMENT_STATUSES = {
    PaymentStatus.FAILED,
    PaymentStatus.CANCELLED,
    PaymentStatus.EXPIRED,
}


def is_telegram_notification_delivery_enabled() -> bool:
    return bool(settings.telegram_bot_token.strip())


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _format_amount(amount: int, currency: str) -> str:
    if currency == "RUB":
        return f"{amount} ₽"
    return f"{amount} {currency}"


def _is_telegram_bot_blocked_error(*, status_code: int, description: str) -> bool:
    normalized = description.strip().lower()
    return status_code == 403 and "bot was blocked by the user" in normalized


def _format_subscription_days_left(days_left: int) -> str:
    remainder_10 = days_left % 10
    remainder_100 = days_left % 100
    if remainder_10 == 1 and remainder_100 != 11:
        suffix = translate("api.notifications.units.day.one")
    elif remainder_10 in {2, 3, 4} and remainder_100 not in {12, 13, 14}:
        suffix = translate("api.notifications.units.day.few")
    else:
        suffix = translate("api.notifications.units.day.many")
    return f"{days_left} {suffix}"


def _format_subscription_expiry_moment(expires_at: datetime | None) -> str | None:
    if expires_at is None:
        return None
    normalized = expires_at.astimezone(UTC)
    return normalized.strftime("%d.%m.%Y %H:%M UTC")


def _build_subscription_expiry_token(expires_at: datetime | None) -> str:
    if expires_at is None:
        return "unknown"
    return expires_at.astimezone(UTC).isoformat()


def _get_payment_provider_label(provider: PaymentProvider) -> str:
    if provider == PaymentProvider.YOOKASSA:
        return translate("api.payments.providers.yookassa")
    if provider == PaymentProvider.TELEGRAM_STARS:
        return translate("api.payments.providers.telegram_stars")
    return provider.value


def _get_payment_plan_name(payment: Payment) -> str | None:
    if not payment.plan_code:
        return None
    try:
        return get_subscription_plan(payment.plan_code).name
    except SubscriptionPlanError:
        return payment.plan_code


def _normalize_notification_channels(
    channels: tuple[NotificationChannel, ...],
) -> tuple[NotificationChannel, ...]:
    unique_channels: list[NotificationChannel] = []
    for channel in channels:
        if channel not in unique_channels:
            unique_channels.append(channel)
    return tuple(unique_channels)


async def _resolve_notification_channels(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    channels: tuple[NotificationChannel, ...],
    deliver_to_telegram: bool,
) -> tuple[NotificationChannel, ...]:
    resolved_channels = list(_normalize_notification_channels(channels))
    if not deliver_to_telegram or not is_telegram_notification_delivery_enabled():
        return tuple(resolved_channels)

    account_row = (
        await session.execute(
            select(Account.telegram_id, Account.telegram_bot_blocked_at).where(
                Account.id == account_id
            )
        )
    ).one_or_none()
    if (
        account_row is not None
        and account_row[0] is not None
        and account_row[1] is None
        and NotificationChannel.TELEGRAM not in resolved_channels
    ):
        resolved_channels.append(NotificationChannel.TELEGRAM)
    return tuple(resolved_channels)


def _format_telegram_notification_text(notification: Notification) -> str:
    parts = [notification.title.strip(), notification.body.strip()]
    if notification.action_url:
        if notification.action_label:
            parts.append(f"{notification.action_label}: {notification.action_url}")
        else:
            parts.append(notification.action_url)
    return "\n\n".join(part for part in parts if part)


def _calculate_retry_delay_seconds(
    *,
    attempts_count: int,
    retry_after_seconds: int | None = None,
) -> int:
    if retry_after_seconds is not None and retry_after_seconds > 0:
        return retry_after_seconds

    base_seconds = max(5, int(settings.notification_telegram_retry_base_seconds))
    max_seconds = max(
        base_seconds, int(settings.notification_telegram_retry_max_seconds)
    )
    exponent = max(0, attempts_count - 1)
    return min(max_seconds, base_seconds * (2**exponent))


class TelegramNotificationClient:
    def __init__(
        self,
        *,
        bot_token: str,
        api_base_url: str = "https://api.telegram.org",
        timeout_seconds: float = 10.0,
    ) -> None:
        normalized_token = bot_token.strip()
        if not normalized_token:
            raise TelegramNotificationConfigurationError(
                "Telegram bot token is not configured"
            )
        self._bot_token = normalized_token
        self._client = httpx.AsyncClient(
            base_url=api_base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, *, json: dict) -> dict:
        try:
            response = await self._client.post(
                f"/bot{self._bot_token}/{method}",
                json=json,
            )
        except httpx.HTTPError as exc:
            raise TelegramNotificationDeliveryError(
                "Telegram API request failed",
                code="http_error",
                retryable=True,
            ) from exc

        payload = response.json()
        if response.status_code == 429:
            retry_after = payload.get("parameters", {}).get("retry_after")
            raise TelegramNotificationDeliveryError(
                str(payload.get("description") or "Telegram rate limit exceeded"),
                code="rate_limited",
                retryable=True,
                retry_after_seconds=int(retry_after)
                if isinstance(retry_after, int)
                else None,
            )

        if response.status_code >= 500:
            raise TelegramNotificationDeliveryError(
                str(payload.get("description") or "Telegram server error"),
                code=f"http_{response.status_code}",
                retryable=True,
            )

        if response.status_code >= 400 or payload.get("ok") is False:
            description = str(
                payload.get("description") or "Telegram API rejected the message"
            )
            if _is_telegram_bot_blocked_error(
                status_code=response.status_code,
                description=description,
            ):
                raise TelegramNotificationDeliveryError(
                    description,
                    code="telegram_bot_blocked",
                    retryable=False,
                    mark_telegram_bot_blocked=True,
                )
            raise TelegramNotificationDeliveryError(
                description,
                code=f"http_{response.status_code}",
                retryable=False,
            )

        result = payload.get("result") or {}
        if not isinstance(result, dict):
            raise TelegramNotificationDeliveryError(
                "Telegram API did not return a valid result payload",
                code="invalid_result",
                retryable=True,
            )
        return result

    async def send_message(
        self,
        *,
        telegram_id: int,
        text: str,
        parse_mode: str | None = None,
        disable_web_page_preview: bool | None = True,
        reply_markup: dict | None = None,
    ) -> str:
        payload: dict[str, object] = {
            "chat_id": telegram_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if disable_web_page_preview is not None:
            payload["disable_web_page_preview"] = disable_web_page_preview
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = await self._request("sendMessage", json=payload)
        message_id = result.get("message_id")
        if message_id is None:
            raise TelegramNotificationDeliveryError(
                "Telegram API did not return message_id",
                code="missing_message_id",
                retryable=True,
            )
        return str(message_id)

    async def send_photo(
        self,
        *,
        telegram_id: int,
        photo_url: str,
        caption: str | None = None,
        parse_mode: str | None = None,
        reply_markup: dict | None = None,
    ) -> str:
        payload: dict[str, object] = {
            "chat_id": telegram_id,
            "photo": photo_url,
        }
        if caption:
            payload["caption"] = caption
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = await self._request("sendPhoto", json=payload)
        message_id = result.get("message_id")
        if message_id is None:
            raise TelegramNotificationDeliveryError(
                "Telegram API did not return message_id",
                code="missing_message_id",
                retryable=True,
            )
        return str(message_id)


def get_telegram_notification_client() -> TelegramNotificationClient:
    return TelegramNotificationClient(bot_token=settings.telegram_bot_token)


class TelegramDeliveryProcessResult:
    __slots__ = ("processed", "delivered", "scheduled_retry", "terminal_failed")

    def __init__(self) -> None:
        self.processed = 0
        self.delivered = 0
        self.scheduled_retry = 0
        self.terminal_failed = 0


async def create_notification(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    type: NotificationType,
    title: str,
    body: str,
    priority: NotificationPriority = NotificationPriority.INFO,
    payload: dict | None = None,
    action_label: str | None = None,
    action_url: str | None = None,
    dedupe_key: str | None = None,
    channels: tuple[NotificationChannel, ...] = (NotificationChannel.IN_APP,),
    deliver_to_telegram: bool = True,
) -> Notification | None:
    normalized_title = _normalize_required_text(title, field_name="title")
    normalized_body = _normalize_required_text(body, field_name="body")
    normalized_action_label = _normalize_optional_text(action_label)
    normalized_action_url = _normalize_optional_text(action_url)
    normalized_dedupe_key = _normalize_optional_text(dedupe_key)

    account_exists = await session.scalar(
        select(Account.id).where(Account.id == account_id)
    )
    if account_exists is None:
        logger.warning(
            "Skipping notification for missing account_id=%s type=%s dedupe_key=%s",
            account_id,
            type.value,
            normalized_dedupe_key,
        )
        return None

    if normalized_dedupe_key:
        result = await session.execute(
            select(Notification).where(
                Notification.account_id == account_id,
                Notification.dedupe_key == normalized_dedupe_key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

    notification = Notification(
        account_id=account_id,
        type=type,
        title=normalized_title,
        body=normalized_body,
        priority=priority,
        payload=payload,
        action_label=normalized_action_label,
        action_url=normalized_action_url,
        dedupe_key=normalized_dedupe_key,
    )
    session.add(notification)
    await session.flush()

    resolved_channels = await _resolve_notification_channels(
        session,
        account_id=account_id,
        channels=channels,
        deliver_to_telegram=deliver_to_telegram,
    )
    now = datetime.now(UTC)
    for channel in resolved_channels:
        if channel == NotificationChannel.IN_APP:
            delivery = NotificationDelivery(
                notification_id=notification.id,
                channel=channel,
                status=NotificationDeliveryStatus.DELIVERED,
                attempts_count=1,
                last_attempt_at=now,
                delivered_at=now,
            )
        else:
            delivery = NotificationDelivery(
                notification_id=notification.id,
                channel=channel,
                status=NotificationDeliveryStatus.PENDING,
                attempts_count=0,
            )
        session.add(delivery)

    await session.flush()
    return notification


async def notify_payment_succeeded(
    session: AsyncSession,
    *,
    payment: Payment,
) -> Notification:
    if payment.flow_type == PaymentFlowType.WALLET_TOPUP:
        title = translate("api.notifications.payment_succeeded.topup.title")
        body = translate(
            "api.notifications.payment_succeeded.topup.body",
            amount=_format_amount(payment.amount, payment.currency),
            provider=_get_payment_provider_label(payment.provider),
        )
    else:
        plan_name = _get_payment_plan_name(payment) or translate(
            "api.notifications.plan_fallback"
        )
        title = translate("api.notifications.payment_succeeded.plan.title")
        body = translate(
            "api.notifications.payment_succeeded.plan.body",
            plan_name=plan_name,
        )

    return await create_notification(
        session,
        account_id=payment.account_id,
        type=NotificationType.PAYMENT_SUCCEEDED,
        title=title,
        body=body,
        priority=NotificationPriority.SUCCESS,
        payload={
            "payment_id": payment.id,
            "amount": payment.amount,
            "currency": payment.currency,
            "provider": payment.provider.value,
            "plan_code": payment.plan_code,
            "flow_type": payment.flow_type.value,
        },
        dedupe_key=f"payment_succeeded:{payment.id}",
    )


async def notify_payment_failed(
    session: AsyncSession,
    *,
    payment: Payment,
    status: PaymentStatus | None = None,
) -> Notification:
    resolved_status = status or payment.status
    if resolved_status not in FINAL_FAILED_PAYMENT_STATUSES:
        raise ValueError(f"unsupported failed payment status: {resolved_status}")

    provider_label = _get_payment_provider_label(payment.provider)
    if payment.flow_type == PaymentFlowType.WALLET_TOPUP:
        title = translate("api.notifications.payment_failed.topup.title")
        body = translate(
            "api.notifications.payment_failed.topup.body",
            amount=_format_amount(payment.amount, payment.currency),
            provider=provider_label,
        )
    else:
        plan_name = _get_payment_plan_name(payment) or translate(
            "api.notifications.plan_fallback"
        )
        title = translate("api.notifications.payment_failed.plan.title")
        body = translate(
            "api.notifications.payment_failed.plan.body",
            plan_name=plan_name,
            provider=provider_label,
        )

    return await create_notification(
        session,
        account_id=payment.account_id,
        type=NotificationType.PAYMENT_FAILED,
        title=title,
        body=body,
        priority=NotificationPriority.ERROR,
        payload={
            "payment_id": payment.id,
            "amount": payment.amount,
            "currency": payment.currency,
            "provider": payment.provider.value,
            "plan_code": payment.plan_code,
            "flow_type": payment.flow_type.value,
            "status": resolved_status.value,
        },
        dedupe_key=f"payment_failed:{payment.id}:{resolved_status.value}",
    )


async def notify_referral_reward_received(
    session: AsyncSession,
    *,
    reward: ReferralReward,
) -> Notification:
    return await create_notification(
        session,
        account_id=reward.referrer_account_id,
        type=NotificationType.REFERRAL_REWARD_RECEIVED,
        title=translate("api.notifications.referral_reward_received.title"),
        body=translate(
            "api.notifications.referral_reward_received.body",
            amount=_format_amount(int(reward.reward_amount), reward.currency),
        ),
        priority=NotificationPriority.SUCCESS,
        payload={
            "reward_id": reward.id,
            "reward_amount": int(reward.reward_amount),
            "currency": reward.currency,
            "referred_account_id": str(reward.referred_account_id),
            "subscription_grant_id": reward.subscription_grant_id,
        },
        dedupe_key=f"referral_reward:{reward.subscription_grant_id}",
    )


async def notify_subscription_expiring(
    session: AsyncSession,
    *,
    account: Account,
    days_left: int,
    expires_at: datetime | None,
    remnawave_event: str,
) -> Notification:
    if days_left <= 0:
        raise ValueError("days_left must be positive")

    deadline_text = _format_subscription_expiry_moment(expires_at)
    body = translate(
        "api.notifications.subscription_expiring.body",
        days_left=_format_subscription_days_left(days_left),
    )
    if deadline_text:
        body += translate(
            "api.notifications.subscription_expiring.deadline_suffix",
            expires_at=deadline_text,
        )

    expires_token = _build_subscription_expiry_token(expires_at)
    return await create_notification(
        session,
        account_id=account.id,
        type=NotificationType.SUBSCRIPTION_EXPIRING,
        title=translate("api.notifications.subscription_expiring.title"),
        body=body,
        priority=NotificationPriority.WARNING,
        payload={
            "days_left": days_left,
            "expires_at": expires_at.isoformat() if expires_at is not None else None,
            "remnawave_event": remnawave_event,
            "remnawave_user_uuid": str(account.remnawave_user_uuid or account.id),
        },
        dedupe_key=f"subscription_expiring:{account.id}:{days_left}:{expires_token}",
    )


async def notify_subscription_expired(
    session: AsyncSession,
    *,
    account: Account,
    expires_at: datetime | None,
    remnawave_event: str,
) -> Notification:
    deadline_text = _format_subscription_expiry_moment(expires_at)
    body = translate("api.notifications.subscription_expired.body")
    if deadline_text:
        body += translate(
            "api.notifications.subscription_expired.deadline_suffix",
            expires_at=deadline_text,
        )
    body += translate("api.notifications.subscription_expired.action_hint")

    expires_token = _build_subscription_expiry_token(expires_at)
    return await create_notification(
        session,
        account_id=account.id,
        type=NotificationType.SUBSCRIPTION_EXPIRED,
        title=translate("api.notifications.subscription_expired.title"),
        body=body,
        priority=NotificationPriority.ERROR,
        payload={
            "expires_at": expires_at.isoformat() if expires_at is not None else None,
            "remnawave_event": remnawave_event,
            "remnawave_user_uuid": str(account.remnawave_user_uuid or account.id),
        },
        dedupe_key=f"subscription_expired:{account.id}:{expires_token}",
    )


async def notify_withdrawal_created(
    session: AsyncSession,
    *,
    withdrawal: Withdrawal,
) -> Notification:
    return await create_notification(
        session,
        account_id=withdrawal.account_id,
        type=NotificationType.WITHDRAWAL_CREATED,
        title=translate("api.notifications.withdrawal_created.title"),
        body=translate(
            "api.notifications.withdrawal_created.body",
            amount=_format_amount(int(withdrawal.amount), "RUB"),
        ),
        priority=NotificationPriority.INFO,
        payload={
            "withdrawal_id": withdrawal.id,
            "amount": int(withdrawal.amount),
            "destination_type": withdrawal.destination_type.value,
            "status": withdrawal.status.value,
        },
        dedupe_key=f"withdrawal_created:{withdrawal.id}",
    )


async def notify_withdrawal_paid(
    session: AsyncSession,
    *,
    withdrawal: Withdrawal,
) -> Notification:
    return await create_notification(
        session,
        account_id=withdrawal.account_id,
        type=NotificationType.WITHDRAWAL_PAID,
        title=translate("api.notifications.withdrawal_paid.title"),
        body=translate(
            "api.notifications.withdrawal_paid.body",
            amount=_format_amount(int(withdrawal.amount), "RUB"),
        ),
        priority=NotificationPriority.INFO,
        payload={
            "withdrawal_id": withdrawal.id,
            "amount": int(withdrawal.amount),
            "destination_type": withdrawal.destination_type.value,
            "status": withdrawal.status.value,
        },
        dedupe_key=f"withdrawal_paid:{withdrawal.id}",
    )


async def notify_withdrawal_rejected(
    session: AsyncSession,
    *,
    withdrawal: Withdrawal,
) -> Notification:
    return await create_notification(
        session,
        account_id=withdrawal.account_id,
        type=NotificationType.WITHDRAWAL_REJECTED,
        title=translate("api.notifications.withdrawal_rejected.title"),
        body=translate(
            "api.notifications.withdrawal_rejected.body",
            amount=_format_amount(int(withdrawal.amount), "RUB"),
        ),
        priority=NotificationPriority.WARNING,
        payload={
            "withdrawal_id": withdrawal.id,
            "amount": int(withdrawal.amount),
            "destination_type": withdrawal.destination_type.value,
            "status": withdrawal.status.value,
        },
        dedupe_key=f"withdrawal_rejected:{withdrawal.id}",
    )


async def process_pending_telegram_deliveries(
    session: AsyncSession,
    *,
    limit: int,
    client: TelegramNotificationClient | None = None,
) -> TelegramDeliveryProcessResult:
    result = TelegramDeliveryProcessResult()
    if limit <= 0 or not is_telegram_notification_delivery_enabled():
        return result

    now = datetime.now(UTC)
    should_close_client = client is None
    telegram_client = client or get_telegram_notification_client()

    query = (
        select(NotificationDelivery, Notification, Account)
        .join(Notification, Notification.id == NotificationDelivery.notification_id)
        .join(Account, Account.id == Notification.account_id)
        .where(
            NotificationDelivery.channel == NotificationChannel.TELEGRAM,
            or_(
                NotificationDelivery.status == NotificationDeliveryStatus.PENDING,
                and_(
                    NotificationDelivery.status == NotificationDeliveryStatus.FAILED,
                    NotificationDelivery.next_retry_at.is_not(None),
                    NotificationDelivery.next_retry_at <= now,
                ),
            ),
        )
        .order_by(
            NotificationDelivery.next_retry_at.asc().nullsfirst(),
            NotificationDelivery.created_at.asc(),
            NotificationDelivery.id.asc(),
        )
        .limit(limit)
    )
    rows = await session.execute(query)

    try:
        for delivery, notification, account in rows.all():
            result.processed += 1
            delivery.attempts_count += 1
            delivery.last_attempt_at = now
            delivery.error_code = None
            delivery.error_message = None

            if account.telegram_id is None:
                delivery.status = NotificationDeliveryStatus.FAILED
                delivery.next_retry_at = None
                delivery.error_code = "missing_telegram_id"
                delivery.error_message = "Account does not have telegram_id"
                result.terminal_failed += 1
                continue

            if account.telegram_bot_blocked_at is not None:
                delivery.status = NotificationDeliveryStatus.FAILED
                delivery.next_retry_at = None
                delivery.error_code = "telegram_bot_blocked"
                delivery.error_message = "account previously blocked the Telegram bot"
                result.terminal_failed += 1
                continue

            try:
                provider_message_id = await telegram_client.send_message(
                    telegram_id=int(account.telegram_id),
                    text=_format_telegram_notification_text(notification),
                )
            except TelegramNotificationDeliveryError as exc:
                delivery.status = NotificationDeliveryStatus.FAILED
                delivery.error_code = exc.code
                delivery.error_message = str(exc)
                if exc.mark_telegram_bot_blocked:
                    await mark_telegram_bot_blocked(
                        session,
                        account=account,
                        blocked_at=now,
                    )

                max_attempts = max(1, int(settings.notification_telegram_max_attempts))
                if exc.retryable and delivery.attempts_count < max_attempts:
                    delay_seconds = _calculate_retry_delay_seconds(
                        attempts_count=delivery.attempts_count,
                        retry_after_seconds=exc.retry_after_seconds,
                    )
                    delivery.next_retry_at = now + timedelta(seconds=delay_seconds)
                    result.scheduled_retry += 1
                else:
                    delivery.next_retry_at = None
                    result.terminal_failed += 1
                continue

            delivery.status = NotificationDeliveryStatus.DELIVERED
            delivery.provider_message_id = provider_message_id
            delivery.delivered_at = now
            delivery.next_retry_at = None
            result.delivered += 1

        await session.flush()
        return result
    finally:
        if should_close_client:
            await telegram_client.close()


async def get_account_notifications(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    limit: int,
    offset: int,
    unread_only: bool = False,
) -> tuple[list[Notification], int, int]:
    filters = [Notification.account_id == account_id]
    if unread_only:
        filters.append(Notification.read_at.is_(None))

    total = await session.scalar(
        select(func.count()).select_from(Notification).where(*filters)
    )
    unread_count = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.account_id == account_id, Notification.read_at.is_(None))
    )
    result = await session.execute(
        select(Notification)
        .where(*filters)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0), int(unread_count or 0)


async def get_account_unread_notifications_count(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
) -> int:
    unread_count = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.account_id == account_id, Notification.read_at.is_(None))
    )
    return int(unread_count or 0)


async def mark_notification_read(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    notification_id: int,
) -> Notification:
    result = await session.execute(
        select(Notification)
        .where(
            Notification.id == notification_id, Notification.account_id == account_id
        )
        .with_for_update()
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise NotificationNotFoundError(translate("api.notifications.errors.not_found"))

    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        await session.flush()
    return notification


async def mark_all_notifications_read(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
) -> int:
    now = datetime.now(UTC)
    result = await session.execute(
        update(Notification)
        .where(Notification.account_id == account_id, Notification.read_at.is_(None))
        .values(read_at=now)
    )
    return int(result.rowcount or 0)
