"""add supabase auth provider

Revision ID: 20260307_add_supabase_provider
Revises: 20260303_add_balance_referrals
Create Date: 2026-03-07
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260307_add_supabase_provider"
down_revision = "20260303_add_balance_referrals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE authprovider ADD VALUE IF NOT EXISTS 'supabase'")


def downgrade() -> None:
    bind = op.get_bind()

    op.execute("DELETE FROM auth_link_tokens WHERE provider = 'supabase'")
    op.execute("DELETE FROM auth_accounts WHERE provider = 'supabase'")
    op.execute("ALTER TYPE authprovider RENAME TO authprovider_old")

    auth_provider_enum = sa.Enum("google", "yandex", "vk", name="authprovider")
    auth_provider_enum.create(bind, checkfirst=False)

    op.execute(
        "ALTER TABLE auth_accounts "
        "ALTER COLUMN provider TYPE authprovider "
        "USING provider::text::authprovider"
    )
    op.execute(
        "ALTER TABLE auth_link_tokens "
        "ALTER COLUMN provider TYPE authprovider "
        "USING provider::text::authprovider"
    )
    op.execute("DROP TYPE authprovider_old")
