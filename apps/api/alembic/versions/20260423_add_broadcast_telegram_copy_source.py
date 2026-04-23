"""add telegram copy source fields to broadcasts

Revision ID: 20260423_broadcast_tg_copy
Revises: 20260416_ba_preset_channels
Create Date: 2026-04-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260423_broadcast_tg_copy"
down_revision = "20260416_ba_preset_channels"
branch_labels = None
depends_on = None


def _get_column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("broadcasts"):
        return

    existing_columns = _get_column_names(inspector, "broadcasts")
    if "telegram_copy_source_chat_id" not in existing_columns:
        op.add_column(
            "broadcasts",
            sa.Column("telegram_copy_source_chat_id", sa.BigInteger(), nullable=True),
        )
    if "telegram_copy_message_ids" not in existing_columns:
        op.add_column(
            "broadcasts",
            sa.Column("telegram_copy_message_ids", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("broadcasts"):
        return

    existing_columns = _get_column_names(inspector, "broadcasts")
    if "telegram_copy_message_ids" in existing_columns:
        op.drop_column("broadcasts", "telegram_copy_message_ids")
    if "telegram_copy_source_chat_id" in existing_columns:
        op.drop_column("broadcasts", "telegram_copy_source_chat_id")
