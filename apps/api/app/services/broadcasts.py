from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
import html
from html.parser import HTMLParser
import re
import uuid
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from sqlalchemy import Select, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.db.models import (
    Account,
    AccountStatus,
    AdminActionLog,
    AdminActionType,
    AuthAccount,
    Broadcast,
    BroadcastAudienceSegment,
    BroadcastAudiencePreset,
    BroadcastChannel,
    BroadcastContentType,
    BroadcastDelivery,
    BroadcastDeliveryStatus,
    BroadcastRun,
    BroadcastRunStatus,
    BroadcastRunType,
    BroadcastStatus,
    NotificationChannel,
    NotificationPriority,
    NotificationType,
    Payment,
)
from app.domain.payments import PaymentFlowType, PaymentStatus
from app.services.accounts import mark_telegram_bot_blocked
from app.services.notifications import (
    TelegramNotificationConfigurationError,
    TelegramNotificationDeliveryError,
    create_notification,
    get_telegram_notification_client,
)


class BroadcastServiceError(Exception):
    pass


class BroadcastNotFoundError(BroadcastServiceError):
    pass


class BroadcastConflictError(BroadcastServiceError):
    pass


class BroadcastValidationError(BroadcastServiceError):
    pass


class BroadcastAudiencePresetNotFoundError(BroadcastServiceError):
    pass


@dataclass(slots=True)
class BroadcastAudienceEstimate:
    total_accounts: int
    in_app_recipients: int
    telegram_recipients: int


@dataclass(slots=True)
class BroadcastAudiencePreviewItem:
    account: Account
    match_reasons: list[str]
    delivery_channels: list[BroadcastChannel]
    delivery_notes: list[str]


@dataclass(slots=True)
class BroadcastAudiencePreview:
    total_accounts: int
    limit: int
    has_more: bool
    items: list[BroadcastAudiencePreviewItem]
    manual_list_diagnostics: BroadcastAudienceManualListDiagnostics | None = None


@dataclass(slots=True)
class BroadcastAudienceManualListExcludedAccount:
    account: Account
    matched_by: list[str]
    reasons: list[str]


@dataclass(slots=True)
class BroadcastAudienceManualListDiagnostics:
    requested_account_ids: int
    requested_emails: int
    requested_telegram_ids: int
    matched_accounts: int
    final_accounts: int
    unresolved_account_ids: list[str]
    unresolved_emails: list[str]
    unresolved_telegram_ids: list[int]
    excluded_accounts: list[BroadcastAudienceManualListExcludedAccount]


@dataclass(slots=True, frozen=True)
class BroadcastAudienceConfig:
    segment: BroadcastAudienceSegment
    exclude_blocked: bool = True
    manual_account_ids: tuple[uuid.UUID, ...] = ()
    manual_emails: tuple[str, ...] = ()
    manual_telegram_ids: tuple[int, ...] = ()
    last_seen_older_than_days: int | None = None
    include_never_seen: bool = False
    pending_payment_older_than_minutes: int | None = None
    pending_payment_within_last_days: int | None = None
    failed_payment_within_last_days: int | None = None
    subscription_expired_from_days: int | None = None
    subscription_expired_to_days: int | None = None
    cooldown_days: int | None = None
    cooldown_key: str | None = None
    telegram_quiet_hours_start: str | None = None
    telegram_quiet_hours_end: str | None = None


@dataclass(slots=True)
class BroadcastRunCounters:
    total_deliveries: int = 0
    pending_deliveries: int = 0
    delivered_deliveries: int = 0
    failed_deliveries: int = 0
    skipped_deliveries: int = 0
    in_app_delivered: int = 0
    telegram_delivered: int = 0
    in_app_pending: int = 0
    telegram_pending: int = 0


@dataclass(slots=True)
class BroadcastRunWithCounters:
    run: BroadcastRun
    counters: BroadcastRunCounters


@dataclass(slots=True)
class BroadcastSchedulerResult:
    started_runs: int = 0


@dataclass(slots=True)
class BroadcastDeliveryProcessResult:
    processed: int = 0
    delivered: int = 0
    scheduled_retry: int = 0
    terminal_failed: int = 0
    skipped: int = 0


@dataclass(slots=True)
class BroadcastTestSendTargetResult:
    target: str
    source: str
    resolution: str
    status: str
    account_id: uuid.UUID | None = None
    telegram_id: int | None = None
    channels_attempted: list[str] = field(default_factory=list)
    in_app_notification_id: int | None = None
    telegram_message_ids: list[str] = field(default_factory=list)
    detail: str | None = None


@dataclass(slots=True)
class BroadcastTestSendResult:
    broadcast_id: int
    audit_log_id: int
    total_targets: int
    sent_targets: int
    partial_targets: int
    failed_targets: int
    skipped_targets: int
    resolved_account_targets: int
    direct_telegram_targets: int
    in_app_notifications_created: int
    telegram_targets_sent: int
    items: list[BroadcastTestSendTargetResult]


BROADCAST_TZ = ZoneInfo(settings.broadcast_timezone)
TELEGRAM_PHOTO_CAPTION_MAX_LENGTH = 1024
ABANDONED_CHECKOUT_DEFAULT_OLDER_THAN_MINUTES = 30
ABANDONED_CHECKOUT_DEFAULT_WITHIN_LAST_DAYS = 7
FAILED_PAYMENT_DEFAULT_WITHIN_LAST_DAYS = 7
MANUAL_LIST_MAX_IDENTIFIERS = 5000
INACTIVE_AUDIENCE_DEFAULT_OLDER_THAN_DAYS = 7
MANUAL_LIST_DIAGNOSTIC_SAMPLE_LIMIT = 20
DIRECT_PLAN_PENDING_STATUSES = (
    PaymentStatus.CREATED,
    PaymentStatus.PENDING,
    PaymentStatus.REQUIRES_ACTION,
)
DIRECT_PLAN_FAILED_STATUSES = (
    PaymentStatus.FAILED,
    PaymentStatus.CANCELLED,
    PaymentStatus.EXPIRED,
)


