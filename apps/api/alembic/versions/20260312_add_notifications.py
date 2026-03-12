"""add notifications

Revision ID: 20260312_add_notifications
Revises: 20260312_initial_schema
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260312_add_notifications"
down_revision = "20260312_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("action_label", sa.String(length=64), nullable=True),
        sa.Column("action_url", sa.String(length=512), nullable=True),
        sa.Column("dedupe_key", sa.String(length=191), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "dedupe_key", name="uq_notifications_account_dedupe_key"),
    )
    op.create_index(
        "ix_notifications_account_created",
        "notifications",
        ["account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_account_read_created",
        "notifications",
        ["account_id", "read_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_type_created",
        "notifications",
        ["type", "created_at"],
        unique=False,
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", "channel", name="uq_notification_deliveries_channel"),
    )
    op.create_index(
        "ix_notification_deliveries_status_retry",
        "notification_deliveries",
        ["status", "next_retry_at"],
        unique=False,
    )
    op.create_index(
        "ix_notification_deliveries_channel_status",
        "notification_deliveries",
        ["channel", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_channel_status", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_status_retry", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")

    op.drop_index("ix_notifications_type_created", table_name="notifications")
    op.drop_index("ix_notifications_account_read_created", table_name="notifications")
    op.drop_index("ix_notifications_account_created", table_name="notifications")
    op.drop_table("notifications")
