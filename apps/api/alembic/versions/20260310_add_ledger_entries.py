"""add ledger entries

Revision ID: 20260310_add_ledger_entries
Revises: 20260309_initial_schema
Create Date: 2026-03-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260310_add_ledger_entries"
down_revision = "20260309_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'RUB'")),
        sa.Column("balance_before", sa.BigInteger(), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("reference_type", sa.String(length=64), nullable=True),
        sa.Column("reference_id", sa.String(length=128), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_by_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount <> 0", name="ck_ledger_entries_nonzero_amount"),
        sa.CheckConstraint(
            "balance_after = balance_before + amount",
            name="ck_ledger_entries_balance_progression",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_ledger_entries_idempotency_key"),
    )
    op.create_index(
        "ix_ledger_entries_account_created",
        "ledger_entries",
        ["account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ledger_entries_reference",
        "ledger_entries",
        ["reference_type", "reference_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ledger_entries_reference", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_account_created", table_name="ledger_entries")
    op.drop_table("ledger_entries")
