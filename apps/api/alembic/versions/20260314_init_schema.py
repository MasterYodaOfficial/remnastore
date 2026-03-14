"""initialize current development schema

Revision ID: 20260314_init_schema
Revises:
Create Date: 2026-03-14
"""

from app.db.base import Base
import app.db.models  # noqa: F401
from alembic import op


revision = "20260314_init_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
