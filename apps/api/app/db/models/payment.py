from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.payments import PaymentFlowType, PaymentProvider, PaymentStatus


payment_enum_kwargs = dict(
    values_callable=lambda obj: [e.value for e in obj],
    native_enum=False,
    create_constraint=False,
)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_payment_id", name="uq_payments_provider_payment_id"
        ),
        UniqueConstraint(
            "provider", "idempotency_key", name="uq_payments_provider_idempotency"
        ),
        Index("ix_payments_account_created", "account_id", "created_at"),
        Index("ix_payments_flow_status", "flow_type", "status"),
        Index("ix_payments_external_reference", "external_reference"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider, **payment_enum_kwargs, length=32),
        nullable=False,
    )
    flow_type: Mapped[PaymentFlowType] = mapped_column(
        Enum(PaymentFlowType, **payment_enum_kwargs, length=32),
        nullable=False,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, **payment_enum_kwargs, length=32),
        nullable=False,
    )
    amount: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="RUB")
    provider_payment_id: Mapped[str] = mapped_column(Text(), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    plan_code: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(255))
    success_url: Mapped[str | None] = mapped_column(Text())
    cancel_url: Mapped[str | None] = mapped_column(Text())
    confirmation_url: Mapped[str | None] = mapped_column(Text())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[dict | None] = mapped_column(JSON())
    request_metadata: Mapped[dict | None] = mapped_column("metadata", JSON())
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_event_id", name="uq_payment_events_provider_event_id"
        ),
        Index("ix_payment_events_payment_created", "payment_id", "created_at"),
        Index("ix_payment_events_provider_payment", "provider", "provider_payment_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider, **payment_enum_kwargs, length=32),
        nullable=False,
    )
    flow_type: Mapped[PaymentFlowType | None] = mapped_column(
        Enum(PaymentFlowType, **payment_enum_kwargs, length=32),
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, **payment_enum_kwargs, length=32),
        nullable=False,
    )
    provider_event_id: Mapped[str] = mapped_column(Text(), nullable=False)
    provider_payment_id: Mapped[str] = mapped_column(Text(), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(64))
    amount: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="RUB")
    raw_payload: Mapped[dict] = mapped_column(JSON(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
