"""add channels to broadcast audience presets

Revision ID: 20260416_ba_preset_channels
Revises: 20260319_add_account_event_logs
Create Date: 2026-04-16
"""

from __future__ import annotations

import json

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

    existing_columns = _get_column_names(inspector, "broadcast_audience_presets")
    if "channels" not in existing_columns:
        op.add_column(
            "broadcast_audience_presets",
            sa.Column("channels", sa.JSON(), nullable=True),
        )

    default_channels = json.dumps(["in_app"])
    op.execute(
        sa.text(
            "UPDATE broadcast_audience_presets "
            "SET channels = CAST(:default_channels AS JSON) "
            "WHERE channels IS NULL"
        ).bindparams(default_channels=default_channels)
    )
    op.alter_column(
        "broadcast_audience_presets",
        "channels",
        nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("broadcast_audience_presets"):
        return

    existing_columns = _get_column_names(inspector, "broadcast_audience_presets")
    if "channels" in existing_columns:
        op.drop_column("broadcast_audience_presets", "channels")
