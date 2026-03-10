"""add payments and payment events

Revision ID: 20260310_add_payments
Revises: 20260310_add_ledger_entries
Create Date: 2026-03-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260310_add_payments"
down_revision = "20260310_add_ledger_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("flow_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default=sa.text("'RUB'")),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=False),
        sa.Column("external_reference", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("plan_code", sa.String(length=64), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("success_url", sa.String(length=512), nullable=True),
        sa.Column("cancel_url", sa.String(length=512), nullable=True),
        sa.Column("confirmation_url", sa.String(length=1024), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("provider", "provider_payment_id", name="uq_payments_provider_payment_id"),
        sa.UniqueConstraint("provider", "idempotency_key", name="uq_payments_provider_idempotency"),
    )
    op.create_index(
        "ix_payments_account_created",
        "payments",
        ["account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_payments_flow_status",
        "payments",
        ["flow_type", "status"],
        unique=False,
    )
    op.create_index(
        "ix_payments_external_reference",
        "payments",
        ["external_reference"],
        unique=False,
    )

    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("flow_type", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=128), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default=sa.text("'RUB'")),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            ondelete="SET NULL",
            name="fk_payment_events_payment_id",
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_payment_events_provider_event_id",
        ),
    )
    op.create_index(
        "ix_payment_events_payment_created",
        "payment_events",
        ["payment_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_payment_events_provider_payment",
        "payment_events",
        ["provider", "provider_payment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_payment_events_provider_payment", table_name="payment_events")
    op.drop_index("ix_payment_events_payment_created", table_name="payment_events")
    op.drop_table("payment_events")
    op.drop_index("ix_payments_external_reference", table_name="payments")
    op.drop_index("ix_payments_flow_status", table_name="payments")
    op.drop_index("ix_payments_account_created", table_name="payments")
    op.drop_table("payments")
