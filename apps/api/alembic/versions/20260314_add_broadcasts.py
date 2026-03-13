"""add broadcasts

Revision ID: 20260314_add_broadcasts
Revises: 20260313_add_admin_action_logs
Create Date: 2026-03-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260314_add_broadcasts"
down_revision = "20260313_add_admin_action_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=16), nullable=False),
        sa.Column("image_url", sa.String(length=1024), nullable=True),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("buttons", sa.JSON(), nullable=False),
        sa.Column("audience", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("estimated_total_accounts", sa.Integer(), nullable=False),
        sa.Column("estimated_in_app_recipients", sa.Integer(), nullable=False),
        sa.Column("estimated_telegram_recipients", sa.Integer(), nullable=False),
        sa.Column("created_by_admin_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_admin_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("launched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_broadcasts_status_created", "broadcasts", ["status", "created_at"], unique=False)
    op.create_index(
        "ix_broadcasts_created_by_created",
        "broadcasts",
        ["created_by_admin_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_broadcasts_updated", "broadcasts", ["updated_at"], unique=False)

    op.create_table(
        "broadcast_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("broadcast_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("attempts_count", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["broadcast_id"], ["broadcasts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "broadcast_id",
            "account_id",
            "channel",
            name="uq_broadcast_deliveries_target_channel",
        ),
    )
    op.create_index(
        "ix_broadcast_deliveries_broadcast_status",
        "broadcast_deliveries",
        ["broadcast_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_broadcast_deliveries_channel_status_retry",
        "broadcast_deliveries",
        ["channel", "status", "next_retry_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_broadcast_deliveries_channel_status_retry", table_name="broadcast_deliveries")
    op.drop_index("ix_broadcast_deliveries_broadcast_status", table_name="broadcast_deliveries")
    op.drop_table("broadcast_deliveries")

    op.drop_index("ix_broadcasts_updated", table_name="broadcasts")
    op.drop_index("ix_broadcasts_created_by_created", table_name="broadcasts")
    op.drop_index("ix_broadcasts_status_created", table_name="broadcasts")
    op.drop_table("broadcasts")
