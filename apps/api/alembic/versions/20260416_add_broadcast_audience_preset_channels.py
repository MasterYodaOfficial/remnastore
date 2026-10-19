"""add channels to broadcast audience presets

Revision ID: 20260416_ba_preset_channels
Revises: 20260319_add_account_event_logs
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260416_ba_preset_channels"
down_revision = "20260319_add_account_event_logs"
branch_labels = None
depends_on = None


def _get_column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("broadcast_audience_presets"):
        return

    existing_columns = {
        column["name"]: column
        for column in inspector.get_columns("broadcast_audience_presets")
    }
    if "channels" not in existing_columns:
        op.add_column(
            "broadcast_audience_presets",
            sa.Column("channels", sa.JSON(), nullable=True),
        )

    presets = sa.table("broadcast_audience_presets", sa.column("channels", sa.JSON()))
    op.execute(
        presets.update().where(presets.c.channels.is_(None)).values(channels=["in_app"])
    )
    if "channels" not in existing_columns or existing_columns["channels"]["nullable"]:
        # SQLite versions used by CI need table recreation to change nullability.
        # On PostgreSQL the same batch operation emits a normal ALTER COLUMN.
        with op.batch_alter_table("broadcast_audience_presets") as batch_op:
            batch_op.alter_column("channels", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("broadcast_audience_presets"):
        return

    existing_columns = _get_column_names(inspector, "broadcast_audience_presets")
    if "channels" in existing_columns:
        op.drop_column("broadcast_audience_presets", "channels")
