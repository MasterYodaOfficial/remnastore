import importlib.util
import unittest
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.db.models import SubscriptionPlanRecord


class DeviceMigrationTests(unittest.TestCase):
    def test_upgrade_existing_schema_keeps_catalog_and_downgrade_keeps_base_tables(
        self,
    ):
        path = (
            Path(__file__).resolve().parents[1]
            / "alembic/versions/20261019_add_hwid_devices.py"
        )
        spec = importlib.util.spec_from_file_location("device_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            SubscriptionPlanRecord.metadata.create_all(connection)
            for name in (
                "device_prepayments",
                "device_purchases",
                "device_pricing_periods",
                "account_device_settings",
            ):
                connection.execute(text(f"DROP TABLE {name}"))
            connection.execute(
                text("ALTER TABLE subscription_grants DROP COLUMN device_metadata")
            )
            connection.execute(
                text(
                    "ALTER TABLE subscription_plans DROP COLUMN extra_device_price_rub"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO subscription_plans (code, name, price_rub, duration_days, features, popular, sort_order) VALUES ('existing', 'Existing', 777, 30, '[]', 0, 0)"
                )
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT price_rub FROM subscription_plans WHERE code='existing'"
                    )
                ),
                777,
            )
            self.assertIsNone(
                connection.scalar(
                    text(
                        "SELECT extra_device_price_rub FROM subscription_plans WHERE code='existing'"
                    )
                )
            )
            self.assertTrue(inspect(connection).has_table("device_purchases"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
            self.assertFalse(inspect(connection).has_table("device_purchases"))
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT price_rub FROM subscription_plans WHERE code='existing'"
                    )
                ),
                777,
            )
