from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BroadcastAudiencePreset(Base):
    __tablename__ = "broadcast_audience_presets"
    __table_args__ = (
        Index("ix_broadcast_audience_presets_updated", "updated_at"),
        Index(
            "ix_broadcast_audience_presets_created_by",
            "created_by_admin_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text())
    channels: Mapped[list[str]] = mapped_column(JSON(), nullable=False)
    audience: Mapped[dict] = mapped_column(JSON(), nullable=False)
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    updated_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
