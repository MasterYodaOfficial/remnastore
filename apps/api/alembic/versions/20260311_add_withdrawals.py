"""add referral withdrawals

Revision ID: 20260311_add_withdrawals
Revises: 20260311_add_referrals
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_add_withdrawals"
down_revision = "20260311_add_referrals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "withdrawals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("destination_type", sa.String(length=16), nullable=False),
        sa.Column("destination_value", sa.String(length=255), nullable=False),
        sa.Column("user_comment", sa.Text(), nullable=True),
        sa.Column("admin_comment", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reserved_ledger_entry_id", sa.Integer(), nullable=True),
        sa.Column("released_ledger_entry_id", sa.Integer(), nullable=True),
        sa.Column("processed_by_admin_id", sa.Uuid(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_withdrawals_account_created",
        "withdrawals",
        ["account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_withdrawals_account_status_created",
        "withdrawals",
        ["account_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_withdrawals_reserved_ledger_entry_id",
        "withdrawals",
        ["reserved_ledger_entry_id"],
        unique=True,
    )
    op.create_index(
        "ix_withdrawals_released_ledger_entry_id",
        "withdrawals",
        ["released_ledger_entry_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_withdrawals_released_ledger_entry_id", table_name="withdrawals")
    op.drop_index("ix_withdrawals_reserved_ledger_entry_id", table_name="withdrawals")
    op.drop_index("ix_withdrawals_account_status_created", table_name="withdrawals")
    op.drop_index("ix_withdrawals_account_created", table_name="withdrawals")
    op.drop_table("withdrawals")
