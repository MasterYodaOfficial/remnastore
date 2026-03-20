import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    Index,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LedgerEntryType(str, enum.Enum):
    TOPUP_MANUAL = "topup_manual"
    TOPUP_PAYMENT = "topup_payment"
    SUBSCRIPTION_DEBIT = "subscription_debit"
    REFERRAL_REWARD = "referral_reward"
    WITHDRAWAL_RESERVE = "withdrawal_reserve"
    WITHDRAWAL_RELEASE = "withdrawal_release"
    WITHDRAWAL_PAYOUT = "withdrawal_payout"
    PROMO_CREDIT = "promo_credit"
    REFUND = "refund"
    ADMIN_CREDIT = "admin_credit"
    ADMIN_DEBIT = "admin_debit"
    MERGE_CREDIT = "merge_credit"
    MERGE_DEBIT = "merge_debit"


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="ck_ledger_entries_nonzero_amount"),
        CheckConstraint(
            "balance_after = balance_before + amount",
            name="ck_ledger_entries_balance_progression",
        ),
        Index("ix_ledger_entries_account_created", "account_id", "created_at"),
        Index("ix_ledger_entries_reference", "reference_type", "reference_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    entry_type: Mapped[LedgerEntryType] = mapped_column(
        Enum(
            LedgerEntryType,
            values_callable=lambda obj: [e.value for e in obj],
            native_enum=False,
            length=32,
            create_constraint=False,
        ),
        nullable=False,
    )
    amount: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    balance_before: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(64))
    reference_id: Mapped[str | None] = mapped_column(String(128))
    comment: Mapped[str | None] = mapped_column(Text())
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    created_by_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
