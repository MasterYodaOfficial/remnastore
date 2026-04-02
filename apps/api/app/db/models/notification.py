from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    Uuid,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


notification_enum_kwargs = dict(
    values_callable=lambda obj: [e.value for e in obj],
    native_enum=False,
    create_constraint=False,
)


class NotificationType(str, enum.Enum):
    BROADCAST = "broadcast"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"
    SUBSCRIPTION_EXPIRING = "subscription_expiring"
    SUBSCRIPTION_EXPIRED = "subscription_expired"
    SUBSCRIPTION_NO_CONNECTION = "subscription_no_connection"
    REFERRAL_REWARD_RECEIVED = "referral_reward_received"
    WITHDRAWAL_CREATED = "withdrawal_created"
    WITHDRAWAL_PAID = "withdrawal_paid"
    WITHDRAWAL_REJECTED = "withdrawal_rejected"


class NotificationPriority(str, enum.Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class NotificationChannel(str, enum.Enum):
    IN_APP = "in_app"
    TELEGRAM = "telegram"


class NotificationDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "dedupe_key", name="uq_notifications_account_dedupe_key"
        ),
        Index("ix_notifications_account_created", "account_id", "created_at"),
        Index(
            "ix_notifications_account_read_created",
            "account_id",
            "read_at",
            "created_at",
        ),
        Index("ix_notifications_type_created", "type", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, **notification_enum_kwargs, length=32),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text(), nullable=False)
    priority: Mapped[NotificationPriority] = mapped_column(
        Enum(NotificationPriority, **notification_enum_kwargs, length=16),
        nullable=False,
        default=NotificationPriority.INFO,
    )
    payload: Mapped[dict | None] = mapped_column(JSON())
    action_label: Mapped[str | None] = mapped_column(String(64))
    action_url: Mapped[str | None] = mapped_column(String(512))
    dedupe_key: Mapped[str | None] = mapped_column(String(191))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", "channel", name="uq_notification_deliveries_channel"
        ),
        Index("ix_notification_deliveries_status_retry", "status", "next_retry_at"),
        Index("ix_notification_deliveries_channel_status", "channel", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, **notification_enum_kwargs, length=16),
        nullable=False,
    )
    status: Mapped[NotificationDeliveryStatus] = mapped_column(
        Enum(NotificationDeliveryStatus, **notification_enum_kwargs, length=16),
        nullable=False,
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    attempts_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
