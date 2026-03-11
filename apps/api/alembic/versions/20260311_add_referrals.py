"""add referral attribution and reward history

Revision ID: 20260311_add_referrals
Revises: 20260311_expand_subscription_grants_for_wallet
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_add_referrals"
down_revision = "20260311_expand_subscription_grants_for_wallet"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referral_attributions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("referrer_account_id", sa.Uuid(), nullable=False),
        sa.Column("referred_account_id", sa.Uuid(), nullable=False),
        sa.Column("referral_code", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_referral_attributions_referrer_created",
        "referral_attributions",
        ["referrer_account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_referral_attributions_referred_account_id",
        "referral_attributions",
        ["referred_account_id"],
        unique=True,
    )
    op.create_index(
        "ix_referral_attributions_referral_code",
        "referral_attributions",
        ["referral_code"],
        unique=False,
    )

    op.create_table(
        "referral_rewards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("attribution_id", sa.Integer(), nullable=False),
        sa.Column("referrer_account_id", sa.Uuid(), nullable=False),
        sa.Column("referred_account_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_grant_id", sa.Integer(), nullable=False),
        sa.Column("ledger_entry_id", sa.Integer(), nullable=False),
        sa.Column("purchase_amount_rub", sa.BigInteger(), nullable=False),
        sa.Column("reward_amount", sa.BigInteger(), nullable=False),
        sa.Column("reward_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="RUB"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_referral_rewards_referrer_created",
        "referral_rewards",
        ["referrer_account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_referral_rewards_referred_account_id",
        "referral_rewards",
        ["referred_account_id"],
        unique=True,
    )
    op.create_index(
        "ix_referral_rewards_subscription_grant_id",
        "referral_rewards",
        ["subscription_grant_id"],
        unique=True,
    )
    op.create_index(
        "ix_referral_rewards_ledger_entry_id",
        "referral_rewards",
        ["ledger_entry_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_referral_rewards_ledger_entry_id", table_name="referral_rewards")
    op.drop_index("ix_referral_rewards_subscription_grant_id", table_name="referral_rewards")
    op.drop_index("ix_referral_rewards_referred_account_id", table_name="referral_rewards")
    op.drop_index("ix_referral_rewards_referrer_created", table_name="referral_rewards")
    op.drop_table("referral_rewards")

    op.drop_index("ix_referral_attributions_referral_code", table_name="referral_attributions")
    op.drop_index("ix_referral_attributions_referred_account_id", table_name="referral_attributions")
    op.drop_index("ix_referral_attributions_referrer_created", table_name="referral_attributions")
    op.drop_table("referral_attributions")
