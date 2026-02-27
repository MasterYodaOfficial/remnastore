"""create accounts and auth link tables

Revision ID: 20260227_create_accounts
Revises: 
Create Date: 2026-02-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260227_create_accounts"
down_revision = None
branch_labels = None
depends_on = None


account_status_enum = sa.Enum("active", "blocked", name="accountstatus")
login_source_enum = sa.Enum(
    "telegram_webapp", "telegram_bot_start", "browser_oauth", name="loginsource"
)
auth_provider_enum = sa.Enum("google", "yandex", "vk", name="authprovider")


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=64), nullable=True),
        sa.Column("last_name", sa.String(length=64), nullable=True),
        sa.Column("is_premium", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("locale", sa.String(length=16), nullable=True),
        sa.Column("remnawave_user_uuid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subscription_url", sa.String(length=512), nullable=True),
        sa.Column(
            "status",
            account_status_enum,
            nullable=False,
            server_default=sa.text("'active'::accountstatus"),
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
        "ix_auth_accounts_account_id", "auth_accounts", ["account_id"], unique=False
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
    op.drop_index("ix_auth_link_tokens_account_id", table_name="auth_link_tokens")
    op.drop_index("ix_auth_link_tokens_provider_uid", table_name="auth_link_tokens")
    op.drop_table("auth_link_tokens")

    op.drop_index("ix_auth_accounts_account_id", table_name="auth_accounts")
    op.drop_table("auth_accounts")

    op.drop_index("ix_accounts_remnawave_user_uuid", table_name="accounts")
    op.drop_table("accounts")

    auth_provider_enum.drop(op.get_bind(), checkfirst=False)
    login_source_enum.drop(op.get_bind(), checkfirst=False)
    account_status_enum.drop(op.get_bind(), checkfirst=False)
