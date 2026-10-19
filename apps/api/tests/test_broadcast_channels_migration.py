import importlib.util
import unittest
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    JSON,
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    event,
    inspect,
    select,
)
from sqlalchemy.exc import IntegrityError


class BroadcastChannelsMigrationTests(unittest.TestCase):
    def setUp(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "alembic/versions/20260416_add_broadcast_audience_preset_channels.py"
        )
        spec = importlib.util.spec_from_file_location(
            "broadcast_channels_migration", path
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, "before_cursor_execute")
        def reject_unsupported_alter(
            connection, cursor, statement, parameters, context, executemany
        ):
            # Reproduce older SQLite even when local SQLite supports ALTER COLUMN.
            if (
                statement.lstrip().upper().startswith("ALTER TABLE")
                and "ALTER COLUMN" in statement.upper()
            ):
                raise AssertionError(
                    "SQLite-compatible migrations must not emit ALTER COLUMN"
                )

    def _check_upgrade(self, *, has_channels: bool, nullable: bool = True):
        metadata = MetaData()
        columns = [
            Column("id", Integer, primary_key=True),
            Column("name", String, nullable=False),
        ]
        if has_channels:
            columns.append(Column("channels", JSON, nullable=nullable))
        table = Table("broadcast_audience_presets", metadata, *columns)
        Index("ix_test_preset_name", table.c.name)
        with self.engine.begin() as connection:
            metadata.create_all(connection)
            if has_channels:
                connection.execute(
                    table.insert(),
                    [{"id": 1, "name": "Existing", "channels": ["telegram"]}],
                )
                if nullable:
                    # SQL NULL differs from JSON null in SQLAlchemy's JSON type.
                    connection.exec_driver_sql(
                        "INSERT INTO broadcast_audience_presets (id, name, channels) VALUES (2, 'Legacy', NULL)"
                    )
            else:
                connection.execute(table.insert(), [{"id": 1, "name": "Existing"}])
            with Operations.context(MigrationContext.configure(connection)):
                self.migration.upgrade()
                self.migration.upgrade()
            upgraded = Table(
                "broadcast_audience_presets", MetaData(), autoload_with=connection
            )
            rows = (
                connection.execute(select(upgraded).order_by(upgraded.c.id))
                .mappings()
                .all()
            )
            self.assertEqual(
                rows[0]["channels"], ["telegram"] if has_channels else ["in_app"]
            )
            if has_channels and nullable:
                self.assertEqual(rows[1]["channels"], ["in_app"])
            self.assertEqual(rows[0]["name"], "Existing")
            self.assertFalse(
                next(
                    c
                    for c in inspect(connection).get_columns(table.name)
                    if c["name"] == "channels"
                )["nullable"]
            )
            self.assertIn(
                "ix_test_preset_name",
                {i["name"] for i in inspect(connection).get_indexes(table.name)},
            )
            with self.assertRaises(IntegrityError):
                connection.exec_driver_sql(
                    "INSERT INTO broadcast_audience_presets (id, name, channels) VALUES (99, 'Invalid', NULL)"
                )

    def test_old_schema_gets_json_default_and_not_null_constraint(self):
        self._check_upgrade(has_channels=False)

    def test_nullable_channels_are_backfilled_without_losing_existing_values(self):
        self._check_upgrade(has_channels=True)

    def test_fresh_schema_does_not_need_alter_column(self):
        self._check_upgrade(has_channels=True, nullable=False)
