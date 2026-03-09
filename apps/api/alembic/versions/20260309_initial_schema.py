"""create initial schema

Revision ID: 20260309_initial_schema
Revises:
Create Date: 2026-03-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260309_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


account_status_enum = postgresql.ENUM(
    "active",
    "blocked",
    name="accountstatus",
    create_type=False,
)
login_source_enum = postgresql.ENUM(
    "telegram_webapp",
    "telegram_bot_start",
    "browser_oauth",
    name="loginsource",
    create_type=False,
)
auth_provider_enum = postgresql.ENUM(
    "supabase",
    "google",
    "yandex",
    "vk",
    name="authprovider",
    create_type=False,
)
link_type_enum = postgresql.ENUM(
    "telegram_from_browser",
    "browser_from_telegram",
    name="linktype",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    account_status_enum.create(bind, checkfirst=True)
    login_source_enum.create(bind, checkfirst=True)
    auth_provider_enum.create(bind, checkfirst=True)
    link_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=64), nullable=True),
        sa.Column("last_name", sa.String(length=64), nullable=True),
        sa.Column("is_premium", sa.Boolean(), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=True),
        sa.Column("remnawave_user_uuid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subscription_url", sa.String(length=512), nullable=True),
        sa.Column("subscription_status", sa.String(length=32), nullable=True),
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subscription_last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subscription_is_trial", sa.Boolean(), nullable=False),
        sa.Column("trial_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("balance", sa.BigInteger(), nullable=False),
        sa.Column("referral_code", sa.String(length=64), nullable=True),
        sa.Column("referral_earnings", sa.BigInteger(), nullable=False),
        sa.Column("referrals_count", sa.BigInteger(), nullable=False),
        sa.Column("referral_reward_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "referred_by_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            account_status_enum,
            nullable=False,
        ),
        sa.Column("last_login_source", login_source_enum, nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("telegram_id", name="uq_accounts_telegram_id"),
        sa.UniqueConstraint("referral_code", name="uq_accounts_referral_code"),
    )
    op.create_index(
        "ix_accounts_remnawave_user_uuid",
        "accounts",
        ["remnawave_user_uuid"],
        unique=False,
    )

    op.create_table(
        "auth_accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", auth_provider_enum, nullable=False),
        sa.Column("provider_uid", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("provider", "provider_uid", name="uq_auth_provider_uid"),
    )
    op.create_index(
        "ix_auth_accounts_account_id",
        "auth_accounts",
        ["account_id"],
        unique=False,
    )

    op.create_table(
        "auth_link_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("link_token", sa.String(length=128), nullable=False),
        sa.Column("provider", auth_provider_enum, nullable=False),
        sa.Column("provider_uid", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("link_type", link_type_enum, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("link_token", name="uq_link_token"),
    )
    op.create_index(
        "ix_auth_link_tokens_provider_uid",
        "auth_link_tokens",
        ["provider", "provider_uid"],
        unique=False,
    )
    op.create_index(
        "ix_auth_link_tokens_account_id",
        "auth_link_tokens",
        ["account_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_auth_link_tokens_account_id", table_name="auth_link_tokens")
    op.drop_index("ix_auth_link_tokens_provider_uid", table_name="auth_link_tokens")
    op.drop_table("auth_link_tokens")

    op.drop_index("ix_auth_accounts_account_id", table_name="auth_accounts")
    op.drop_table("auth_accounts")

    op.drop_index("ix_accounts_remnawave_user_uuid", table_name="accounts")
    op.drop_table("accounts")

    link_type_enum.drop(bind, checkfirst=True)
    auth_provider_enum.drop(bind, checkfirst=True)
    login_source_enum.drop(bind, checkfirst=True)
    account_status_enum.drop(bind, checkfirst=True)
