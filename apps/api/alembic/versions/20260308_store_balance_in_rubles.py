"""store balance in rubles

Revision ID: 20260308_store_balance_rubles
Revises: 20260308_add_link_type_to_tokens
Create Date: 2026-03-08
"""

from alembic import op


revision = "20260308_store_balance_rubles"
down_revision = "20260308_add_link_type_to_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("accounts", "balance_cents", new_column_name="balance")
    op.execute("UPDATE accounts SET balance = balance / 100")


def downgrade() -> None:
    op.execute("UPDATE accounts SET balance = balance * 100")
    op.alter_column("accounts", "balance", new_column_name="balance_cents")
