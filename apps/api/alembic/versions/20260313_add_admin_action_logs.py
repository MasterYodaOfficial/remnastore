"""add admin action logs

Revision ID: 20260313_add_admin_action_logs
Revises: 20260312_add_admins
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260313_add_admin_action_logs"
down_revision = "20260312_add_admins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_action_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("admin_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("target_account_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_type",
            "idempotency_key",
            name="uq_admin_action_logs_type_idempotency",
        ),
    )
    op.create_index(
        "ix_admin_action_logs_admin_created",
        "admin_action_logs",
        ["admin_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_action_logs_target_account_created",
        "admin_action_logs",
        ["target_account_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_admin_action_logs_target_account_created", table_name="admin_action_logs")
    op.drop_index("ix_admin_action_logs_admin_created", table_name="admin_action_logs")
    op.drop_table("admin_action_logs")
