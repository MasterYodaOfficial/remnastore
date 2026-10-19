"""Add device pricing, prepaid periods and durable device purchases.

Revision ID: 20261019_hwid_devices
Revises: 20261019_subscription_plans
"""

import sqlalchemy as sa
from alembic import op

revision = "20261019_hwid_devices"
down_revision = "20261019_subscription_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "extra_device_price_rub" not in {
        c["name"] for c in inspector.get_columns("subscription_plans")
    }:
        op.add_column(
            "subscription_plans", sa.Column("extra_device_price_rub", sa.BigInteger())
        )
    if "device_metadata" not in {
        c["name"] for c in inspector.get_columns("subscription_grants")
    }:
        op.add_column("subscription_grants", sa.Column("device_metadata", sa.JSON()))
    # A fresh install already includes these tables through the initial revision.
    if not inspector.has_table("account_device_settings"):
        op.create_table(
            "account_device_settings",
            sa.Column(
                "account_id",
                sa.Uuid(),
                sa.ForeignKey("accounts.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("base_limit", sa.Integer(), nullable=False),
            sa.Column("extra_count", sa.Integer(), nullable=False),
            sa.Column("renewal_extra_count", sa.Integer(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint("base_limit >= 0", name="ck_device_settings_base_limit"),
            sa.CheckConstraint(
                "extra_count >= 0", name="ck_device_settings_extra_count"
            ),
            sa.CheckConstraint(
                "renewal_extra_count >= 0", name="ck_device_settings_renewal_count"
            ),
        )
    if not inspector.has_table("device_pricing_periods"):
        op.create_table(
            "device_pricing_periods",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "account_id",
                sa.Uuid(),
                sa.ForeignKey("accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "grant_id",
                sa.Integer(),
                sa.ForeignKey("subscription_grants.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("extra_device_price_rub", sa.BigInteger()),
        )
        op.create_index(
            "ix_device_pricing_account_end",
            "device_pricing_periods",
            ["account_id", "ends_at"],
        )
    if not inspector.has_table("device_purchases"):
        op.create_table(
            "device_purchases",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "account_id",
                sa.Uuid(),
                sa.ForeignKey("accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
            sa.Column("quote_hash", sa.String(64), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("target_extra_count", sa.Integer(), nullable=False),
            sa.Column("amount", sa.BigInteger(), nullable=False),
            sa.Column(
                "subscription_expires_at", sa.DateTime(timezone=True), nullable=False
            ),
            sa.Column("allocations", sa.JSON(), nullable=False),
            sa.Column("applied_at", sa.DateTime(timezone=True)),
            sa.Column("refunded_at", sa.DateTime(timezone=True)),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint("amount >= 0", name="ck_device_purchases_amount"),
        )
        op.create_index(
            "ix_device_purchases_account_pending",
            "device_purchases",
            ["account_id", "applied_at"],
        )
    if not inspector.has_table("device_prepayments"):
        op.create_table(
            "device_prepayments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "account_id",
                sa.Uuid(),
                sa.ForeignKey("accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("reference", sa.String(160), nullable=False, unique=True),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("active_quantity", sa.Integer(), nullable=False),
            sa.Column("first_extra", sa.Integer(), nullable=False),
            sa.Column("amount_rub", sa.BigInteger(), nullable=False),
            sa.Column("credited_rub", sa.BigInteger(), nullable=False),
        )
        op.create_index(
            "ix_device_prepayments_account_end",
            "device_prepayments",
            ["account_id", "ends_at"],
        )


def downgrade() -> None:
    for table in (
        "device_prepayments",
        "device_purchases",
        "device_pricing_periods",
        "account_device_settings",
    ):
        op.drop_table(table)
    op.drop_column("subscription_grants", "device_metadata")
    op.drop_column("subscription_plans", "extra_device_price_rub")
