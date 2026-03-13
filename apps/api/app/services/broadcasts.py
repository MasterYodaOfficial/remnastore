from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
import uuid
from urllib.parse import urlparse

from sqlalchemy import Select, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Account,
    AccountStatus,
    AdminActionLog,
    AdminActionType,
    Broadcast,
    BroadcastAudienceSegment,
    BroadcastChannel,
    BroadcastContentType,
    BroadcastStatus,
    Payment,
)
from app.domain.payments import PaymentStatus


class BroadcastServiceError(Exception):
    pass


class BroadcastNotFoundError(BroadcastServiceError):
    pass


class BroadcastConflictError(BroadcastServiceError):
    pass


class BroadcastValidationError(BroadcastServiceError):
    pass


@dataclass(slots=True)
class BroadcastAudienceEstimate:
    total_accounts: int
    in_app_recipients: int
    telegram_recipients: int


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


def _is_allowed_button_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https", "tg"} and bool(parsed.netloc or parsed.path)


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
    segment: BroadcastAudienceSegment,
    exclude_blocked: bool,
) -> dict[str, str | bool]:
    return {
        "segment": segment.value,
        "exclude_blocked": exclude_blocked,
    }


def _build_base_audience_query(
    *,
    segment: BroadcastAudienceSegment,
    exclude_blocked: bool,
) -> Select[tuple[Account.id]]:
    now = datetime.now(UTC)
    query = select(Account.id)

    if exclude_blocked:
        query = query.where(Account.status != AccountStatus.BLOCKED)

    if segment == BroadcastAudienceSegment.ACTIVE:
        query = query.where(Account.status == AccountStatus.ACTIVE)
    elif segment == BroadcastAudienceSegment.WITH_TELEGRAM:
        query = query.where(Account.telegram_id.is_not(None))
    elif segment == BroadcastAudienceSegment.PAID:
        query = query.where(
            exists(
                select(Payment.id).where(
                    Payment.account_id == Account.id,
                    Payment.status == PaymentStatus.SUCCEEDED,
                )
            )
        )
    elif segment == BroadcastAudienceSegment.EXPIRED:
        query = query.where(
            Account.subscription_expires_at.is_not(None),
            Account.subscription_expires_at <= now,
        )

    return query


async def estimate_broadcast_audience(
    session: AsyncSession,
    *,
    segment: BroadcastAudienceSegment,
    exclude_blocked: bool,
    channels: tuple[BroadcastChannel, ...] | list[BroadcastChannel],
) -> BroadcastAudienceEstimate:
    channel_values = normalize_broadcast_channels(channels)
    base_query = _build_base_audience_query(
        segment=segment,
        exclude_blocked=exclude_blocked,
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
                .where(Account.telegram_id.is_not(None))
            )
            or 0
        )

    in_app_recipients = total_accounts if BroadcastChannel.IN_APP.value in channel_values else 0
    return BroadcastAudienceEstimate(
        total_accounts=total_accounts,
        in_app_recipients=in_app_recipients,
        telegram_recipients=telegram_recipients,
    )


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
    audience_segment: BroadcastAudienceSegment,
    audience_exclude_blocked: bool,
) -> Broadcast:
    normalized_name = _normalize_required_text(name, field_name="name")
    normalized_title = _normalize_required_text(title, field_name="title")
    normalized_body_html = validate_telegram_html_subset(body_html)
    normalized_channels = normalize_broadcast_channels(channels)
    normalized_buttons = normalize_broadcast_buttons(buttons)
    normalized_image_url = _normalize_optional_text(image_url)

    if content_type == BroadcastContentType.PHOTO and normalized_image_url is None:
        raise BroadcastValidationError("image_url is required for photo broadcast")
    if content_type == BroadcastContentType.TEXT:
        normalized_image_url = None

    estimate = await estimate_broadcast_audience(
        session,
        segment=audience_segment,
        exclude_blocked=audience_exclude_blocked,
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
        audience=build_broadcast_audience_payload(
            segment=audience_segment,
            exclude_blocked=audience_exclude_blocked,
        ),
        status=BroadcastStatus.DRAFT,
        estimated_total_accounts=estimate.total_accounts,
        estimated_in_app_recipients=estimate.in_app_recipients,
        estimated_telegram_recipients=estimate.telegram_recipients,
        created_by_admin_id=admin_id,
        updated_by_admin_id=admin_id,
    )
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
    audience_segment: BroadcastAudienceSegment,
    audience_exclude_blocked: bool,
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

    if content_type == BroadcastContentType.PHOTO and normalized_image_url is None:
        raise BroadcastValidationError("image_url is required for photo broadcast")
    if content_type == BroadcastContentType.TEXT:
        normalized_image_url = None

    estimate = await estimate_broadcast_audience(
        session,
        segment=audience_segment,
        exclude_blocked=audience_exclude_blocked,
        channels=channels,
    )

    broadcast.name = normalized_name
    broadcast.title = normalized_title
    broadcast.body_html = normalized_body_html
    broadcast.content_type = content_type
    broadcast.image_url = normalized_image_url
    broadcast.channels = normalized_channels
    broadcast.buttons = normalized_buttons
    broadcast.audience = build_broadcast_audience_payload(
        segment=audience_segment,
        exclude_blocked=audience_exclude_blocked,
    )
    broadcast.estimated_total_accounts = estimate.total_accounts
    broadcast.estimated_in_app_recipients = estimate.in_app_recipients
    broadcast.estimated_telegram_recipients = estimate.telegram_recipients
    broadcast.updated_by_admin_id = admin_id
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
