from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


broadcast_enum_kwargs = dict(
    values_callable=lambda obj: [e.value for e in obj],
    native_enum=False,
    create_constraint=False,
)


class BroadcastStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BroadcastContentType(str, enum.Enum):
    TEXT = "text"
    PHOTO = "photo"


class BroadcastChannel(str, enum.Enum):
    IN_APP = "in_app"
    TELEGRAM = "telegram"


class BroadcastAudienceSegment(str, enum.Enum):
    ALL = "all"
    ACTIVE = "active"
    WITH_TELEGRAM = "with_telegram"
    PAID = "paid"
    EXPIRED = "expired"


class BroadcastDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"


class Broadcast(Base):
    __tablename__ = "broadcasts"
    __table_args__ = (
        Index("ix_broadcasts_status_created", "status", "created_at"),
        Index("ix_broadcasts_created_by_created", "created_by_admin_id", "created_at"),
        Index("ix_broadcasts_updated", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body_html: Mapped[str] = mapped_column(Text(), nullable=False)
    content_type: Mapped[BroadcastContentType] = mapped_column(
        Enum(BroadcastContentType, **broadcast_enum_kwargs, length=16),
        nullable=False,
        default=BroadcastContentType.TEXT,
    )
    image_url: Mapped[str | None] = mapped_column(String(1024))
    channels: Mapped[list[str]] = mapped_column(JSON(), nullable=False)
    buttons: Mapped[list[dict]] = mapped_column(JSON(), nullable=False, default=list)
    audience: Mapped[dict] = mapped_column(JSON(), nullable=False)
    status: Mapped[BroadcastStatus] = mapped_column(
        Enum(BroadcastStatus, **broadcast_enum_kwargs, length=16),
        nullable=False,
        default=BroadcastStatus.DRAFT,
    )
    estimated_total_accounts: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    estimated_in_app_recipients: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    estimated_telegram_recipients: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_by_admin_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BroadcastDelivery(Base):
    __tablename__ = "broadcast_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "broadcast_id",
            "account_id",
            "channel",
            name="uq_broadcast_deliveries_target_channel",
        ),
        Index("ix_broadcast_deliveries_broadcast_status", "broadcast_id", "status"),
        Index(
            "ix_broadcast_deliveries_channel_status_retry",
            "channel",
            "status",
            "next_retry_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    broadcast_id: Mapped[int] = mapped_column(
        ForeignKey("broadcasts.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    channel: Mapped[BroadcastChannel] = mapped_column(
        Enum(BroadcastChannel, **broadcast_enum_kwargs, length=16),
        nullable=False,
    )
    status: Mapped[BroadcastDeliveryStatus] = mapped_column(
        Enum(BroadcastDeliveryStatus, **broadcast_enum_kwargs, length=16),
        nullable=False,
        default=BroadcastDeliveryStatus.PENDING,
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    attempts_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
