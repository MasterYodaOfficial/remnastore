"""add balance and referral fields to accounts

Revision ID: 20260303_add_balance_referrals
Revises: 20260227_create_accounts
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260303_add_balance_referrals"
down_revision = "20260227_create_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column(
            "balance_cents",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "accounts",
        sa.Column("referral_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "referral_earnings_cents",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "referrals_count",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "referral_reward_rate",
            sa.Numeric(5, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "referred_by_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_accounts_referral_code", "accounts", ["referral_code"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_accounts_referral_code", "accounts", type_="unique")
    op.drop_column("accounts", "referred_by_account_id")
    op.drop_column("accounts", "referral_reward_rate")
    op.drop_column("accounts", "referrals_count")
    op.drop_column("accounts", "referral_earnings_cents")
    op.drop_column("accounts", "referral_code")
    op.drop_column("accounts", "balance_cents")
