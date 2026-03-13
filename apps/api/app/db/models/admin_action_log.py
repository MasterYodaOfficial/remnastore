from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


admin_action_enum_kwargs = dict(
    values_callable=lambda obj: [e.value for e in obj],
    native_enum=False,
    create_constraint=False,
)


class AdminActionType(str, enum.Enum):
    BALANCE_ADJUSTMENT = "balance_adjustment"
    SUBSCRIPTION_GRANT = "subscription_grant"


class AdminActionLog(Base):
    __tablename__ = "admin_action_logs"
    __table_args__ = (
        UniqueConstraint(
            "action_type",
            "idempotency_key",
            name="uq_admin_action_logs_type_idempotency",
        ),
        Index("ix_admin_action_logs_admin_created", "admin_id", "created_at"),
        Index("ix_admin_action_logs_target_account_created", "target_account_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    admin_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    action_type: Mapped[AdminActionType] = mapped_column(
        Enum(AdminActionType, **admin_action_enum_kwargs, length=64),
        nullable=False,
    )
    target_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    comment: Mapped[str | None] = mapped_column(Text())
    payload: Mapped[dict | None] = mapped_column(JSON())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
