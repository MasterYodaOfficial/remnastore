"""store referral earnings in rubles

Revision ID: 20260309_store_referral_earnings_rubles
Revises: 20260308_store_balance_rubles
Create Date: 2026-03-09
"""

from alembic import op


revision = "20260309_store_referral_earnings_rubles"
down_revision = "20260308_store_balance_rubles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("accounts", "referral_earnings_cents", new_column_name="referral_earnings")
    op.execute("UPDATE accounts SET referral_earnings = referral_earnings / 100")


def downgrade() -> None:
    op.execute("UPDATE accounts SET referral_earnings = referral_earnings * 100")
    op.alter_column("accounts", "referral_earnings", new_column_name="referral_earnings_cents")
