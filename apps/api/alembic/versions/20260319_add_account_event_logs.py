"""add account event logs

Revision ID: 20260319_add_account_event_logs
Revises: 20260314_init_schema
Create Date: 2026-03-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260319_add_account_event_logs"
down_revision = "20260314_init_schema"
branch_labels = None
depends_on = None


def _get_index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("account_event_logs"):
        op.create_table(
            "account_event_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("account_id", sa.Uuid(as_uuid=True), nullable=True),
            sa.Column("actor_account_id", sa.Uuid(as_uuid=True), nullable=True),
            sa.Column("actor_admin_id", sa.Uuid(as_uuid=True), nullable=True),
            sa.Column("event_type", sa.String(length=128), nullable=False),
            sa.Column("outcome", sa.String(length=32), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=True),
            sa.Column("request_id", sa.String(length=128), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        existing_indexes: set[str] = set()
    else:
        existing_indexes = _get_index_names(inspector, "account_event_logs")
    if "ix_account_event_logs_account_created" not in existing_indexes:
        op.create_index(
            "ix_account_event_logs_account_created",
            "account_event_logs",
            ["account_id", "created_at"],
            unique=False,
        )
    if "ix_account_event_logs_event_created" not in existing_indexes:
        op.create_index(
            "ix_account_event_logs_event_created",
            "account_event_logs",
            ["event_type", "created_at"],
            unique=False,
        )
    if "ix_account_event_logs_request_id" not in existing_indexes:
        op.create_index(
            "ix_account_event_logs_request_id",
            "account_event_logs",
            ["request_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("account_event_logs"):
        return

    existing_indexes = _get_index_names(inspector, "account_event_logs")
    if "ix_account_event_logs_request_id" in existing_indexes:
        op.drop_index(
            "ix_account_event_logs_request_id", table_name="account_event_logs"
        )
    if "ix_account_event_logs_event_created" in existing_indexes:
        op.drop_index(
            "ix_account_event_logs_event_created", table_name="account_event_logs"
        )
    if "ix_account_event_logs_account_created" in existing_indexes:
        op.drop_index(
            "ix_account_event_logs_account_created", table_name="account_event_logs"
        )
    op.drop_table("account_event_logs")
