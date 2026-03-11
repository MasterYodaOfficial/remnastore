"""expand subscription grants for wallet purchases

Revision ID: 20260311_expand_subscription_grants_for_wallet
Revises: 20260311_expand_payment_ids
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_expand_subscription_grants_for_wallet"
down_revision = "20260311_expand_payment_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscription_grants",
        sa.Column("purchase_source", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "subscription_grants",
        sa.Column("reference_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "subscription_grants",
        sa.Column("reference_id", sa.String(length=128), nullable=True),
    )

    op.execute(
        """
        UPDATE subscription_grants
        SET purchase_source = 'direct_payment',
            reference_type = 'payment',
            reference_id = payment_id::text
        WHERE payment_id IS NOT NULL
        """
    )

    op.alter_column("subscription_grants", "purchase_source", nullable=False)
    op.alter_column("subscription_grants", "payment_id", nullable=True)

    op.create_index(
        "ix_subscription_grants_source_reference",
        "subscription_grants",
        ["purchase_source", "reference_type", "reference_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_subscription_grants_source_reference", table_name="subscription_grants")
    op.alter_column("subscription_grants", "payment_id", nullable=False)
    op.drop_column("subscription_grants", "reference_id")
    op.drop_column("subscription_grants", "reference_type")
    op.drop_column("subscription_grants", "purchase_source")
