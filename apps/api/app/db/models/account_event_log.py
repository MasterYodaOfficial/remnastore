from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountEventLog(Base):
    __tablename__ = "account_event_logs"
    __table_args__ = (
        Index("ix_account_event_logs_account_created", "account_id", "created_at"),
        Index("ix_account_event_logs_event_created", "event_type", "created_at"),
        Index("ix_account_event_logs_request_id", "request_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    actor_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    actor_admin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    source: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict | None] = mapped_column(JSON())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
