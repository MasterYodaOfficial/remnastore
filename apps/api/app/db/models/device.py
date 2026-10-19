import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountDeviceSettings(Base):
    __tablename__ = "account_device_settings"
    __table_args__ = (
        CheckConstraint("base_limit >= 0", name="ck_device_settings_base_limit"),
        CheckConstraint("extra_count >= 0", name="ck_device_settings_extra_count"),
        CheckConstraint(
            "renewal_extra_count >= 0", name="ck_device_settings_renewal_count"
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    base_limit: Mapped[int] = mapped_column(nullable=False)
    extra_count: Mapped[int] = mapped_column(default=0, nullable=False)
    renewal_extra_count: Mapped[int] = mapped_column(default=0, nullable=False)
    revision: Mapped[int] = mapped_column(default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DevicePricingPeriod(Base):
    __tablename__ = "device_pricing_periods"
    __table_args__ = (Index("ix_device_pricing_account_end", "account_id", "ends_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    grant_id: Mapped[int] = mapped_column(
        ForeignKey("subscription_grants.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    extra_device_price_rub: Mapped[int | None] = mapped_column(BigInteger())


class DevicePurchase(Base):
    """A durable wallet debit and desired limit, reconciled after a panel outage."""

    __tablename__ = "device_purchases"
    __table_args__ = (
        Index("ix_device_purchases_account_pending", "account_id", "applied_at"),
        CheckConstraint("amount >= 0", name="ck_device_purchases_amount"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False
    )
    quote_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    target_extra_count: Mapped[int] = mapped_column(nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    subscription_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    allocations: Mapped[list[dict]] = mapped_column(JSON(), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DevicePrepayment(Base):
    """Tracks the actual RUB paid for seats so a downgrade cannot over-credit."""

    __tablename__ = "device_prepayments"
    __table_args__ = (
        Index("ix_device_prepayments_account_end", "account_id", "ends_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    reference: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    active_quantity: Mapped[int] = mapped_column(nullable=False)
    first_extra: Mapped[int] = mapped_column(default=1, nullable=False)
    amount_rub: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    credited_rub: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0)
