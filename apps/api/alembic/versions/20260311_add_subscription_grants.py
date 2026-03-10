"""add subscription grants

Revision ID: 20260311_add_subscription_grants
Revises: 20260310_add_payments
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260311_add_subscription_grants"
down_revision = "20260310_add_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_grants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("plan_code", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default=sa.text("'RUB'")),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("base_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            ondelete="RESTRICT",
            name="fk_subscription_grants_payment_id",
        ),
    )
    op.create_index(
        "ix_subscription_grants_account_created",
        "subscription_grants",
        ["account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_subscription_grants_payment_id",
        "subscription_grants",
        ["payment_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_subscription_grants_payment_id", table_name="subscription_grants")
    op.drop_index("ix_subscription_grants_account_created", table_name="subscription_grants")
    op.drop_table("subscription_grants")
