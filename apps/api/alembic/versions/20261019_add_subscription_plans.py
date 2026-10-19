"""Store the subscription catalog in the database.

Revision ID: 20261019_subscription_plans
Revises: 20260423_broadcast_tg_copy
Create Date: 2026-10-19
"""

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "20261019_subscription_plans"
down_revision = "20260423_broadcast_tg_copy"
branch_labels = None
depends_on = None

# Read the old catalog once, preserving prices edited before this upgrade.
LEGACY_CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "config" / "subscription-plans.json"
)


def _load_legacy_catalog() -> list[dict]:
    payload = json.loads(LEGACY_CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("The legacy subscription catalog must be a non-empty list")
    rows = []
    codes = set()
    for index, item in enumerate(payload):
        code = item["code"].strip()
        name = item["name"].strip()
        features = item["features"]
        if (
            not code
            or len(code) > 64
            or code in codes
            or not name
            or len(name) > 255
            or not isinstance(features, list)
            or not features
            or not all(isinstance(value, str) and value.strip() for value in features)
        ):
            raise ValueError(f"Invalid legacy subscription plan at index {index}")
        codes.add(code)
        rows.append(
            {
                "code": code,
                "name": name,
                "price_rub": item["price_rub"],
                "price_stars": item.get("price_stars"),
                "duration_days": item["duration_days"],
                "features": [value.strip() for value in features],
                "device_limit": item.get("device_limit"),
                "popular": bool(item.get("popular", False)),
                "sort_order": index,
            }
        )
    return rows


def upgrade() -> None:
    bind = op.get_bind()
    # The initial revision uses current Base.metadata on fresh installations.
    if sa.inspect(bind).has_table("subscription_plans"):
        table = sa.Table("subscription_plans", sa.MetaData(), autoload_with=bind)
        if bind.scalar(sa.select(sa.func.count()).select_from(table)):
            return
        op.bulk_insert(table, _load_legacy_catalog())
        return
    rows = _load_legacy_catalog()
    table = op.create_table(
        "subscription_plans",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("price_rub", sa.BigInteger(), nullable=False),
        sa.Column("price_stars", sa.BigInteger(), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("device_limit", sa.Integer(), nullable=True),
        sa.Column("popular", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("price_rub > 0", name="ck_subscription_plans_price_rub"),
        sa.CheckConstraint(
            "price_stars IS NULL OR price_stars > 0",
            name="ck_subscription_plans_price_stars",
        ),
        sa.CheckConstraint("duration_days > 0", name="ck_subscription_plans_duration"),
        sa.CheckConstraint(
            "device_limit IS NULL OR device_limit >= 0",
            name="ck_subscription_plans_device_limit",
        ),
    )
    op.bulk_insert(table, rows)


def downgrade() -> None:
    op.drop_table("subscription_plans")
