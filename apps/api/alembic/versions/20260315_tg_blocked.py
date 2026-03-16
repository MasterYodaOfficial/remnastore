"""add telegram bot blocked marker to accounts

Revision ID: 20260315_tg_blocked
Revises: 20260314_init_schema
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260315_tg_blocked"
down_revision = "20260314_init_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("accounts")}
    if "telegram_bot_blocked_at" in existing_columns:
        return
    op.add_column(
        "accounts",
        sa.Column("telegram_bot_blocked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("accounts")}
    if "telegram_bot_blocked_at" not in existing_columns:
        return
    op.drop_column("accounts", "telegram_bot_blocked_at")
