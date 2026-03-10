"""expand payment identifier columns

Revision ID: 20260311_expand_payment_ids
Revises: 20260311_expand_payment_urls
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_expand_payment_ids"
down_revision = "20260311_expand_payment_urls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "payments",
        "provider_payment_id",
        existing_type=sa.String(length=128),
        type_=sa.Text(),
    )
    op.alter_column(
        "payment_events",
        "provider_event_id",
        existing_type=sa.String(length=128),
        type_=sa.Text(),
    )
    op.alter_column(
        "payment_events",
        "provider_payment_id",
        existing_type=sa.String(length=128),
        type_=sa.Text(),
    )


def downgrade() -> None:
    op.alter_column(
        "payment_events",
        "provider_payment_id",
        existing_type=sa.Text(),
        type_=sa.String(length=128),
    )
    op.alter_column(
        "payment_events",
        "provider_event_id",
        existing_type=sa.Text(),
        type_=sa.String(length=128),
    )
    op.alter_column(
        "payments",
        "provider_payment_id",
        existing_type=sa.Text(),
        type_=sa.String(length=128),
    )
