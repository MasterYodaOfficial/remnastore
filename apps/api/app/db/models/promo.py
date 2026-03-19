from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


promo_enum_kwargs = dict(
    values_callable=lambda obj: [e.value for e in obj],
    native_enum=False,
    create_constraint=False,
)


class PromoCampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class PromoEffectType(str, enum.Enum):
    PERCENT_DISCOUNT = "percent_discount"
    FIXED_DISCOUNT = "fixed_discount"
    FIXED_PRICE = "fixed_price"
    EXTRA_DAYS = "extra_days"
    FREE_DAYS = "free_days"
    BALANCE_CREDIT = "balance_credit"


class PromoRedemptionStatus(str, enum.Enum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    CANCELED = "canceled"


class PromoRedemptionContext(str, enum.Enum):
    DIRECT = "direct"
    PLAN_PURCHASE = "plan_purchase"
    SUBSCRIPTION_GRANT = "subscription_grant"
    BALANCE_CREDIT = "balance_credit"


class PromoCampaign(Base):
    __tablename__ = "promo_campaigns"
    __table_args__ = (
        Index("ix_promo_campaigns_status_created", "status", "created_at"),
        Index("ix_promo_campaigns_window", "starts_at", "ends_at"),
        Index("ix_promo_campaigns_created_by_admin", "created_by_admin_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text())
    status: Mapped[PromoCampaignStatus] = mapped_column(
        Enum(PromoCampaignStatus, **promo_enum_kwargs, length=32),
        nullable=False,
        default=PromoCampaignStatus.DRAFT,
    )
    effect_type: Mapped[PromoEffectType] = mapped_column(
        Enum(PromoEffectType, **promo_enum_kwargs, length=32),
        nullable=False,
    )
    effect_value: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="RUB")
    plan_codes: Mapped[list[str] | None] = mapped_column(JSON())
    first_purchase_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_active_subscription: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_no_active_subscription: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_redemptions_limit: Mapped[int | None] = mapped_column()
    per_account_redemptions_limit: Mapped[int | None] = mapped_column()
    created_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("admins.id", ondelete="SET NULL"),
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


class PromoCode(Base):
    __tablename__ = "promo_codes"
    __table_args__ = (
        UniqueConstraint("code", name="uq_promo_codes_code"),
        Index("ix_promo_codes_campaign_created", "campaign_id", "created_at"),
        Index("ix_promo_codes_assigned_account", "assigned_account_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("promo_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    assigned_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    max_redemptions: Mapped[int | None] = mapped_column()
    created_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("admins.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"
    __table_args__ = (
        UniqueConstraint("reference_type", "reference_id", name="uq_promo_redemptions_reference"),
        Index("ix_promo_redemptions_campaign_created", "campaign_id", "created_at"),
        Index("ix_promo_redemptions_code_created", "promo_code_id", "created_at"),
        Index("ix_promo_redemptions_account_created", "account_id", "created_at"),
        Index("ix_promo_redemptions_reference", "reference_type", "reference_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("promo_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    promo_code_id: Mapped[int] = mapped_column(
        ForeignKey("promo_codes.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[PromoRedemptionStatus] = mapped_column(
        Enum(PromoRedemptionStatus, **promo_enum_kwargs, length=32),
        nullable=False,
        default=PromoRedemptionStatus.PENDING,
    )
    redemption_context: Mapped[PromoRedemptionContext] = mapped_column(
        Enum(PromoRedemptionContext, **promo_enum_kwargs, length=32),
        nullable=False,
        default=PromoRedemptionContext.DIRECT,
    )
    plan_code: Mapped[str | None] = mapped_column(String(64))
    effect_type: Mapped[PromoEffectType] = mapped_column(
        Enum(PromoEffectType, **promo_enum_kwargs, length=32),
        nullable=False,
    )
    effect_value: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="RUB")
    original_amount: Mapped[int | None] = mapped_column(BigInteger())
    discount_amount: Mapped[int | None] = mapped_column(BigInteger())
    final_amount: Mapped[int | None] = mapped_column(BigInteger())
    granted_duration_days: Mapped[int | None] = mapped_column()
    balance_credit_amount: Mapped[int | None] = mapped_column(BigInteger())
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"))
    subscription_grant_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscription_grants.id", ondelete="SET NULL")
    )
    ledger_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("ledger_entries.id", ondelete="SET NULL")
    )
    reference_type: Mapped[str | None] = mapped_column(String(64))
    reference_id: Mapped[str | None] = mapped_column(String(128))
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
