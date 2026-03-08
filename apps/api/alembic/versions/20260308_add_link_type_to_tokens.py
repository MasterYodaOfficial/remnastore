"""add link_type to auth_link_tokens

Revision ID: 20260308_add_link_type_to_tokens
Revises: 20260307_add_supabase_provider
Create Date: 2026-03-08
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260308_add_link_type_to_tokens"
down_revision = "20260307_add_supabase_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type for link type
    sa.Enum("telegram_from_browser", "browser_from_telegram", name="linktype").create(
        op.get_bind(), checkfirst=True
    )
    
    # Add column to auth_link_tokens
    op.add_column(
        "auth_link_tokens",
        sa.Column(
            "link_type",
            sa.Enum("telegram_from_browser", "browser_from_telegram", name="linktype"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("auth_link_tokens", "link_type")
    op.execute("DROP TYPE IF EXISTS linktype")
