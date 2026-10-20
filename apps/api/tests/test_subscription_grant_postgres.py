"""Exercise the asyncpg timestamp codec that SQLite cannot validate."""

import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.schema import CreateSchema

from app.db.base import Base
from app.db.models import Payment, SubscriptionGrant


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not set")
class SubscriptionGrantPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def test_paid_grant_insert_preserves_timestamp_contract(self):
        engine = create_async_engine(os.environ["TEST_POSTGRES_URL"])
        schema = "remnastore_test_" + uuid.uuid4().hex
        try:
            async with engine.connect() as connection:
                # The isolated schema, tables and rows are all rolled back.
                async with connection.begin() as transaction:
                    await connection.execute(CreateSchema(schema))
                    connection = await connection.execution_options(
                        schema_translate_map={None: schema}
                    )
                    await connection.run_sync(
                        lambda conn: Base.metadata.create_all(
                            conn,
                            tables=[Payment.__table__, SubscriptionGrant.__table__],
                        )
                    )
                    start = datetime.now(UTC)
                    end = start + timedelta(days=180)
                    async with AsyncSession(bind=connection) as session:
                        grant = SubscriptionGrant(
                            account_id=uuid.uuid4(),
                            purchase_source="direct_payment",
                            reference_type="payment",
                            reference_id="263-regression",
                            plan_code="plan_6m",
                            amount=990,
                            currency="RUB",
                            duration_days=180,
                            base_expires_at=start,
                            target_expires_at=end,
                        )
                        session.add(grant)
                        # Before the fix, asyncpg rejects the aware created_at
                        # value here with "can't subtract ... datetimes".
                        await session.flush()
                        await session.refresh(grant)
                        self.assertIsNotNone(grant.id)
                        self.assertIsNone(grant.created_at.tzinfo)
                        self.assertGreaterEqual(
                            grant.created_at, start.replace(tzinfo=None)
                        )
                        self.assertLessEqual(
                            grant.created_at, datetime.now(UTC).replace(tzinfo=None)
                        )
                        self.assertEqual(grant.base_expires_at, start)
                        self.assertEqual(grant.target_expires_at, end)
                        grant.applied_at = datetime.now(UTC)
                        await session.flush()
                        await session.refresh(grant)
                        self.assertIsNotNone(grant.applied_at.tzinfo)
                        self.assertEqual(
                            await session.scalar(select(SubscriptionGrant.id)), grant.id
                        )
                    await transaction.rollback()
        finally:
            await engine.dispose()
