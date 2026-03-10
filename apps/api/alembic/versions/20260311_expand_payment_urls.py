"""expand payment url columns

Revision ID: 20260311_expand_payment_urls
Revises: 20260311_add_subscription_grants
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_expand_payment_urls"
down_revision = "20260311_add_subscription_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("payments", "success_url", existing_type=sa.String(length=512), type_=sa.Text())
    op.alter_column("payments", "cancel_url", existing_type=sa.String(length=512), type_=sa.Text())
    op.alter_column(
        "payments",
        "confirmation_url",
        existing_type=sa.String(length=1024),
        type_=sa.Text(),
    )


def downgrade() -> None:
    op.alter_column(
        "payments",
        "confirmation_url",
        existing_type=sa.Text(),
        type_=sa.String(length=1024),
    )
    op.alter_column("payments", "cancel_url", existing_type=sa.Text(), type_=sa.String(length=512))
    op.alter_column("payments", "success_url", existing_type=sa.Text(), type_=sa.String(length=512))
