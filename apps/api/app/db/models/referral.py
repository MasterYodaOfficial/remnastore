import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReferralAttribution(Base):
    __tablename__ = "referral_attributions"
    __table_args__ = (
        Index("ix_referral_attributions_referrer_created", "referrer_account_id", "created_at"),
        Index("ix_referral_attributions_referred_account_id", "referred_account_id", unique=True),
        Index("ix_referral_attributions_referral_code", "referral_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    referrer_account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    referred_account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    referral_code: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class ReferralReward(Base):
    __tablename__ = "referral_rewards"
    __table_args__ = (
        Index("ix_referral_rewards_referrer_created", "referrer_account_id", "created_at"),
        Index("ix_referral_rewards_referred_account_id", "referred_account_id", unique=True),
        Index("ix_referral_rewards_subscription_grant_id", "subscription_grant_id", unique=True),
        Index("ix_referral_rewards_ledger_entry_id", "ledger_entry_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    attribution_id: Mapped[int] = mapped_column(nullable=False)
    referrer_account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    referred_account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    subscription_grant_id: Mapped[int] = mapped_column(nullable=False)
    ledger_entry_id: Mapped[int] = mapped_column(nullable=False)
    purchase_amount_rub: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    reward_amount: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    reward_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class TelegramReferralIntent(Base):
    __tablename__ = "telegram_referral_intents"
    __table_args__ = (
        Index("ix_tg_ref_intents_telegram_id", "telegram_id", unique=True),
        Index("ix_tg_ref_intents_account_id", "account_id"),
        Index("ix_tg_ref_intents_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    referral_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    result_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
