import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import MetaData, Table, create_engine, inspect, select

from app.db.models import SubscriptionPlanRecord
from app.core.config import settings


class SubscriptionPlanMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.catalog_path = Path(self._tmpdir.name) / "plans.json"
        self.catalog = [
            {
                "code": "custom_plan",
                "name": "Мой тариф",
                "price_rub": 321,
                "price_stars": 123,
                "duration_days": 42,
                "features": ["Все серверы", "Поддержка"],
                "device_limit": 8,
                "popular": True,
            },
            {
                "code": "second_plan",
                "name": "Второй тариф",
                "price_rub": 99,
                "duration_days": 7,
                "features": ["Доступ"],
            },
        ]
        self.catalog_path.write_text(json.dumps(self.catalog), encoding="utf-8")
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "alembic/versions/20261019_add_subscription_plans.py"
        )
        spec = importlib.util.spec_from_file_location("plan_migration", migration_path)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        catalog_patch = patch.object(
            self.migration, "LEGACY_CATALOG_PATH", self.catalog_path
        )
        catalog_patch.start()
        self.addCleanup(catalog_patch.stop)
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)

    def test_upgrade_preserves_custom_catalog_and_order(self) -> None:
        with self.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                self.migration.upgrade()
            rows = (
                connection.execute(
                    select(
                        Table(
                            "subscription_plans", MetaData(), autoload_with=connection
                        )
                    ).order_by(SubscriptionPlanRecord.sort_order)
                )
                .mappings()
                .all()
            )
            self.assertEqual(len(rows), 2)
            for original, row in zip(self.catalog, rows, strict=True):
                for key, value in original.items():
                    self.assertEqual(row[key], value)
            self.assertIsNone(rows[1]["price_stars"])
            self.assertIsNone(rows[1]["device_limit"])
            self.assertFalse(rows[1]["popular"])

    def test_fresh_schema_is_seeded_and_existing_catalog_is_not_overwritten(
        self,
    ) -> None:
        with self.engine.begin() as connection:
            SubscriptionPlanRecord.__table__.create(connection)
            with Operations.context(MigrationContext.configure(connection)):
                self.migration.upgrade()
                connection.execute(
                    SubscriptionPlanRecord.__table__.update()
                    .where(SubscriptionPlanRecord.code == "custom_plan")
                    .values(price_rub=777)
                )
                self.catalog_path.unlink()
                self.migration.upgrade()
            self.assertEqual(
                connection.scalar(
                    select(SubscriptionPlanRecord.price_rub).where(
                        SubscriptionPlanRecord.code == "custom_plan"
                    )
                ),
                777,
            )

    def test_duplicate_codes_fail_before_creating_table(self) -> None:
        self.catalog_path.write_text(
            json.dumps([self.catalog[0], self.catalog[0]]), encoding="utf-8"
        )
        with self.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                with self.assertRaises(ValueError):
                    self.migration.upgrade()
            self.assertFalse(inspect(connection).has_table("subscription_plans"))

    def test_downgrade_removes_table(self) -> None:
        with self.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                self.migration.upgrade()
                self.migration.downgrade()
            self.assertFalse(inspect(connection).has_table("subscription_plans"))

    def test_full_alembic_chain_seeds_once_on_fresh_install(self) -> None:
        database_path = Path(self._tmpdir.name) / "fresh.sqlite3"
        api_root = Path(__file__).resolve().parents[1]
        config = Config(str(api_root.parents[1] / "alembic.ini"))
        config.set_main_option("script_location", str(api_root / "alembic"))
        with patch.object(
            settings, "database_url", f"sqlite+aiosqlite:///{database_path}"
        ):
            command.upgrade(config, "head")
            engine = create_engine(f"sqlite:///{database_path}")
            try:
                with engine.begin() as connection:
                    self.assertEqual(
                        connection.scalar(
                            select(SubscriptionPlanRecord.price_rub).where(
                                SubscriptionPlanRecord.code == "plan_1m"
                            )
                        ),
                        199,
                    )
                    connection.execute(
                        SubscriptionPlanRecord.__table__.update()
                        .where(SubscriptionPlanRecord.code == "plan_1m")
                        .values(price_rub=999)
                    )
                command.upgrade(config, "head")
                with engine.connect() as connection:
                    self.assertEqual(
                        connection.scalar(
                            select(SubscriptionPlanRecord.price_rub).where(
                                SubscriptionPlanRecord.code == "plan_1m"
                            )
                        ),
                        999,
                    )
            finally:
                engine.dispose()
