from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


withdrawal_enum_kwargs = dict(
    values_callable=lambda obj: [e.value for e in obj],
    native_enum=False,
    create_constraint=False,
)


class WithdrawalStatus(str, enum.Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    PAID = "paid"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class WithdrawalDestinationType(str, enum.Enum):
    CARD = "card"
    SBP = "sbp"


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    __table_args__ = (
        Index("ix_withdrawals_account_created", "account_id", "created_at"),
        Index("ix_withdrawals_account_status_created", "account_id", "status", "created_at"),
        Index("ix_withdrawals_reserved_ledger_entry_id", "reserved_ledger_entry_id", unique=True),
        Index("ix_withdrawals_released_ledger_entry_id", "released_ledger_entry_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    destination_type: Mapped[WithdrawalDestinationType] = mapped_column(
        Enum(WithdrawalDestinationType, **withdrawal_enum_kwargs, length=16),
        nullable=False,
    )
    destination_value: Mapped[str] = mapped_column(String(255), nullable=False)
    user_comment: Mapped[str | None] = mapped_column(Text())
    admin_comment: Mapped[str | None] = mapped_column(Text())
    status: Mapped[WithdrawalStatus] = mapped_column(
        Enum(WithdrawalStatus, **withdrawal_enum_kwargs, length=16),
        nullable=False,
        default=WithdrawalStatus.NEW,
    )
    reserved_ledger_entry_id: Mapped[int | None] = mapped_column(nullable=True)
    released_ledger_entry_id: Mapped[int | None] = mapped_column(nullable=True)
    processed_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
