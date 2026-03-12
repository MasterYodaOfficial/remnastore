"""add admins

Revision ID: 20260312_add_admins
Revises: 20260312_add_notifications
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260312_add_admins"
down_revision = "20260312_add_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admins_username", "admins", ["username"], unique=True)
    op.create_index("ix_admins_email", "admins", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_admins_email", table_name="admins")
    op.drop_index("ix_admins_username", table_name="admins")
    op.drop_table("admins")