class _TelegramHtmlSubsetValidator(HTMLParser):
    _allowed_tags = {
        "a": {"href"},
        "b": set(),
        "blockquote": set(),
        "code": set(),
        "del": set(),
        "em": set(),
        "i": set(),
        "ins": set(),
        "pre": set(),
        "s": set(),
        "strike": set(),
        "strong": set(),
        "tg-spoiler": set(),
        "u": set(),
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self._allowed_tags:
            self.errors.append(f"unsupported telegram html tag: <{tag}>")
            return

        allowed_attributes = self._allowed_tags[tag]
        for attribute_name, attribute_value in attrs:
            if attribute_name not in allowed_attributes:
                self.errors.append(
                    f"unsupported attribute for <{tag}>: {attribute_name}"
                )
                continue
            if tag == "a" and attribute_name == "href":
                if attribute_value is None or not _is_allowed_button_url(attribute_value):
                    self.errors.append("anchor href must be a valid http/https/tg URL")
        self._stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag not in self._allowed_tags:
            self.errors.append(f"unsupported telegram html closing tag: </{tag}>")
            return
        if not self._stack:
            self.errors.append(f"unexpected closing tag: </{tag}>")
            return
        if self._stack[-1] != tag:
            self.errors.append(f"telegram html tags must be properly nested: </{tag}>")
            return
        self._stack.pop()

    def close(self) -> None:
        super().close()
        if self._stack:
            self.errors.append(f"unclosed telegram html tag: <{self._stack[-1]}>")


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise BroadcastValidationError(f"{field_name} is required")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_broadcast_audience_preset_name(value: str) -> str:
    normalized = _normalize_required_text(value, field_name="name")
    if len(normalized) > 255:
        raise BroadcastValidationError("name is too long")
    return normalized


def _normalize_broadcast_audience_preset_description(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is not None and len(normalized) > 2000:
        raise BroadcastValidationError("description is too long")
    return normalized


def _is_allowed_button_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https", "tg"} and bool(parsed.netloc or parsed.path)


def _normalize_test_target_emails(emails: list[str]) -> list[str]:
    normalized_items: list[str] = []
    seen: set[str] = set()
    for raw_email in emails:
        email_value = raw_email.strip().lower()
        if not email_value or email_value in seen:
            continue
        seen.add(email_value)
        normalized_items.append(email_value)
    return normalized_items


def _normalize_test_target_telegram_ids(telegram_ids: list[int]) -> list[int]:
    normalized_items: list[int] = []
    seen: set[int] = set()
    for telegram_id in telegram_ids:
        normalized_value = int(telegram_id)
        if normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized_items.append(normalized_value)
    return normalized_items


def _broadcast_title_html(title: str) -> str:
    return f"<b>{html.escape(title)}</b>"


def build_broadcast_telegram_html(broadcast: Broadcast) -> str:
    return "\n\n".join(
        part
        for part in (
            _broadcast_title_html(broadcast.title),
            broadcast.body_html.strip(),
        )
        if part
    )


def build_broadcast_in_app_body(body_html: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", body_html)
    normalized = html.unescape(without_tags).replace("\r\n", "\n").strip()
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized


def build_broadcast_notification_payload(broadcast: Broadcast) -> dict[str, object]:
    return {
        "broadcast_id": broadcast.id,
        "content_type": broadcast.content_type.value,
        "image_url": broadcast.image_url,
        "body_html": broadcast.body_html,
        "buttons": broadcast.buttons,
    }


def _normalize_scheduled_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=BROADCAST_TZ)
    return value.astimezone(BROADCAST_TZ)


def _now_moscow() -> datetime:
    return datetime.now(BROADCAST_TZ)


def _normalize_optional_int(
    value: object,
    *,
    field_name: str,
    min_value: int = 0,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise BroadcastValidationError(f"{field_name} must be an integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise BroadcastValidationError(f"{field_name} must be an integer") from exc
    if normalized < min_value:
        raise BroadcastValidationError(f"{field_name} must be >= {min_value}")
    return normalized


def _normalize_optional_cooldown_key(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BroadcastValidationError("cooldown_key must be a string")
    normalized = value.strip().lower()
    if not normalized:
        return None
    if len(normalized) > 64:
        raise BroadcastValidationError("cooldown_key must be <= 64 characters")
    return normalized


def _normalize_manual_account_ids(value: object) -> tuple[uuid.UUID, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise BroadcastValidationError("manual_account_ids must be a list")

    normalized_items: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for item in value:
        try:
            normalized_value = item if isinstance(item, uuid.UUID) else uuid.UUID(str(item).strip())
        except (TypeError, ValueError, AttributeError) as exc:
            raise BroadcastValidationError("manual_account_ids must contain valid UUIDs") from exc
        if normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized_items.append(normalized_value)
    return tuple(normalized_items)


def _normalize_manual_emails(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise BroadcastValidationError("manual_emails must be a list")

    normalized_items: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise BroadcastValidationError("manual_emails must contain strings")
        normalized_value = item.strip().lower()
        if not normalized_value or normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized_items.append(normalized_value)
    return tuple(normalized_items)


def _normalize_manual_telegram_ids(value: object) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise BroadcastValidationError("manual_telegram_ids must be a list")

    normalized_items: list[int] = []
    seen: set[int] = set()
    for item in value:
        if isinstance(item, bool):
            raise BroadcastValidationError("manual_telegram_ids must contain integers")
        try:
            normalized_value = int(item)
        except (TypeError, ValueError) as exc:
            raise BroadcastValidationError("manual_telegram_ids must contain integers") from exc
        if normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized_items.append(normalized_value)
    return tuple(normalized_items)


def _normalize_optional_hhmm_time(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BroadcastValidationError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        return None
    match = re.fullmatch(r"(\d{2}):(\d{2})", normalized)
    if match is None:
        raise BroadcastValidationError(f"{field_name} must use HH:MM format")
    hours = int(match.group(1))
    minutes = int(match.group(2))
    if hours > 23 or minutes > 59:
        raise BroadcastValidationError(f"{field_name} must be a valid time")
    return f"{hours:02d}:{minutes:02d}"


def _parse_hhmm_time(value: str) -> time:
    hours, minutes = value.split(":", maxsplit=1)
    return time(hour=int(hours), minute=int(minutes))


def normalize_broadcast_audience_config(
    *,
    audience: dict[str, object] | None = None,
) -> BroadcastAudienceConfig:
    raw_audience = audience or {}
    raw_segment = raw_audience.get("segment") or BroadcastAudienceSegment.ALL
    if isinstance(raw_segment, BroadcastAudienceSegment):
        segment = raw_segment
    else:
        try:
            segment = BroadcastAudienceSegment(str(raw_segment))
        except ValueError as exc:
            raise BroadcastValidationError(f"unsupported audience segment: {raw_segment}") from exc
    exclude_blocked = bool(raw_audience.get("exclude_blocked", True))
    manual_account_ids = _normalize_manual_account_ids(raw_audience.get("manual_account_ids"))
    manual_emails = _normalize_manual_emails(raw_audience.get("manual_emails"))
    manual_telegram_ids = _normalize_manual_telegram_ids(raw_audience.get("manual_telegram_ids"))
    last_seen_older_than_days = None
    include_never_seen = bool(raw_audience.get("include_never_seen", False))

    pending_payment_older_than_minutes = None
    pending_payment_within_last_days = None
    failed_payment_within_last_days = None
    subscription_expired_from_days = None
    subscription_expired_to_days = None
    cooldown_days = _normalize_optional_int(
        raw_audience.get("cooldown_days"),
        field_name="cooldown_days",
        min_value=1,
    )
    cooldown_key = _normalize_optional_cooldown_key(raw_audience.get("cooldown_key"))
    telegram_quiet_hours_start = _normalize_optional_hhmm_time(
        raw_audience.get("telegram_quiet_hours_start"),
        field_name="telegram_quiet_hours_start",
    )
    telegram_quiet_hours_end = _normalize_optional_hhmm_time(
        raw_audience.get("telegram_quiet_hours_end"),
        field_name="telegram_quiet_hours_end",
    )
    manual_identifiers_total = (
        len(manual_account_ids) + len(manual_emails) + len(manual_telegram_ids)
    )
    if manual_identifiers_total > MANUAL_LIST_MAX_IDENTIFIERS:
        raise BroadcastValidationError(
            f"manual audience supports at most {MANUAL_LIST_MAX_IDENTIFIERS} identifiers"
        )

    if segment == BroadcastAudienceSegment.MANUAL_LIST:
        if manual_identifiers_total == 0:
            raise BroadcastValidationError(
                "manual_list audience requires at least one account_id, email or telegram_id"
            )
    elif segment in {
        BroadcastAudienceSegment.INACTIVE_ACCOUNTS,
        BroadcastAudienceSegment.INACTIVE_PAID_USERS,
    }:
        last_seen_older_than_days = (
            _normalize_optional_int(
                raw_audience.get("last_seen_older_than_days"),
                field_name="last_seen_older_than_days",
                min_value=1,
            )
            or INACTIVE_AUDIENCE_DEFAULT_OLDER_THAN_DAYS
        )
    elif segment == BroadcastAudienceSegment.ABANDONED_CHECKOUT:
        pending_payment_older_than_minutes = (
            _normalize_optional_int(
                raw_audience.get("pending_payment_older_than_minutes"),
                field_name="pending_payment_older_than_minutes",
                min_value=1,
            )
            or ABANDONED_CHECKOUT_DEFAULT_OLDER_THAN_MINUTES
        )
        pending_payment_within_last_days = (
            _normalize_optional_int(
                raw_audience.get("pending_payment_within_last_days"),
                field_name="pending_payment_within_last_days",
                min_value=1,
            )
            or ABANDONED_CHECKOUT_DEFAULT_WITHIN_LAST_DAYS
        )
    elif segment == BroadcastAudienceSegment.FAILED_PAYMENT:
        failed_payment_within_last_days = (
            _normalize_optional_int(
                raw_audience.get("failed_payment_within_last_days"),
                field_name="failed_payment_within_last_days",
                min_value=1,
            )
            or FAILED_PAYMENT_DEFAULT_WITHIN_LAST_DAYS
        )
    elif segment == BroadcastAudienceSegment.EXPIRED:
        subscription_expired_from_days = _normalize_optional_int(
            raw_audience.get("subscription_expired_from_days"),
            field_name="subscription_expired_from_days",
            min_value=0,
        )
        subscription_expired_to_days = _normalize_optional_int(
            raw_audience.get("subscription_expired_to_days"),
            field_name="subscription_expired_to_days",
            min_value=0,
        )
        if (
            subscription_expired_from_days is not None
            and subscription_expired_to_days is not None
            and subscription_expired_from_days > subscription_expired_to_days
        ):
            raise BroadcastValidationError(
                "subscription_expired_from_days must be <= subscription_expired_to_days"
            )

    if (cooldown_days is None) != (cooldown_key is None):
        raise BroadcastValidationError("cooldown_days and cooldown_key must be provided together")
    if (telegram_quiet_hours_start is None) != (telegram_quiet_hours_end is None):
        raise BroadcastValidationError(
            "telegram_quiet_hours_start and telegram_quiet_hours_end must be provided together"
        )
    if (
        telegram_quiet_hours_start is not None
        and telegram_quiet_hours_end is not None
        and telegram_quiet_hours_start == telegram_quiet_hours_end
    ):
        raise BroadcastValidationError("telegram quiet hours start and end must differ")

    return BroadcastAudienceConfig(
        segment=segment,
        exclude_blocked=exclude_blocked,
        manual_account_ids=manual_account_ids,
        manual_emails=manual_emails,
        manual_telegram_ids=manual_telegram_ids,
        last_seen_older_than_days=last_seen_older_than_days,
        include_never_seen=include_never_seen,
        pending_payment_older_than_minutes=pending_payment_older_than_minutes,
        pending_payment_within_last_days=pending_payment_within_last_days,
        failed_payment_within_last_days=failed_payment_within_last_days,
        subscription_expired_from_days=subscription_expired_from_days,
        subscription_expired_to_days=subscription_expired_to_days,
        cooldown_days=cooldown_days,
        cooldown_key=cooldown_key,
        telegram_quiet_hours_start=telegram_quiet_hours_start,
        telegram_quiet_hours_end=telegram_quiet_hours_end,
    )


def _get_broadcast_audience_config(broadcast: Broadcast) -> BroadcastAudienceConfig:
    return normalize_broadcast_audience_config(audience=broadcast.audience)


def validate_broadcast_runtime_constraints(broadcast: Broadcast) -> None:
    channels = normalize_broadcast_channels(broadcast.channels)
    if (
        broadcast.content_type == BroadcastContentType.PHOTO
        and BroadcastChannel.TELEGRAM.value in channels
        and len(build_broadcast_telegram_html(broadcast)) > TELEGRAM_PHOTO_CAPTION_MAX_LENGTH
    ):
        raise BroadcastValidationError(
            "photo broadcast caption is too long for Telegram; shorten title/body_html"
        )


def build_broadcast_telegram_reply_markup(
    buttons: list[dict[str, str]],
) -> dict[str, list[list[dict[str, str]]]] | None:
    if not buttons:
        return None

    return {
        "inline_keyboard": [
            [{"text": str(button["text"]), "url": str(button["url"])}] for button in buttons
        ]
    }


async def _resolve_accounts_by_emails(
    session: AsyncSession,
    *,
    emails: list[str],
) -> dict[str, Account]:
    if not emails:
        return {}

    result = await session.execute(
        select(Account, AuthAccount.email)
        .outerjoin(AuthAccount, AuthAccount.account_id == Account.id)
        .where(
            or_(
                func.lower(func.coalesce(Account.email, "")).in_(emails),
                func.lower(func.coalesce(AuthAccount.email, "")).in_(emails),
            )
        )
        .order_by(Account.created_at.desc())
    )

    resolved: dict[str, Account] = {}
    for account, auth_email in result.all():
        if account.email:
            lowered_account_email = account.email.strip().lower()
            if lowered_account_email in emails and lowered_account_email not in resolved:
                resolved[lowered_account_email] = account
        if auth_email:
            lowered_auth_email = auth_email.strip().lower()
            if lowered_auth_email in emails and lowered_auth_email not in resolved:
                resolved[lowered_auth_email] = account
    return resolved


async def _resolve_accounts_by_telegram_ids(
    session: AsyncSession,
    *,
    telegram_ids: list[int],
) -> dict[int, Account]:
    if not telegram_ids:
        return {}

    result = await session.execute(
        select(Account)
        .where(Account.telegram_id.in_(telegram_ids))
        .order_by(Account.created_at.desc())
    )
    resolved: dict[int, Account] = {}
    for account in result.scalars().all():
        if account.telegram_id is None:
            continue
        resolved.setdefault(int(account.telegram_id), account)
    return resolved


async def _send_broadcast_to_telegram(
    *,
    telegram_id: int,
    broadcast: Broadcast,
) -> list[str]:
    message_ids: list[str] = []
    reply_markup = build_broadcast_telegram_reply_markup(broadcast.buttons)
    client = get_telegram_notification_client()
    try:
        if broadcast.content_type == BroadcastContentType.PHOTO:
            image_url = _normalize_required_text(
                broadcast.image_url or "",
                field_name="image_url",
            )
            caption = build_broadcast_telegram_html(broadcast)
            if len(caption) > TELEGRAM_PHOTO_CAPTION_MAX_LENGTH:
                raise BroadcastValidationError(
                    "photo broadcast caption is too long for Telegram; shorten title/body_html"
                )
            photo_message_id = await client.send_photo(
                telegram_id=telegram_id,
                photo_url=image_url,
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            message_ids.append(photo_message_id)
        else:
            text_message_id = await client.send_message(
                telegram_id=telegram_id,
                text=build_broadcast_telegram_html(broadcast),
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=reply_markup,
            )
            message_ids.append(text_message_id)
    finally:
        await client.close()

    return message_ids

def validate_telegram_html_subset(value: str) -> str:
    normalized = _normalize_required_text(value, field_name="body_html")
    validator = _TelegramHtmlSubsetValidator()
    validator.feed(normalized)
    validator.close()
    if validator.errors:
        raise BroadcastValidationError(validator.errors[0])
    return normalized


def normalize_broadcast_buttons(buttons: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized_buttons: list[dict[str, str]] = []
    if len(buttons) > 3:
        raise BroadcastValidationError("buttons must contain at most 3 items")

    for button in buttons:
        text = _normalize_required_text(button.get("text", ""), field_name="button text")
        url = _normalize_required_text(button.get("url", ""), field_name="button url")
        if not _is_allowed_button_url(url):
            raise BroadcastValidationError("button url must use http, https or tg scheme")
        normalized_buttons.append({"text": text, "url": url})
    return normalized_buttons


def normalize_broadcast_channels(
    channels: tuple[BroadcastChannel, ...] | list[BroadcastChannel],
) -> list[str]:
    normalized_channels: list[str] = []
    for channel in channels:
        value = channel.value if isinstance(channel, BroadcastChannel) else str(channel)
        if value not in normalized_channels:
            normalized_channels.append(value)

    if not normalized_channels:
        raise BroadcastValidationError("at least one channel is required")
    return normalized_channels


def build_broadcast_audience_payload(
    *,
    audience: BroadcastAudienceConfig,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "segment": audience.segment.value,
        "exclude_blocked": audience.exclude_blocked,
    }
    if audience.manual_account_ids:
        payload["manual_account_ids"] = [str(item) for item in audience.manual_account_ids]
    if audience.manual_emails:
        payload["manual_emails"] = list(audience.manual_emails)
    if audience.manual_telegram_ids:
        payload["manual_telegram_ids"] = list(audience.manual_telegram_ids)
    if audience.last_seen_older_than_days is not None:
        payload["last_seen_older_than_days"] = audience.last_seen_older_than_days
    if audience.include_never_seen:
        payload["include_never_seen"] = audience.include_never_seen
    if audience.pending_payment_older_than_minutes is not None:
        payload["pending_payment_older_than_minutes"] = audience.pending_payment_older_than_minutes
    if audience.pending_payment_within_last_days is not None:
        payload["pending_payment_within_last_days"] = audience.pending_payment_within_last_days
    if audience.failed_payment_within_last_days is not None:
        payload["failed_payment_within_last_days"] = audience.failed_payment_within_last_days
    if audience.subscription_expired_from_days is not None:
        payload["subscription_expired_from_days"] = audience.subscription_expired_from_days
    if audience.subscription_expired_to_days is not None:
        payload["subscription_expired_to_days"] = audience.subscription_expired_to_days
    if audience.cooldown_days is not None:
        payload["cooldown_days"] = audience.cooldown_days
    if audience.cooldown_key is not None:
        payload["cooldown_key"] = audience.cooldown_key
    if audience.telegram_quiet_hours_start is not None:
        payload["telegram_quiet_hours_start"] = audience.telegram_quiet_hours_start
    if audience.telegram_quiet_hours_end is not None:
        payload["telegram_quiet_hours_end"] = audience.telegram_quiet_hours_end
    return payload


def _latest_direct_plan_payment_id_subquery():
    return (
        select(Payment.id)
        .where(
            Payment.account_id == Account.id,
            Payment.flow_type == PaymentFlowType.DIRECT_PLAN_PURCHASE,
        )
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .limit(1)
        .correlate(Account)
        .scalar_subquery()
    )


def _format_preview_relative_age(value: datetime, *, now: datetime) -> str:
    delta = now - value.astimezone(UTC)
    if delta.total_seconds() < 0:
        delta = timedelta(0)

    total_minutes = max(int(delta.total_seconds() // 60), 0)
    if total_minutes < 60:
        return f"{max(total_minutes, 1)} мин. назад"

    total_hours = total_minutes // 60
    if total_hours < 48:
        return f"{total_hours} ч. назад"

    return f"{delta.days} дн. назад"


async def _load_direct_plan_preview_payments(
    session: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
) -> tuple[dict[uuid.UUID, Payment], dict[uuid.UUID, Payment]]:
    if not account_ids:
        return {}, {}

    result = await session.execute(
        select(Payment)
        .where(
            Payment.account_id.in_(account_ids),
            Payment.flow_type == PaymentFlowType.DIRECT_PLAN_PURCHASE,
        )
        .order_by(Payment.account_id.asc(), Payment.created_at.desc(), Payment.id.desc())
    )

    latest_by_account: dict[uuid.UUID, Payment] = {}
    latest_succeeded_by_account: dict[uuid.UUID, Payment] = {}
    for payment in result.scalars().all():
        latest_by_account.setdefault(payment.account_id, payment)
        if payment.status == PaymentStatus.SUCCEEDED:
            latest_succeeded_by_account.setdefault(payment.account_id, payment)

    return latest_by_account, latest_succeeded_by_account


async def _load_auth_emails_for_accounts(
    session: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
) -> dict[uuid.UUID, set[str]]:
    if not account_ids:
        return {}

    result = await session.execute(
        select(AuthAccount.account_id, AuthAccount.email)
        .where(
            AuthAccount.account_id.in_(account_ids),
            AuthAccount.email.is_not(None),
        )
    )
    emails_by_account: dict[uuid.UUID, set[str]] = {}
    for account_id, email in result.all():
        if email is None:
            continue
        normalized_email = email.strip().lower()
        if not normalized_email:
            continue
        emails_by_account.setdefault(account_id, set()).add(normalized_email)
    return emails_by_account


async def _resolve_manual_list_accounts(
    session: AsyncSession,
    *,
    audience: BroadcastAudienceConfig,
) -> tuple[dict[uuid.UUID, Account], dict[uuid.UUID, set[str]], list[str], list[str], list[int]]:
    accounts_by_id: dict[uuid.UUID, Account] = {}
    matched_by_account: dict[uuid.UUID, set[str]] = {}

    unresolved_account_ids: list[str] = []
    if audience.manual_account_ids:
        result = await session.execute(
            select(Account).where(Account.id.in_(list(audience.manual_account_ids)))
        )
        resolved_account_ids: dict[uuid.UUID, Account] = {
            account.id: account for account in result.scalars().all()
        }
        for account in resolved_account_ids.values():
            accounts_by_id[account.id] = account
            matched_by_account.setdefault(account.id, set()).add(f"account_id:{account.id}")
        unresolved_account_ids = [
            str(account_id)
            for account_id in audience.manual_account_ids
            if account_id not in resolved_account_ids
        ]

    unresolved_emails: list[str] = []
    if audience.manual_emails:
        resolved_by_email = await _resolve_accounts_by_emails(
            session,
            emails=list(audience.manual_emails),
        )
        for email, account in resolved_by_email.items():
            accounts_by_id[account.id] = account
            matched_by_account.setdefault(account.id, set()).add(f"email:{email}")
        unresolved_emails = [
            email for email in audience.manual_emails if email not in resolved_by_email
        ]

    unresolved_telegram_ids: list[int] = []
    if audience.manual_telegram_ids:
        resolved_by_telegram_id = await _resolve_accounts_by_telegram_ids(
            session,
            telegram_ids=list(audience.manual_telegram_ids),
        )
        for telegram_id, account in resolved_by_telegram_id.items():
            accounts_by_id[account.id] = account
            matched_by_account.setdefault(account.id, set()).add(f"telegram_id:{telegram_id}")
        unresolved_telegram_ids = [
            telegram_id
            for telegram_id in audience.manual_telegram_ids
            if telegram_id not in resolved_by_telegram_id
        ]

    return (
        accounts_by_id,
        matched_by_account,
        unresolved_account_ids,
        unresolved_emails,
        unresolved_telegram_ids,
    )


async def _build_manual_list_preview_diagnostics(
    session: AsyncSession,
    *,
    audience: BroadcastAudienceConfig,
    final_accounts: int,
) -> BroadcastAudienceManualListDiagnostics | None:
    if audience.segment != BroadcastAudienceSegment.MANUAL_LIST:
        return None

    (
        accounts_by_id,
        matched_by_account,
        unresolved_account_ids,
        unresolved_emails,
        unresolved_telegram_ids,
    ) = await _resolve_manual_list_accounts(
        session,
        audience=audience,
    )
    final_account_ids = set(
        (
            await session.execute(
                _build_base_audience_query(audience=audience)
            )
        ).scalars().all()
    )

    excluded_accounts: list[BroadcastAudienceManualListExcludedAccount] = []
    for account_id, account in accounts_by_id.items():
        if account_id in final_account_ids:
            continue

        reasons: list[str] = []
        if audience.exclude_blocked and account.status == AccountStatus.BLOCKED:
            reasons.append("blocked")
        if (
            account.status != AccountStatus.BLOCKED
            and audience.cooldown_days is not None
            and audience.cooldown_key is not None
        ):
            reasons.append("cooldown")
        if not reasons:
            reasons.append("excluded")

        excluded_accounts.append(
            BroadcastAudienceManualListExcludedAccount(
                account=account,
                matched_by=sorted(matched_by_account.get(account_id, set())),
                reasons=reasons,
            )
        )

    return BroadcastAudienceManualListDiagnostics(
        requested_account_ids=len(audience.manual_account_ids),
        requested_emails=len(audience.manual_emails),
        requested_telegram_ids=len(audience.manual_telegram_ids),
        matched_accounts=len(accounts_by_id),
        final_accounts=final_accounts,
        unresolved_account_ids=unresolved_account_ids,
        unresolved_emails=unresolved_emails,
        unresolved_telegram_ids=unresolved_telegram_ids,
        excluded_accounts=excluded_accounts,
    )


def _build_broadcast_audience_match_reasons(
    *,
    account: Account,
    audience: BroadcastAudienceConfig,
    latest_direct_plan_payment: Payment | None,
    latest_succeeded_direct_plan_payment: Payment | None,
    auth_emails: set[str] | None,
    now: datetime,
) -> list[str]:
    if audience.segment == BroadcastAudienceSegment.ALL:
        return ["Входит в общий сегмент без дополнительных ограничений."]
    if audience.segment == BroadcastAudienceSegment.ACTIVE:
        return ["Аккаунт активен."]
    if audience.segment == BroadcastAudienceSegment.WITH_TELEGRAM:
        return ["Аккаунт привязан к Telegram."]
    if audience.segment == BroadcastAudienceSegment.PAID:
        if latest_succeeded_direct_plan_payment is not None:
            return [
                "Есть успешная покупка тарифа.",
                f"Последняя успешная оплата: {_format_preview_relative_age(latest_succeeded_direct_plan_payment.created_at, now=now)}.",
            ]
        return ["Есть успешная оплата."]
    if audience.segment == BroadcastAudienceSegment.MANUAL_LIST:
        reasons = ["Аккаунт выбран вручную по списку."]
        if account.id in audience.manual_account_ids:
            reasons.append(f"Совпал account_id: {account.id}.")
        matched_emails: list[str] = []
        if account.email is not None:
            normalized_account_email = account.email.strip().lower()
            if normalized_account_email and normalized_account_email in audience.manual_emails:
                matched_emails.append(normalized_account_email)
        if auth_emails:
            matched_emails.extend(
                email for email in sorted(auth_emails) if email in audience.manual_emails
            )
        if matched_emails:
            reasons.append(f"Совпал email: {', '.join(dict.fromkeys(matched_emails))}.")
        if account.telegram_id is not None and int(account.telegram_id) in audience.manual_telegram_ids:
            reasons.append(f"Совпал telegram_id: {account.telegram_id}.")
        return reasons
    if audience.segment == BroadcastAudienceSegment.INACTIVE_ACCOUNTS:
        if account.last_seen_at is not None:
            return [
                f"Аккаунт не заходил {_format_preview_relative_age(account.last_seen_at, now=now)}.",
                f"Порог неактивности: {audience.last_seen_older_than_days} дн.",
            ]
        return [
            "Аккаунт еще ни разу не заходил.",
            f"Порог неактивности: {audience.last_seen_older_than_days} дн.",
        ]
    if audience.segment == BroadcastAudienceSegment.INACTIVE_PAID_USERS:
        reasons = ["Раньше уже была успешная покупка тарифа."]
        if latest_succeeded_direct_plan_payment is not None:
            reasons.append(
                f"Последняя успешная оплата: {_format_preview_relative_age(latest_succeeded_direct_plan_payment.created_at, now=now)}."
            )
        if account.last_seen_at is not None:
            reasons.append(f"Не заходил {_format_preview_relative_age(account.last_seen_at, now=now)}.")
        else:
            reasons.append("После регистрации еще ни разу не заходил.")
        reasons.append(f"Порог неактивности: {audience.last_seen_older_than_days} дн.")
        return reasons
    if audience.segment == BroadcastAudienceSegment.EXPIRED:
        if account.subscription_expires_at is not None:
            return [
                f"Подписка истекла {_format_preview_relative_age(account.subscription_expires_at, now=now)}."
            ]
        return ["Подписка уже истекла."]
    if audience.segment == BroadcastAudienceSegment.ABANDONED_CHECKOUT:
        if latest_direct_plan_payment is not None:
            return [
                "Последняя попытка покупки тарифа не завершена.",
                f"Платеж создан {_format_preview_relative_age(latest_direct_plan_payment.created_at, now=now)}.",
            ]
        return ["Есть незавершенная покупка тарифа."]
    if audience.segment == BroadcastAudienceSegment.FAILED_PAYMENT:
        if latest_direct_plan_payment is not None:
            return [
                "Последняя попытка покупки тарифа завершилась неуспешно.",
                f"Платеж создан {_format_preview_relative_age(latest_direct_plan_payment.created_at, now=now)}.",
            ]
        return ["Есть неуспешная покупка тарифа."]
    if audience.segment == BroadcastAudienceSegment.TRIAL_ENDED_NO_CONVERSION:
        if account.trial_ends_at is not None:
            return [
                f"Trial завершился {_format_preview_relative_age(account.trial_ends_at, now=now)}.",
                "После trial нет успешной покупки тарифа.",
            ]
        return ["Trial завершился без конверсии в оплату."]
    if audience.segment == BroadcastAudienceSegment.PAID_BEFORE_NOT_ACTIVE_NOW:
        reasons = ["Раньше уже была успешная покупка тарифа."]
        if latest_succeeded_direct_plan_payment is not None:
            reasons.append(
                f"Последняя успешная оплата: {_format_preview_relative_age(latest_succeeded_direct_plan_payment.created_at, now=now)}."
            )
        if account.subscription_expires_at is not None:
            reasons.append(
                f"Текущая подписка не активна с {_format_preview_relative_age(account.subscription_expires_at, now=now)}."
            )
        else:
            reasons.append("Сейчас активной подписки нет.")
        return reasons
    return ["Аккаунт соответствует условиям сегмента."]


def _build_broadcast_audience_delivery_preview(
    *,
    account: Account,
    channels: list[str],
    audience: BroadcastAudienceConfig,
) -> tuple[list[BroadcastChannel], list[str]]:
    delivery_channels: list[BroadcastChannel] = []
    delivery_notes: list[str] = []

    if BroadcastChannel.IN_APP.value in channels:
        delivery_channels.append(BroadcastChannel.IN_APP)

    if BroadcastChannel.TELEGRAM.value in channels:
        if account.telegram_id is None:
            delivery_notes.append("Telegram недоступен: аккаунт не привязан к Telegram.")
        elif account.telegram_bot_blocked_at is not None:
            delivery_notes.append("Telegram недоступен: бот заблокирован пользователем.")
        else:
            delivery_channels.append(BroadcastChannel.TELEGRAM)
            quiet_until = _resolve_telegram_quiet_hours_release_at(
                audience=audience,
                now_moscow=_now_moscow(),
            )
            if quiet_until is not None:
                delivery_notes.append(
                    f"Telegram сейчас в quiet hours до {quiet_until.astimezone(BROADCAST_TZ).strftime('%H:%M')}."
                )

    if not delivery_channels:
        delivery_notes.append("По выбранным каналам у этого аккаунта не будет доставки.")

    return delivery_channels, delivery_notes


def _resolve_telegram_quiet_hours_release_at(
    *,
    audience: BroadcastAudienceConfig,
    now_moscow: datetime,
) -> datetime | None:
    if audience.telegram_quiet_hours_start is None or audience.telegram_quiet_hours_end is None:
        return None

    start_time = _parse_hhmm_time(audience.telegram_quiet_hours_start)
    end_time = _parse_hhmm_time(audience.telegram_quiet_hours_end)
    current_time = now_moscow.timetz().replace(tzinfo=None)

    if start_time < end_time:
        if not (start_time <= current_time < end_time):
            return None
        release_date = now_moscow.date()
    else:
        if not (current_time >= start_time or current_time < end_time):
            return None
        release_date = (
            now_moscow.date() + timedelta(days=1)
            if current_time >= start_time
            else now_moscow.date()
        )

    release_at = datetime.combine(release_date, end_time, tzinfo=BROADCAST_TZ)
    if release_at <= now_moscow:
        release_at += timedelta(days=1)
    return release_at.astimezone(UTC)


def _build_manual_list_account_predicate(
    *,
    audience: BroadcastAudienceConfig,
):
    conditions = []
    if audience.manual_account_ids:
        conditions.append(Account.id.in_(list(audience.manual_account_ids)))
    if audience.manual_emails:
        conditions.append(func.lower(func.coalesce(Account.email, "")).in_(list(audience.manual_emails)))
        conditions.append(
            exists(
                select(AuthAccount.id).where(
                    AuthAccount.account_id == Account.id,
                    func.lower(func.coalesce(AuthAccount.email, "")).in_(list(audience.manual_emails)),
                )
            )
        )
    if audience.manual_telegram_ids:
        conditions.append(Account.telegram_id.in_(list(audience.manual_telegram_ids)))
    if not conditions:
        raise BroadcastValidationError(
            "manual_list audience requires at least one account_id, email or telegram_id"
        )
    return or_(*conditions)


def _build_inactive_last_seen_predicate(
    *,
    audience: BroadcastAudienceConfig,
    now: datetime,
):
    cutoff = now - timedelta(days=audience.last_seen_older_than_days or 0)
    conditions = [Account.last_seen_at <= cutoff]
    if audience.include_never_seen:
        conditions.append(Account.last_seen_at.is_(None))
    return or_(*conditions)


def _build_base_audience_query(
    *,
    audience: BroadcastAudienceConfig,
) -> Select[tuple[Account.id]]:
    now = datetime.now(UTC)
    query = select(Account.id)

    if audience.exclude_blocked:
        query = query.where(Account.status != AccountStatus.BLOCKED)

    if audience.segment == BroadcastAudienceSegment.ACTIVE:
        query = query.where(Account.status == AccountStatus.ACTIVE)
    elif audience.segment == BroadcastAudienceSegment.WITH_TELEGRAM:
        query = query.where(Account.telegram_id.is_not(None))
    elif audience.segment == BroadcastAudienceSegment.PAID:
        query = query.where(
            exists(
                select(Payment.id).where(
                    Payment.account_id == Account.id,
                    Payment.status == PaymentStatus.SUCCEEDED,
                )
            )
        )
    elif audience.segment == BroadcastAudienceSegment.MANUAL_LIST:
        query = query.where(_build_manual_list_account_predicate(audience=audience))
    elif audience.segment == BroadcastAudienceSegment.INACTIVE_ACCOUNTS:
        query = query.where(_build_inactive_last_seen_predicate(audience=audience, now=now))
    elif audience.segment == BroadcastAudienceSegment.INACTIVE_PAID_USERS:
        query = query.where(
            _build_inactive_last_seen_predicate(audience=audience, now=now),
            exists(
                select(Payment.id).where(
                    Payment.account_id == Account.id,
                    Payment.flow_type == PaymentFlowType.DIRECT_PLAN_PURCHASE,
                    Payment.status == PaymentStatus.SUCCEEDED,
                )
            ),
        )
    elif audience.segment == BroadcastAudienceSegment.EXPIRED:
        query = query.where(
            Account.subscription_expires_at.is_not(None),
            Account.subscription_expires_at <= now,
        )
        if audience.subscription_expired_from_days is not None:
            query = query.where(
                Account.subscription_expires_at <= now - timedelta(days=audience.subscription_expired_from_days)
            )
        if audience.subscription_expired_to_days is not None:
            query = query.where(
                Account.subscription_expires_at >= now - timedelta(days=audience.subscription_expired_to_days)
            )
    elif audience.segment == BroadcastAudienceSegment.ABANDONED_CHECKOUT:
        latest_pending_payment = aliased(Payment)
        query = query.where(
            exists(
                select(latest_pending_payment.id).where(
                    latest_pending_payment.id == _latest_direct_plan_payment_id_subquery(),
                    latest_pending_payment.status.in_(DIRECT_PLAN_PENDING_STATUSES),
                    latest_pending_payment.created_at
                    <= now - timedelta(minutes=audience.pending_payment_older_than_minutes or 0),
                    latest_pending_payment.created_at
                    >= now - timedelta(days=audience.pending_payment_within_last_days or 0),
                )
            )
        )
    elif audience.segment == BroadcastAudienceSegment.FAILED_PAYMENT:
        latest_failed_payment = aliased(Payment)
        query = query.where(
            exists(
                select(latest_failed_payment.id).where(
                    latest_failed_payment.id == _latest_direct_plan_payment_id_subquery(),
                    latest_failed_payment.status.in_(DIRECT_PLAN_FAILED_STATUSES),
                    latest_failed_payment.created_at
                    >= now - timedelta(days=audience.failed_payment_within_last_days or 0),
                )
            )
        )
    elif audience.segment == BroadcastAudienceSegment.TRIAL_ENDED_NO_CONVERSION:
        query = query.where(
            Account.trial_used_at.is_not(None),
            Account.trial_ends_at.is_not(None),
            Account.trial_ends_at <= now,
            or_(
                Account.subscription_expires_at.is_(None),
                Account.subscription_expires_at <= now,
            ),
            ~exists(
                select(Payment.id).where(
                    Payment.account_id == Account.id,
                    Payment.flow_type == PaymentFlowType.DIRECT_PLAN_PURCHASE,
                    Payment.status == PaymentStatus.SUCCEEDED,
                )
            ),
        )
    elif audience.segment == BroadcastAudienceSegment.PAID_BEFORE_NOT_ACTIVE_NOW:
        query = query.where(
            exists(
                select(Payment.id).where(
                    Payment.account_id == Account.id,
                    Payment.flow_type == PaymentFlowType.DIRECT_PLAN_PURCHASE,
                    Payment.status == PaymentStatus.SUCCEEDED,
                )
            ),
            or_(
                Account.subscription_expires_at.is_(None),
                Account.subscription_expires_at <= now,
            ),
        )

    if audience.cooldown_days is not None and audience.cooldown_key is not None:
        cooldown_cutoff = now - timedelta(days=audience.cooldown_days)
        query = query.where(
            ~exists(
                select(BroadcastDelivery.id)
                .join(Broadcast, Broadcast.id == BroadcastDelivery.broadcast_id)
                .where(
                    BroadcastDelivery.account_id == Account.id,
                    BroadcastDelivery.status == BroadcastDeliveryStatus.DELIVERED,
                    BroadcastDelivery.delivered_at.is_not(None),
                    BroadcastDelivery.delivered_at >= cooldown_cutoff,
                    Broadcast.audience["cooldown_key"].as_string() == audience.cooldown_key,
                )
            )
        )

    return query


async def estimate_broadcast_audience(
    session: AsyncSession,
    *,
    audience: BroadcastAudienceConfig | dict[str, object],
    channels: tuple[BroadcastChannel, ...] | list[BroadcastChannel],
) -> BroadcastAudienceEstimate:
    audience_config = (
        audience if isinstance(audience, BroadcastAudienceConfig) else normalize_broadcast_audience_config(audience=audience)
    )
    channel_values = normalize_broadcast_channels(channels)
    base_query = _build_base_audience_query(
        audience=audience_config,
    ).subquery()

    total_accounts = int(
        await session.scalar(select(func.count()).select_from(base_query)) or 0
    )
    telegram_recipients = 0
    if BroadcastChannel.TELEGRAM.value in channel_values:
        telegram_recipients = int(
            await session.scalar(
                select(func.count())
                .select_from(base_query)
                .join(Account, Account.id == base_query.c.id)
                .where(
                    Account.telegram_id.is_not(None),
                    Account.telegram_bot_blocked_at.is_(None),
                )
            )
            or 0
        )

    in_app_recipients = total_accounts if BroadcastChannel.IN_APP.value in channel_values else 0
    return BroadcastAudienceEstimate(
        total_accounts=total_accounts,
        in_app_recipients=in_app_recipients,
        telegram_recipients=telegram_recipients,
    )


async def _resolve_audience_accounts(
    session: AsyncSession,
    *,
    audience: BroadcastAudienceConfig,
    limit: int | None = None,
) -> list[Account]:
    base_query = _build_base_audience_query(
        audience=audience,
    ).subquery()
    query = (
        select(Account)
        .join(base_query, Account.id == base_query.c.id)
        .order_by(Account.created_at.asc(), Account.id.asc())
    )
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def preview_broadcast_audience(
    session: AsyncSession,
    *,
    audience: BroadcastAudienceConfig | dict[str, object],
    channels: tuple[BroadcastChannel, ...] | list[BroadcastChannel],
    limit: int,
) -> BroadcastAudiencePreview:
    audience_config = (
        audience if isinstance(audience, BroadcastAudienceConfig) else normalize_broadcast_audience_config(audience=audience)
    )
    normalized_channels = normalize_broadcast_channels(channels)
    base_query = _build_base_audience_query(
        audience=audience_config,
    ).subquery()
    total_accounts = int(
        await session.scalar(select(func.count()).select_from(base_query)) or 0
    )
    manual_list_diagnostics = await _build_manual_list_preview_diagnostics(
        session,
        audience=audience_config,
        final_accounts=total_accounts,
    )
    accounts = await _resolve_audience_accounts(
        session,
        audience=audience_config,
        limit=limit,
    )
    latest_payments_by_account, latest_succeeded_payments_by_account = await _load_direct_plan_preview_payments(
        session,
        account_ids=[account.id for account in accounts],
    )
    auth_emails_by_account = await _load_auth_emails_for_accounts(
        session,
        account_ids=[account.id for account in accounts],
    )
    now = datetime.now(UTC)

    items: list[BroadcastAudiencePreviewItem] = []
    for account in accounts:
        delivery_channels, delivery_notes = _build_broadcast_audience_delivery_preview(
            account=account,
            channels=normalized_channels,
            audience=audience_config,
        )
        items.append(
            BroadcastAudiencePreviewItem(
                account=account,
                match_reasons=_build_broadcast_audience_match_reasons(
                    account=account,
                    audience=audience_config,
                    latest_direct_plan_payment=latest_payments_by_account.get(account.id),
                    latest_succeeded_direct_plan_payment=latest_succeeded_payments_by_account.get(account.id),
                    auth_emails=auth_emails_by_account.get(account.id),
                    now=now,
                ),
                delivery_channels=delivery_channels,
                delivery_notes=delivery_notes,
            )
        )

    return BroadcastAudiencePreview(
        total_accounts=total_accounts,
        limit=limit,
        has_more=total_accounts > len(items),
        items=items,
        manual_list_diagnostics=manual_list_diagnostics,
    )


async def _get_latest_broadcast_run(
    session: AsyncSession,
    *,
    broadcast_id: int,
) -> BroadcastRun | None:
    result = await session.execute(
        select(BroadcastRun)
        .where(BroadcastRun.broadcast_id == broadcast_id)
        .order_by(BroadcastRun.created_at.desc(), BroadcastRun.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_broadcast_run_counters(
    session: AsyncSession,
    *,
    run_id: int,
) -> BroadcastRunCounters:
    counters = BroadcastRunCounters()
    result = await session.execute(
        select(
            BroadcastDelivery.status,
            BroadcastDelivery.channel,
            func.count(),
        )
        .where(BroadcastDelivery.run_id == run_id)
        .group_by(BroadcastDelivery.status, BroadcastDelivery.channel)
    )
    for status_value, channel_value, count_value in result.all():
        count = int(count_value or 0)
        counters.total_deliveries += count

        if status_value == BroadcastDeliveryStatus.PENDING:
            counters.pending_deliveries += count
            if channel_value == BroadcastChannel.IN_APP:
                counters.in_app_pending += count
            elif channel_value == BroadcastChannel.TELEGRAM:
                counters.telegram_pending += count
        elif status_value == BroadcastDeliveryStatus.DELIVERED:
            counters.delivered_deliveries += count
            if channel_value == BroadcastChannel.IN_APP:
                counters.in_app_delivered += count
            elif channel_value == BroadcastChannel.TELEGRAM:
                counters.telegram_delivered += count
        elif status_value == BroadcastDeliveryStatus.FAILED:
            counters.failed_deliveries += count
        elif status_value == BroadcastDeliveryStatus.SKIPPED:
            counters.skipped_deliveries += count

    return counters


async def list_broadcasts(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: BroadcastStatus | None = None,
) -> tuple[list[Broadcast], int]:
    filters = []
    if status is not None:
        filters.append(Broadcast.status == status)

    total = int(
        await session.scalar(select(func.count()).select_from(Broadcast).where(*filters)) or 0
    )
    result = await session.execute(
        select(Broadcast)
        .where(*filters)
        .order_by(Broadcast.updated_at.desc(), Broadcast.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


async def list_broadcast_audience_presets(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> tuple[list[BroadcastAudiencePreset], int]:
    total = int(
        await session.scalar(select(func.count()).select_from(BroadcastAudiencePreset)) or 0
    )
    result = await session.execute(
        select(BroadcastAudiencePreset)
        .order_by(BroadcastAudiencePreset.updated_at.desc(), BroadcastAudiencePreset.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


async def get_broadcast_audience_preset(
    session: AsyncSession,
    *,
    preset_id: int,
) -> BroadcastAudiencePreset | None:
    return await session.get(BroadcastAudiencePreset, preset_id)


async def create_broadcast_audience_preset(
    session: AsyncSession,
    *,
    admin_id: uuid.UUID,
    name: str,
    description: str | None,
    audience: dict[str, object] | None,
) -> BroadcastAudiencePreset:
    normalized_name = _normalize_broadcast_audience_preset_name(name)
    normalized_description = _normalize_broadcast_audience_preset_description(description)
    audience_config = normalize_broadcast_audience_config(audience=audience)

    preset = BroadcastAudiencePreset(
        name=normalized_name,
        description=normalized_description,
        audience=build_broadcast_audience_payload(audience=audience_config),
        created_by_admin_id=admin_id,
        updated_by_admin_id=admin_id,
    )
    session.add(preset)
    await session.flush()

    session.add(
        AdminActionLog(
            admin_id=admin_id,
            action_type=AdminActionType.BROADCAST_AUDIENCE_PRESET_UPSERT,
            payload={
                "preset_id": preset.id,
                "operation": "create",
                "audience": preset.audience,
            },
        )
    )
    await session.flush()
    return preset


async def update_broadcast_audience_preset(
    session: AsyncSession,
    *,
    preset_id: int,
    admin_id: uuid.UUID,
    name: str,
    description: str | None,
    audience: dict[str, object] | None,
) -> BroadcastAudiencePreset:
    preset = await session.get(BroadcastAudiencePreset, preset_id)
    if preset is None:
        raise BroadcastAudiencePresetNotFoundError(f"broadcast audience preset not found: {preset_id}")

    normalized_name = _normalize_broadcast_audience_preset_name(name)
    normalized_description = _normalize_broadcast_audience_preset_description(description)
    audience_config = normalize_broadcast_audience_config(audience=audience)

    preset.name = normalized_name
    preset.description = normalized_description
    preset.audience = build_broadcast_audience_payload(audience=audience_config)
    preset.updated_by_admin_id = admin_id
    await session.flush()

    session.add(
        AdminActionLog(
            admin_id=admin_id,
            action_type=AdminActionType.BROADCAST_AUDIENCE_PRESET_UPSERT,
            payload={
                "preset_id": preset.id,
                "operation": "update",
                "audience": preset.audience,
            },
        )
    )
    await session.flush()
    return preset


async def delete_broadcast_audience_preset(
    session: AsyncSession,
    *,
    preset_id: int,
    admin_id: uuid.UUID,
) -> None:
    preset = await session.get(BroadcastAudiencePreset, preset_id)
    if preset is None:
        raise BroadcastAudiencePresetNotFoundError(f"broadcast audience preset not found: {preset_id}")

    session.add(
        AdminActionLog(
            admin_id=admin_id,
            action_type=AdminActionType.BROADCAST_AUDIENCE_PRESET_DELETE,
            payload={
                "preset_id": preset.id,
                "name": preset.name,
            },
        )
    )
    await session.flush()
    await session.delete(preset)


async def get_broadcast(
    session: AsyncSession,
    *,
    broadcast_id: int,
) -> Broadcast | None:
    return await session.get(Broadcast, broadcast_id)


async def create_broadcast_draft(
    session: AsyncSession,
    *,
    admin_id: uuid.UUID,
    name: str,
    title: str,
    body_html: str,
    content_type: BroadcastContentType,
    image_url: str | None,
    channels: tuple[BroadcastChannel, ...] | list[BroadcastChannel],
    buttons: list[dict[str, str]],
    audience: dict[str, object] | None,
) -> Broadcast:
    normalized_name = _normalize_required_text(name, field_name="name")
    normalized_title = _normalize_required_text(title, field_name="title")
    normalized_body_html = validate_telegram_html_subset(body_html)
    normalized_channels = normalize_broadcast_channels(channels)
    normalized_buttons = normalize_broadcast_buttons(buttons)
    normalized_image_url = _normalize_optional_text(image_url)
    audience_config = normalize_broadcast_audience_config(audience=audience)

    if content_type == BroadcastContentType.PHOTO and normalized_image_url is None:
        raise BroadcastValidationError("image_url is required for photo broadcast")
    if content_type == BroadcastContentType.TEXT:
        normalized_image_url = None

    estimate = await estimate_broadcast_audience(
        session,
        audience=audience_config,
        channels=channels,
    )

    broadcast = Broadcast(
        name=normalized_name,
        title=normalized_title,
        body_html=normalized_body_html,
        content_type=content_type,
        image_url=normalized_image_url,
        channels=normalized_channels,
        buttons=normalized_buttons,
        audience=build_broadcast_audience_payload(audience=audience_config),
        status=BroadcastStatus.DRAFT,
        estimated_total_accounts=estimate.total_accounts,
        estimated_in_app_recipients=estimate.in_app_recipients,
        estimated_telegram_recipients=estimate.telegram_recipients,
        created_by_admin_id=admin_id,
        updated_by_admin_id=admin_id,
    )
    validate_broadcast_runtime_constraints(broadcast)
    session.add(broadcast)
    await session.flush()

    session.add(
        AdminActionLog(
            admin_id=admin_id,
            action_type=AdminActionType.BROADCAST_DRAFT_UPSERT,
            payload={
                "broadcast_id": broadcast.id,
                "operation": "create",
                "status": broadcast.status.value,
                "channels": normalized_channels,
                "audience": broadcast.audience,
            },
        )
    )
    await session.flush()
    return broadcast


async def update_broadcast_draft(
    session: AsyncSession,
    *,
    broadcast_id: int,
    admin_id: uuid.UUID,
    name: str,
    title: str,
    body_html: str,
    content_type: BroadcastContentType,
    image_url: str | None,
    channels: tuple[BroadcastChannel, ...] | list[BroadcastChannel],
    buttons: list[dict[str, str]],
    audience: dict[str, object] | None,
) -> Broadcast:
    broadcast = await session.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFoundError(f"broadcast not found: {broadcast_id}")
    if broadcast.status != BroadcastStatus.DRAFT:
        raise BroadcastConflictError("only draft broadcasts can be edited")

    normalized_name = _normalize_required_text(name, field_name="name")
    normalized_title = _normalize_required_text(title, field_name="title")
    normalized_body_html = validate_telegram_html_subset(body_html)
    normalized_channels = normalize_broadcast_channels(channels)
    normalized_buttons = normalize_broadcast_buttons(buttons)
    normalized_image_url = _normalize_optional_text(image_url)
    audience_config = normalize_broadcast_audience_config(audience=audience)

    if content_type == BroadcastContentType.PHOTO and normalized_image_url is None:
        raise BroadcastValidationError("image_url is required for photo broadcast")
    if content_type == BroadcastContentType.TEXT:
        normalized_image_url = None

    estimate = await estimate_broadcast_audience(
        session,
        audience=audience_config,
        channels=channels,
    )

    broadcast.name = normalized_name
    broadcast.title = normalized_title
    broadcast.body_html = normalized_body_html
    broadcast.content_type = content_type
    broadcast.image_url = normalized_image_url
    broadcast.channels = normalized_channels
    broadcast.buttons = normalized_buttons
    broadcast.audience = build_broadcast_audience_payload(audience=audience_config)
    broadcast.estimated_total_accounts = estimate.total_accounts
    broadcast.estimated_in_app_recipients = estimate.in_app_recipients
    broadcast.estimated_telegram_recipients = estimate.telegram_recipients
    broadcast.updated_by_admin_id = admin_id
    validate_broadcast_runtime_constraints(broadcast)
    await session.flush()

    session.add(
        AdminActionLog(
            admin_id=admin_id,
            action_type=AdminActionType.BROADCAST_DRAFT_UPSERT,
            payload={
                "broadcast_id": broadcast.id,
                "operation": "update",
                "status": broadcast.status.value,
                "channels": normalized_channels,
                "audience": broadcast.audience,
            },
        )
    )
    await session.flush()
    return broadcast


async def delete_broadcast_draft(
    session: AsyncSession,
    *,
    broadcast_id: int,
    admin_id: uuid.UUID,
) -> None:
    broadcast = await session.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFoundError(f"broadcast not found: {broadcast_id}")
    if broadcast.status != BroadcastStatus.DRAFT:
        raise BroadcastConflictError("only draft broadcasts can be deleted")

    session.add(
        AdminActionLog(
            admin_id=admin_id,
            action_type=AdminActionType.BROADCAST_DRAFT_DELETE,
            payload={
                "broadcast_id": broadcast.id,
                "status": broadcast.status.value,
            },
        )
    )
    await session.flush()
    await session.delete(broadcast)


async def _get_active_runtime_run(
    session: AsyncSession,
    *,
    broadcast_id: int,
) -> BroadcastRun | None:
    result = await session.execute(
        select(BroadcastRun)
        .where(
            BroadcastRun.broadcast_id == broadcast_id,
            BroadcastRun.status.in_(
                [
                    BroadcastRunStatus.RUNNING,
                    BroadcastRunStatus.PAUSED,
                ]
            ),
        )
        .order_by(BroadcastRun.created_at.desc(), BroadcastRun.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _create_runtime_run(
    session: AsyncSession,
    *,
    broadcast: Broadcast,
    run_type: BroadcastRunType,
    triggered_by_admin_id: uuid.UUID,
    started_at: datetime,
) -> BroadcastRun:
    validate_broadcast_runtime_constraints(broadcast)
    if broadcast.status not in {BroadcastStatus.DRAFT, BroadcastStatus.SCHEDULED}:
        raise BroadcastConflictError("broadcast is not ready to launch")

    active_run = await _get_active_runtime_run(session, broadcast_id=broadcast.id)
    if active_run is not None:
        raise BroadcastConflictError("broadcast already has an active run")

    audience_config = _get_broadcast_audience_config(broadcast)
    accounts = await _resolve_audience_accounts(
        session,
        audience=audience_config,
    )
    channels = normalize_broadcast_channels(broadcast.channels)
    telegram_targets = [
        account
        for account in accounts
        if account.telegram_id is not None and account.telegram_bot_blocked_at is None
    ]

    run = BroadcastRun(
        broadcast_id=broadcast.id,
        run_type=run_type,
        status=BroadcastRunStatus.RUNNING,
        triggered_by_admin_id=triggered_by_admin_id,
        snapshot_total_accounts=len(accounts),
        snapshot_in_app_targets=(
            len(accounts) if BroadcastChannel.IN_APP.value in channels else 0
        ),
        snapshot_telegram_targets=(
            len(telegram_targets) if BroadcastChannel.TELEGRAM.value in channels else 0
        ),
        started_at=started_at.astimezone(UTC),
    )
    session.add(run)
    await session.flush()

    now_utc = datetime.now(UTC)
    for account in accounts:
        if BroadcastChannel.IN_APP.value in channels:
            session.add(
                BroadcastDelivery(
                    run_id=run.id,
                    broadcast_id=broadcast.id,
                    account_id=account.id,
                    channel=BroadcastChannel.IN_APP,
                    status=BroadcastDeliveryStatus.PENDING,
                    attempts_count=0,
                    next_retry_at=now_utc,
                )
            )

        if (
            BroadcastChannel.TELEGRAM.value in channels
            and account.telegram_id is not None
            and account.telegram_bot_blocked_at is None
        ):
            session.add(
                BroadcastDelivery(
                    run_id=run.id,
                    broadcast_id=broadcast.id,
                    account_id=account.id,
                    channel=BroadcastChannel.TELEGRAM,
                    status=BroadcastDeliveryStatus.PENDING,
                    attempts_count=0,
                    next_retry_at=now_utc,
                )
            )

    broadcast.status = BroadcastStatus.RUNNING
    broadcast.launched_at = started_at.astimezone(UTC)
    broadcast.completed_at = None
    broadcast.cancelled_at = None
    broadcast.last_error = None
    await session.flush()
    return run


async def launch_broadcast_now(
    session: AsyncSession,
    *,
    broadcast_id: int,
    admin_id: uuid.UUID,
    comment: str | None,
    idempotency_key: str,
) -> Broadcast:
    broadcast = await session.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFoundError(f"broadcast not found: {broadcast_id}")
    if broadcast.status != BroadcastStatus.DRAFT:
        raise BroadcastConflictError("only draft broadcasts can be launched now")

    normalized_idempotency_key = _normalize_required_text(
        idempotency_key,
        field_name="idempotency_key",
    )
    normalized_comment = _normalize_optional_text(comment)

    existing_log_result = await session.execute(
        select(AdminActionLog).where(
            AdminActionLog.action_type == AdminActionType.BROADCAST_SEND_NOW,
            AdminActionLog.idempotency_key == normalized_idempotency_key,
        )
    )
    existing_log = existing_log_result.scalar_one_or_none()
    if existing_log is not None:
        existing_broadcast = await session.get(Broadcast, broadcast_id)
        if existing_broadcast is None:
            raise BroadcastNotFoundError(f"broadcast not found: {broadcast_id}")
        return existing_broadcast

    run = await _create_runtime_run(
        session,
        broadcast=broadcast,
        run_type=BroadcastRunType.SEND_NOW,
        triggered_by_admin_id=admin_id,
        started_at=_now_moscow(),
    )
    await _sync_broadcast_run_state(session, run=run)
    broadcast.updated_by_admin_id = admin_id
    await session.flush()

    session.add(
        AdminActionLog(
            admin_id=admin_id,
            action_type=AdminActionType.BROADCAST_SEND_NOW,
            idempotency_key=normalized_idempotency_key,
            comment=normalized_comment,
            payload={"broadcast_id": broadcast.id, "status": broadcast.status.value},
        )
    )
    await session.flush()
    return broadcast


async def schedule_broadcast_launch(
    session: AsyncSession,
    *,
    broadcast_id: int,
    admin_id: uuid.UUID,
    scheduled_at: datetime,
    comment: str | None,
    idempotency_key: str,
) -> Broadcast:
    broadcast = await session.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFoundError(f"broadcast not found: {broadcast_id}")
    if broadcast.status != BroadcastStatus.DRAFT:
        raise BroadcastConflictError("only draft broadcasts can be scheduled")

    normalized_idempotency_key = _normalize_required_text(
        idempotency_key,
        field_name="idempotency_key",
    )
    normalized_comment = _normalize_optional_text(comment)
    normalized_scheduled_at = _normalize_scheduled_datetime(scheduled_at)
    if normalized_scheduled_at <= _now_moscow():
        raise BroadcastValidationError("scheduled_at must be in the future")

    validate_broadcast_runtime_constraints(broadcast)

    existing_log_result = await session.execute(
        select(AdminActionLog).where(
            AdminActionLog.action_type == AdminActionType.BROADCAST_SCHEDULE,
            AdminActionLog.idempotency_key == normalized_idempotency_key,
        )
    )
    existing_log = existing_log_result.scalar_one_or_none()
    if existing_log is not None:
        existing_broadcast = await session.get(Broadcast, broadcast_id)
        if existing_broadcast is None:
            raise BroadcastNotFoundError(f"broadcast not found: {broadcast_id}")
        return existing_broadcast

    broadcast.status = BroadcastStatus.SCHEDULED
    broadcast.scheduled_at = normalized_scheduled_at.astimezone(UTC)
    broadcast.updated_by_admin_id = admin_id
    broadcast.last_error = None
    await session.flush()

    session.add(
        AdminActionLog(
            admin_id=admin_id,
            action_type=AdminActionType.BROADCAST_SCHEDULE,
            idempotency_key=normalized_idempotency_key,
            comment=normalized_comment,
            payload={
                "broadcast_id": broadcast.id,
                "status": broadcast.status.value,
                "scheduled_at": broadcast.scheduled_at.isoformat()
                if broadcast.scheduled_at
                else None,
            },
        )
    )
    await session.flush()
    return broadcast


async def pause_broadcast(
    session: AsyncSession,
    *,
    broadcast_id: int,
    admin_id: uuid.UUID,
    comment: str | None,
    idempotency_key: str,
) -> Broadcast:
    broadcast = await session.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFoundError(f"broadcast not found: {broadcast_id}")
    if broadcast.status not in {BroadcastStatus.SCHEDULED, BroadcastStatus.RUNNING}:
        raise BroadcastConflictError("only scheduled or running broadcasts can be paused")

    normalized_idempotency_key = _normalize_required_text(
        idempotency_key,
        field_name="idempotency_key",
    )
    normalized_comment = _normalize_optional_text(comment)

    existing_log_result = await session.execute(
        select(AdminActionLog).where(
            AdminActionLog.action_type == AdminActionType.BROADCAST_PAUSE,
            AdminActionLog.idempotency_key == normalized_idempotency_key,
        )
    )
    existing_log = existing_log_result.scalar_one_or_none()
    if existing_log is not None:
        existing_broadcast = await session.get(Broadcast, broadcast_id)
        if existing_broadcast is None:
            raise BroadcastNotFoundError(f"broadcast not found: {broadcast_id}")
        return existing_broadcast

    run = await _get_active_runtime_run(session, broadcast_id=broadcast.id)
    if run is not None:
        run.status = BroadcastRunStatus.PAUSED
    broadcast.status = BroadcastStatus.PAUSED
    broadcast.updated_by_admin_id = admin_id
    await session.flush()

    session.add(
        AdminActionLog(
            admin_id=admin_id,
            action_type=AdminActionType.BROADCAST_PAUSE,
            idempotency_key=normalized_idempotency_key,
            comment=normalized_comment,
            payload={"broadcast_id": broadcast.id, "status": broadcast.status.value},
        )
    )
    await session.flush()
    return broadcast


async def resume_broadcast(
    session: AsyncSession,
    *,
    broadcast_id: int,
    admin_id: uuid.UUID,
    comment: str | None,
    idempotency_key: str,
) -> Broadcast:
    broadcast = await session.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFoundError(f"broadcast not found: {broadcast_id}")
    if broadcast.status != BroadcastStatus.PAUSED:
        raise BroadcastConflictError("only paused broadcasts can be resumed")

    normalized_idempotency_key = _normalize_required_text(
        idempotency_key,
        field_name="idempotency_key",
    )
    normalized_comment = _normalize_optional_text(comment)

    existing_log_result = await session.execute(
        select(AdminActionLog).where(
            AdminActionLog.action_type == AdminActionType.BROADCAST_RESUME,
            AdminActionLog.idempotency_key == normalized_idempotency_key,
        )
    )
    existing_log = existing_log_result.scalar_one_or_none()
    if existing_log is not None:
        existing_broadcast = await session.get(Broadcast, broadcast_id)
        if existing_broadcast is None:
            raise BroadcastNotFoundError(f"broadcast not found: {broadcast_id}")
        return existing_broadcast

    run = await _get_active_runtime_run(session, broadcast_id=broadcast.id)
    if run is not None:
        run.status = BroadcastRunStatus.RUNNING
        broadcast.status = BroadcastStatus.RUNNING
    elif broadcast.scheduled_at is not None:
        broadcast.status = BroadcastStatus.SCHEDULED
    else:
        raise BroadcastConflictError("paused broadcast cannot be resumed without an active run")
    broadcast.updated_by_admin_id = admin_id
    await session.flush()

    session.add(
        AdminActionLog(
            admin_id=admin_id,
            action_type=AdminActionType.BROADCAST_RESUME,
            idempotency_key=normalized_idempotency_key,
            comment=normalized_comment,
            payload={"broadcast_id": broadcast.id, "status": broadcast.status.value},
        )
    )
    await session.flush()
    return broadcast


async def cancel_broadcast(
    session: AsyncSession,
    *,
    broadcast_id: int,
    admin_id: uuid.UUID,
    comment: str | None,
    idempotency_key: str,
) -> Broadcast:
    broadcast = await session.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFoundError(f"broadcast not found: {broadcast_id}")
    if broadcast.status not in {
        BroadcastStatus.SCHEDULED,
        BroadcastStatus.RUNNING,
        BroadcastStatus.PAUSED,
    }:
        raise BroadcastConflictError("only scheduled, running or paused broadcasts can be cancelled")

    normalized_idempotency_key = _normalize_required_text(
        idempotency_key,
        field_name="idempotency_key",
    )
    normalized_comment = _normalize_optional_text(comment)

    existing_log_result = await session.execute(
        select(AdminActionLog).where(
            AdminActionLog.action_type == AdminActionType.BROADCAST_CANCEL,
            AdminActionLog.idempotency_key == normalized_idempotency_key,
        )
    )
    existing_log = existing_log_result.scalar_one_or_none()
    if existing_log is not None:
        existing_broadcast = await session.get(Broadcast, broadcast_id)
        if existing_broadcast is None:
            raise BroadcastNotFoundError(f"broadcast not found: {broadcast_id}")
        return existing_broadcast

    now_utc = datetime.now(UTC)
    run = await _get_active_runtime_run(session, broadcast_id=broadcast.id)
    if run is not None:
        run.status = BroadcastRunStatus.CANCELLED
        run.cancelled_at = now_utc
        await session.execute(
            update(BroadcastDelivery)
            .where(
                BroadcastDelivery.run_id == run.id,
                BroadcastDelivery.status == BroadcastDeliveryStatus.PENDING,
            )
            .values(
                status=BroadcastDeliveryStatus.SKIPPED,
                error_code="cancelled",
                error_message="broadcast cancelled by admin",
                next_retry_at=None,
            )
        )

    broadcast.status = BroadcastStatus.CANCELLED
    broadcast.cancelled_at = now_utc
    broadcast.completed_at = None
    broadcast.updated_by_admin_id = admin_id
    await session.flush()

    session.add(
        AdminActionLog(
            admin_id=admin_id,
            action_type=AdminActionType.BROADCAST_CANCEL,
            idempotency_key=normalized_idempotency_key,
            comment=normalized_comment,
            payload={"broadcast_id": broadcast.id, "status": broadcast.status.value},
        )
    )
    await session.flush()
    return broadcast


def _calculate_broadcast_retry_delay_seconds(
    *,
    attempts_count: int,
    retry_after_seconds: int | None = None,
) -> int:
    if retry_after_seconds is not None and retry_after_seconds > 0:
        return retry_after_seconds

    base_seconds = max(5, int(settings.broadcast_telegram_retry_base_seconds))
    max_seconds = max(base_seconds, int(settings.broadcast_telegram_retry_max_seconds))
    exponent = max(0, attempts_count - 1)
    return min(max_seconds, base_seconds * (2**exponent))


async def _sync_broadcast_run_state(
    session: AsyncSession,
    *,
    run: BroadcastRun,
) -> BroadcastRunCounters:
    counters = await get_broadcast_run_counters(session, run_id=run.id)
    broadcast = await session.get(Broadcast, run.broadcast_id)
    if broadcast is None:
        return counters

    now_utc = datetime.now(UTC)
    if run.status == BroadcastRunStatus.CANCELLED:
        broadcast.status = BroadcastStatus.CANCELLED
        broadcast.cancelled_at = run.cancelled_at or now_utc
        return counters

    if run.status == BroadcastRunStatus.PAUSED:
        broadcast.status = BroadcastStatus.PAUSED
        return counters

    if counters.pending_deliveries > 0:
        run.status = BroadcastRunStatus.RUNNING
        broadcast.status = BroadcastStatus.RUNNING
        return counters

    run.completed_at = run.completed_at or now_utc
    broadcast.completed_at = now_utc
    if counters.total_deliveries == 0:
        run.status = BroadcastRunStatus.COMPLETED
        broadcast.status = BroadcastStatus.COMPLETED
        return counters

    if counters.delivered_deliveries > 0 or counters.skipped_deliveries > 0:
        run.status = BroadcastRunStatus.COMPLETED
        broadcast.status = BroadcastStatus.COMPLETED
    else:
        run.status = BroadcastRunStatus.FAILED
        broadcast.status = BroadcastStatus.FAILED
        if not broadcast.last_error:
            broadcast.last_error = run.last_error or "all broadcast deliveries failed"
    return counters


async def start_due_scheduled_broadcasts(
    session: AsyncSession,
    *,
    limit: int,
) -> BroadcastSchedulerResult:
    result = BroadcastSchedulerResult()
    now_moscow = _now_moscow()
    due_broadcasts_result = await session.execute(
        select(Broadcast)
        .where(
            Broadcast.status == BroadcastStatus.SCHEDULED,
            Broadcast.scheduled_at.is_not(None),
            Broadcast.scheduled_at <= now_moscow.astimezone(UTC),
        )
        .order_by(Broadcast.scheduled_at.asc(), Broadcast.id.asc())
        .limit(limit)
    )
    for broadcast in due_broadcasts_result.scalars().all():
        run = await _create_runtime_run(
            session,
            broadcast=broadcast,
            run_type=BroadcastRunType.SCHEDULED,
            triggered_by_admin_id=broadcast.updated_by_admin_id,
            started_at=now_moscow,
        )
        await _sync_broadcast_run_state(session, run=run)
        result.started_runs += 1

    return result


async def _mark_broadcast_delivery_delivered(
    *,
    delivery: BroadcastDelivery,
    provider_message_id: str | None,
    notification_id: int | None = None,
) -> None:
    now_utc = datetime.now(UTC)
    delivery.status = BroadcastDeliveryStatus.DELIVERED
    delivery.provider_message_id = provider_message_id
    delivery.notification_id = notification_id
    delivery.attempts_count += 1
    delivery.last_attempt_at = now_utc
    delivery.next_retry_at = None
    delivery.delivered_at = now_utc
    delivery.error_code = None
    delivery.error_message = None


async def _mark_broadcast_delivery_failed(
    *,
    delivery: BroadcastDelivery,
    code: str,
    message: str,
    retryable: bool,
    retry_after_seconds: int | None,
) -> bool:
    now_utc = datetime.now(UTC)
    delivery.attempts_count += 1
    delivery.last_attempt_at = now_utc
    delivery.error_code = code
    delivery.error_message = message
    max_attempts = max(1, int(settings.broadcast_telegram_max_attempts))
    if retryable and delivery.attempts_count < max_attempts:
        delivery.status = BroadcastDeliveryStatus.PENDING
        delivery.next_retry_at = now_utc + timedelta(
            seconds=_calculate_broadcast_retry_delay_seconds(
                attempts_count=delivery.attempts_count,
                retry_after_seconds=retry_after_seconds,
            )
        )
        return True

    delivery.status = BroadcastDeliveryStatus.FAILED
    delivery.next_retry_at = None
    return False


def _defer_broadcast_delivery_for_quiet_hours(
    *,
    delivery: BroadcastDelivery,
    quiet_until: datetime,
) -> None:
    delivery.status = BroadcastDeliveryStatus.PENDING
    delivery.next_retry_at = quiet_until
    delivery.error_code = "quiet_hours"
    delivery.error_message = (
        f"telegram delivery deferred until {quiet_until.astimezone(BROADCAST_TZ).strftime('%Y-%m-%d %H:%M %Z')}"
    )


async def process_pending_broadcast_deliveries(
    session: AsyncSession,
    *,
    limit: int,
) -> BroadcastDeliveryProcessResult:
    result = BroadcastDeliveryProcessResult()
    now_utc = datetime.now(UTC)
    deliveries_result = await session.execute(
        select(BroadcastDelivery, BroadcastRun, Broadcast, Account)
        .join(BroadcastRun, BroadcastRun.id == BroadcastDelivery.run_id)
        .join(Broadcast, Broadcast.id == BroadcastDelivery.broadcast_id)
        .join(Account, Account.id == BroadcastDelivery.account_id)
        .where(
            Broadcast.status == BroadcastStatus.RUNNING,
            BroadcastRun.status == BroadcastRunStatus.RUNNING,
            BroadcastDelivery.status == BroadcastDeliveryStatus.PENDING,
            or_(
                BroadcastDelivery.next_retry_at.is_(None),
                BroadcastDelivery.next_retry_at <= now_utc,
            ),
        )
        .order_by(
            BroadcastDelivery.next_retry_at.asc().nullsfirst(),
            BroadcastDelivery.id.asc(),
        )
        .limit(limit)
    )

    runs_to_sync: dict[int, BroadcastRun] = {}
    audience_config_by_broadcast_id: dict[int, BroadcastAudienceConfig] = {}
    for delivery, run, broadcast, account in deliveries_result.all():
        result.processed += 1
        runs_to_sync[run.id] = run

        if delivery.channel == BroadcastChannel.IN_APP:
            try:
                notification = await create_notification(
                    session,
                    account_id=account.id,
                    type=NotificationType.BROADCAST,
                    title=broadcast.title,
                    body=build_broadcast_in_app_body(broadcast.body_html),
                    priority=NotificationPriority.INFO,
                    payload=build_broadcast_notification_payload(broadcast),
                    action_label=(broadcast.buttons[0]["text"] if broadcast.buttons else None),
                    action_url=(broadcast.buttons[0]["url"] if broadcast.buttons else None),
                    dedupe_key=f"broadcast:{broadcast.id}:run:{run.id}:account:{account.id}:in_app",
                    channels=(NotificationChannel.IN_APP,),
                    deliver_to_telegram=False,
                )
                if notification is None:
                    delivery.status = BroadcastDeliveryStatus.SKIPPED
                    delivery.error_code = "missing_account"
                    delivery.error_message = "account missing while creating in-app notification"
                    delivery.next_retry_at = None
                    result.skipped += 1
                else:
                    await _mark_broadcast_delivery_delivered(
                        delivery=delivery,
                        provider_message_id=str(notification.id),
                        notification_id=notification.id,
                    )
                    result.delivered += 1
            except Exception as exc:
                retry_scheduled = await _mark_broadcast_delivery_failed(
                    delivery=delivery,
                    code="in_app_error",
                    message=str(exc),
                    retryable=False,
                    retry_after_seconds=None,
                )
                if retry_scheduled:
                    result.scheduled_retry += 1
                else:
                    result.terminal_failed += 1
                run.last_error = str(exc)
            continue

        if account.telegram_id is None:
            delivery.status = BroadcastDeliveryStatus.SKIPPED
            delivery.error_code = "missing_telegram_id"
            delivery.error_message = "account does not have telegram_id"
            delivery.next_retry_at = None
            result.skipped += 1
            continue

        if account.telegram_bot_blocked_at is not None:
            delivery.status = BroadcastDeliveryStatus.SKIPPED
            delivery.error_code = "telegram_bot_blocked"
            delivery.error_message = "account previously blocked the Telegram bot"
            delivery.next_retry_at = None
            result.skipped += 1
            continue

        audience_config = audience_config_by_broadcast_id.get(broadcast.id)
        if audience_config is None:
            audience_config = _get_broadcast_audience_config(broadcast)
            audience_config_by_broadcast_id[broadcast.id] = audience_config
        quiet_until = _resolve_telegram_quiet_hours_release_at(
            audience=audience_config,
            now_moscow=_now_moscow(),
        )
        if quiet_until is not None:
            _defer_broadcast_delivery_for_quiet_hours(
                delivery=delivery,
                quiet_until=quiet_until,
            )
            result.scheduled_retry += 1
            continue

        try:
            provider_message_ids = await _send_broadcast_to_telegram(
                telegram_id=int(account.telegram_id),
                broadcast=broadcast,
            )
            await _mark_broadcast_delivery_delivered(
                delivery=delivery,
                provider_message_id=provider_message_ids[-1] if provider_message_ids else None,
            )
            result.delivered += 1
        except BroadcastValidationError as exc:
            retry_scheduled = await _mark_broadcast_delivery_failed(
                delivery=delivery,
                code="validation_error",
                message=str(exc),
                retryable=False,
                retry_after_seconds=None,
            )
            if retry_scheduled:
                result.scheduled_retry += 1
            else:
                result.terminal_failed += 1
            run.last_error = str(exc)
        except TelegramNotificationConfigurationError as exc:
            retry_scheduled = await _mark_broadcast_delivery_failed(
                delivery=delivery,
                code="telegram_not_configured",
                message=str(exc),
                retryable=False,
                retry_after_seconds=None,
            )
            if retry_scheduled:
                result.scheduled_retry += 1
            else:
                result.terminal_failed += 1
            run.last_error = str(exc)
        except TelegramNotificationDeliveryError as exc:
            if exc.mark_telegram_bot_blocked:
                await mark_telegram_bot_blocked(
                    session,
                    account=account,
                    blocked_at=now_utc,
                )
            retry_scheduled = await _mark_broadcast_delivery_failed(
                delivery=delivery,
                code=exc.code,
                message=str(exc),
                retryable=exc.retryable,
                retry_after_seconds=exc.retry_after_seconds,
            )
            if retry_scheduled:
                result.scheduled_retry += 1
            else:
                result.terminal_failed += 1
            run.last_error = str(exc)

    for run in runs_to_sync.values():
        await _sync_broadcast_run_state(session, run=run)

    await session.flush()
    return result


async def list_broadcast_runs(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    broadcast_id: int | None = None,
    status: BroadcastRunStatus | None = None,
    run_type: BroadcastRunType | None = None,
    channel: BroadcastChannel | None = None,
) -> tuple[list[BroadcastRunWithCounters], int]:
    filters = []
    if broadcast_id is not None:
        filters.append(BroadcastRun.broadcast_id == broadcast_id)
    if status is not None:
        filters.append(BroadcastRun.status == status)
    if run_type is not None:
        filters.append(BroadcastRun.run_type == run_type)
    if channel is not None:
        filters.append(
            exists(
                select(BroadcastDelivery.id).where(
                    BroadcastDelivery.run_id == BroadcastRun.id,
                    BroadcastDelivery.channel == channel,
                )
            )
        )

    total = int(
        await session.scalar(select(func.count()).select_from(BroadcastRun).where(*filters)) or 0
    )
    result = await session.execute(
        select(BroadcastRun)
        .where(*filters)
        .order_by(BroadcastRun.created_at.desc(), BroadcastRun.id.desc())
        .limit(limit)
        .offset(offset)
    )
    runs = list(result.scalars().all())
    items = [
        BroadcastRunWithCounters(
            run=run,
            counters=await get_broadcast_run_counters(session, run_id=run.id),
        )
        for run in runs
    ]
    return items, total


async def get_broadcast_run(
    session: AsyncSession,
    *,
    run_id: int,
) -> BroadcastRunWithCounters | None:
    run = await session.get(BroadcastRun, run_id)
    if run is None:
        return None
    return BroadcastRunWithCounters(
        run=run,
        counters=await get_broadcast_run_counters(session, run_id=run.id),
    )


async def get_latest_broadcast_run(
    session: AsyncSession,
    *,
    broadcast_id: int,
) -> BroadcastRunWithCounters | None:
    run = await _get_latest_broadcast_run(session, broadcast_id=broadcast_id)
    if run is None:
        return None
    return BroadcastRunWithCounters(
        run=run,
        counters=await get_broadcast_run_counters(session, run_id=run.id),
    )


async def list_broadcast_run_deliveries(
    session: AsyncSession,
    *,
    run_id: int,
    limit: int,
    offset: int,
    status: BroadcastDeliveryStatus | None = None,
    channel: BroadcastChannel | None = None,
) -> tuple[list[tuple[BroadcastDelivery, Account]], int]:
    filters = [BroadcastDelivery.run_id == run_id]
    if status is not None:
        filters.append(BroadcastDelivery.status == status)
    if channel is not None:
        filters.append(BroadcastDelivery.channel == channel)

    total = int(
        await session.scalar(
            select(func.count()).select_from(BroadcastDelivery).where(*filters)
        )
        or 0
    )
    result = await session.execute(
        select(BroadcastDelivery, Account)
        .join(Account, Account.id == BroadcastDelivery.account_id)
        .where(*filters)
        .order_by(BroadcastDelivery.created_at.asc(), BroadcastDelivery.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.all()), total


async def send_broadcast_test(
    session: AsyncSession,
    *,
    broadcast_id: int,
    admin_id: uuid.UUID,
    emails: list[str],
    telegram_ids: list[int],
    comment: str,
    idempotency_key: str,
) -> BroadcastTestSendResult:
    normalized_comment = _normalize_required_text(comment, field_name="comment")
    normalized_idempotency_key = _normalize_required_text(
        idempotency_key,
        field_name="idempotency_key",
    )
    normalized_emails = _normalize_test_target_emails(emails)
    normalized_telegram_ids = _normalize_test_target_telegram_ids(telegram_ids)
    if not normalized_emails and not normalized_telegram_ids:
        raise BroadcastValidationError("at least one email or telegram_id target is required")

    existing_log_result = await session.execute(
        select(AdminActionLog).where(
            AdminActionLog.action_type == AdminActionType.BROADCAST_TEST_SEND,
            AdminActionLog.idempotency_key == normalized_idempotency_key,
        )
    )
    existing_log = existing_log_result.scalar_one_or_none()
    if existing_log is not None:
        result_payload = (existing_log.payload or {}).get("result") if existing_log.payload else None
        if not isinstance(result_payload, dict):
            raise BroadcastConflictError("broadcast test send idempotency payload is invalid")
        return BroadcastTestSendResult(
            broadcast_id=int(result_payload["broadcast_id"]),
            audit_log_id=existing_log.id,
            total_targets=int(result_payload["total_targets"]),
            sent_targets=int(result_payload["sent_targets"]),
            partial_targets=int(result_payload["partial_targets"]),
            failed_targets=int(result_payload["failed_targets"]),
            skipped_targets=int(result_payload["skipped_targets"]),
            resolved_account_targets=int(result_payload["resolved_account_targets"]),
            direct_telegram_targets=int(result_payload["direct_telegram_targets"]),
            in_app_notifications_created=int(result_payload["in_app_notifications_created"]),
            telegram_targets_sent=int(result_payload["telegram_targets_sent"]),
            items=[
                BroadcastTestSendTargetResult(
                    target=str(item["target"]),
                    source=str(item["source"]),
                    resolution=str(item["resolution"]),
                    status=str(item["status"]),
                    account_id=uuid.UUID(item["account_id"]) if item.get("account_id") else None,
                    telegram_id=int(item["telegram_id"]) if item.get("telegram_id") is not None else None,
                    channels_attempted=[str(channel) for channel in item.get("channels_attempted", [])],
                    in_app_notification_id=(
                        int(item["in_app_notification_id"])
                        if item.get("in_app_notification_id") is not None
                        else None
                    ),
                    telegram_message_ids=[str(message_id) for message_id in item.get("telegram_message_ids", [])],
                    detail=str(item["detail"]) if item.get("detail") else None,
                )
                for item in result_payload.get("items", [])
            ],
        )

    broadcast = await session.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFoundError(f"broadcast not found: {broadcast_id}")
    validate_broadcast_runtime_constraints(broadcast)

    channels = normalize_broadcast_channels(broadcast.channels)
    resolved_email_accounts = await _resolve_accounts_by_emails(
        session,
        emails=normalized_emails,
    )
    resolved_telegram_accounts = await _resolve_accounts_by_telegram_ids(
        session,
        telegram_ids=normalized_telegram_ids,
    )

    items: list[BroadcastTestSendTargetResult] = []
    sent_targets = 0
    partial_targets = 0
    failed_targets = 0
    skipped_targets = 0
    in_app_notifications_created = 0
    telegram_targets_sent = 0
    resolved_account_targets = 0
    direct_telegram_targets = 0
    processed_account_ids: set[uuid.UUID] = set()

    for email in normalized_emails:
        account = resolved_email_accounts.get(email)
        if account is None:
            items.append(
                BroadcastTestSendTargetResult(
                    target=email,
                    source="email",
                    resolution="unresolved",
                    status="skipped",
                    detail="email does not resolve to a local account",
                )
            )
            skipped_targets += 1
            continue

        if account.id in processed_account_ids:
            items.append(
                BroadcastTestSendTargetResult(
                    target=email,
                    source="email",
                    resolution="account",
                    status="skipped",
                    account_id=account.id,
                    telegram_id=account.telegram_id,
                    detail="account already included by another target",
                )
            )
            skipped_targets += 1
            continue

        processed_account_ids.add(account.id)
        resolved_account_targets += 1
        result_item = await _send_broadcast_test_to_account(
            session,
            broadcast=broadcast,
            account=account,
            source="email",
            target=email,
            channels=channels,
        )
        items.append(result_item)

        if result_item.in_app_notification_id is not None:
            in_app_notifications_created += 1
        if result_item.telegram_message_ids:
            telegram_targets_sent += 1

        if result_item.status == "sent":
            sent_targets += 1
        elif result_item.status == "partial":
            partial_targets += 1
        elif result_item.status == "failed":
            failed_targets += 1
        else:
            skipped_targets += 1

    for telegram_id in normalized_telegram_ids:
        account = resolved_telegram_accounts.get(telegram_id)
        if account is not None:
            if account.id in processed_account_ids:
                items.append(
                    BroadcastTestSendTargetResult(
                        target=str(telegram_id),
                        source="telegram_id",
                        resolution="account",
                        status="skipped",
                        account_id=account.id,
                        telegram_id=telegram_id,
                        detail="account already included by another target",
                    )
                )
                skipped_targets += 1
                continue

            processed_account_ids.add(account.id)
            resolved_account_targets += 1
            result_item = await _send_broadcast_test_to_account(
                session,
                broadcast=broadcast,
                account=account,
                source="telegram_id",
                target=str(telegram_id),
                channels=channels,
            )
            items.append(result_item)
            if result_item.in_app_notification_id is not None:
                in_app_notifications_created += 1
            if result_item.telegram_message_ids:
                telegram_targets_sent += 1

            if result_item.status == "sent":
                sent_targets += 1
            elif result_item.status == "partial":
                partial_targets += 1
            elif result_item.status == "failed":
                failed_targets += 1
            else:
                skipped_targets += 1
            continue

        direct_telegram_targets += 1
        direct_result = await _send_broadcast_test_to_direct_telegram(
            broadcast=broadcast,
            telegram_id=telegram_id,
            channels=channels,
        )
        items.append(direct_result)
        if direct_result.telegram_message_ids:
            telegram_targets_sent += 1
        if direct_result.status == "sent":
            sent_targets += 1
        elif direct_result.status == "partial":
            partial_targets += 1
        elif direct_result.status == "failed":
            failed_targets += 1
        else:
            skipped_targets += 1

    audit_log = AdminActionLog(
        admin_id=admin_id,
        action_type=AdminActionType.BROADCAST_TEST_SEND,
        idempotency_key=normalized_idempotency_key,
        comment=normalized_comment,
        payload={
            "broadcast_id": broadcast.id,
            "requested": {
                "emails": normalized_emails,
                "telegram_ids": normalized_telegram_ids,
                "channels": channels,
            },
            "result": {
                "broadcast_id": broadcast.id,
                "total_targets": len(items),
                "sent_targets": sent_targets,
                "partial_targets": partial_targets,
                "failed_targets": failed_targets,
                "skipped_targets": skipped_targets,
                "resolved_account_targets": resolved_account_targets,
                "direct_telegram_targets": direct_telegram_targets,
                "in_app_notifications_created": in_app_notifications_created,
                "telegram_targets_sent": telegram_targets_sent,
                "items": [
                    {
                        "target": item.target,
                        "source": item.source,
                        "resolution": item.resolution,
                        "status": item.status,
                        "account_id": str(item.account_id) if item.account_id else None,
                        "telegram_id": item.telegram_id,
                        "channels_attempted": item.channels_attempted,
                        "in_app_notification_id": item.in_app_notification_id,
                        "telegram_message_ids": item.telegram_message_ids,
                        "detail": item.detail,
                    }
                    for item in items
                ],
            },
        },
    )
    session.add(audit_log)
    await session.flush()

    return BroadcastTestSendResult(
        broadcast_id=broadcast.id,
        audit_log_id=audit_log.id,
        total_targets=len(items),
        sent_targets=sent_targets,
        partial_targets=partial_targets,
        failed_targets=failed_targets,
        skipped_targets=skipped_targets,
        resolved_account_targets=resolved_account_targets,
        direct_telegram_targets=direct_telegram_targets,
        in_app_notifications_created=in_app_notifications_created,
        telegram_targets_sent=telegram_targets_sent,
        items=items,
    )


async def _send_broadcast_test_to_account(
    session: AsyncSession,
    *,
    broadcast: Broadcast,
    account: Account,
    source: str,
    target: str,
    channels: list[str],
) -> BroadcastTestSendTargetResult:
    attempted_channels: list[str] = []
    in_app_ok = False
    telegram_ok = False
    in_app_notification_id: int | None = None
    telegram_message_ids: list[str] = []
    detail_parts: list[str] = []

    if BroadcastChannel.IN_APP.value in channels:
        attempted_channels.append(BroadcastChannel.IN_APP.value)
        notification = await create_notification(
            session,
            account_id=account.id,
            type=NotificationType.BROADCAST,
            title=broadcast.title,
            body=build_broadcast_in_app_body(broadcast.body_html),
            priority=NotificationPriority.INFO,
            payload=build_broadcast_notification_payload(broadcast),
            action_label=(broadcast.buttons[0]["text"] if broadcast.buttons else None),
            action_url=(broadcast.buttons[0]["url"] if broadcast.buttons else None),
            channels=(NotificationChannel.IN_APP,),
            deliver_to_telegram=False,
        )
        if notification is not None:
            in_app_ok = True
            in_app_notification_id = notification.id
        else:
            detail_parts.append("in-app notification was not created")

    if BroadcastChannel.TELEGRAM.value in channels:
        attempted_channels.append(BroadcastChannel.TELEGRAM.value)
        if account.telegram_id is None:
            detail_parts.append("account does not have telegram_id")
        elif account.telegram_bot_blocked_at is not None:
            detail_parts.append("account previously blocked the Telegram bot")
        else:
            try:
                telegram_message_ids = await _send_broadcast_to_telegram(
                    telegram_id=int(account.telegram_id),
                    broadcast=broadcast,
                )
                telegram_ok = True
            except (
                BroadcastValidationError,
                TelegramNotificationConfigurationError,
                TelegramNotificationDeliveryError,
            ) as exc:
                if isinstance(exc, TelegramNotificationDeliveryError) and exc.mark_telegram_bot_blocked:
                    await mark_telegram_bot_blocked(session, account=account)
                detail_parts.append(str(exc))

    status = "skipped"
    success_count = int(in_app_ok) + int(telegram_ok)
    expected_count = len(attempted_channels)
    if expected_count == 0:
        status = "skipped"
    elif success_count == expected_count:
        status = "sent"
    elif success_count == 0:
        status = "failed"
    else:
        status = "partial"

    return BroadcastTestSendTargetResult(
        target=target,
        source=source,
        resolution="account",
        status=status,
        account_id=account.id,
        telegram_id=account.telegram_id,
        channels_attempted=attempted_channels,
        in_app_notification_id=in_app_notification_id,
        telegram_message_ids=telegram_message_ids,
        detail="; ".join(detail_parts) if detail_parts else None,
    )


async def _send_broadcast_test_to_direct_telegram(
    *,
    broadcast: Broadcast,
    telegram_id: int,
    channels: list[str],
) -> BroadcastTestSendTargetResult:
    attempted_channels: list[str] = []
    detail_parts: list[str] = []
    telegram_message_ids: list[str] = []
    telegram_ok = False

    if BroadcastChannel.IN_APP.value in channels:
        detail_parts.append("in-app delivery requires a local account")

    if BroadcastChannel.TELEGRAM.value in channels:
        attempted_channels.append(BroadcastChannel.TELEGRAM.value)
        try:
            telegram_message_ids = await _send_broadcast_to_telegram(
                telegram_id=telegram_id,
                broadcast=broadcast,
            )
            telegram_ok = True
        except (
            BroadcastValidationError,
            TelegramNotificationConfigurationError,
            TelegramNotificationDeliveryError,
        ) as exc:
            detail_parts.append(str(exc))
    else:
        detail_parts.append("broadcast does not have telegram channel enabled")

    status = "sent" if telegram_ok else "failed"
    if not attempted_channels:
        status = "skipped"

    return BroadcastTestSendTargetResult(
        target=str(telegram_id),
        source="telegram_id",
        resolution="telegram_direct",
        status=status,
        telegram_id=telegram_id,
        channels_attempted=attempted_channels,
        telegram_message_ids=telegram_message_ids,
        detail="; ".join(detail_parts) if detail_parts else None,
    )
