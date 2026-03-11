import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SubscriptionGrant(Base):
    __tablename__ = "subscription_grants"
    __table_args__ = (
        Index("ix_subscription_grants_account_created", "account_id", "created_at"),
        Index("ix_subscription_grants_payment_id", "payment_id", unique=True),
        Index(
            "ix_subscription_grants_source_reference",
            "purchase_source",
            "reference_type",
            "reference_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"),
    )
    purchase_source: Mapped[str] = mapped_column(String(32), nullable=False, default="direct_payment")
    reference_type: Mapped[str | None] = mapped_column(String(64))
    reference_id: Mapped[str | None] = mapped_column(String(128))
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="RUB")
    duration_days: Mapped[int] = mapped_column(nullable=False)
    base_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
