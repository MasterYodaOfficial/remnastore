from __future__ import annotations

import tempfile
import unittest
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_account
from app.db.base import Base
from app.db.models import Account
from app.db.session import get_session
from app.integrations.remnawave.client import (
    RemnawaveRequestError,
    RemnawaveSubscriptionAccess,
)
from app.main import create_app
from app.services import subscription_access as subscription_access_service


class DummyCache:
    def __init__(self) -> None:
        self._json_values: dict[str, dict] = {}

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def subscription_access_key(self, account_id: str) -> str:
        return f"subscription-access:{account_id}"

    async def get_json(self, key: str):
        return self._json_values.get(key)

    async def set_json(self, key: str, value, ttl_seconds: int) -> None:
        del ttl_seconds
        self._json_values[key] = value

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._json_values.pop(key, None)


@dataclass
class FakeSubscriptionGateway:
    snapshots: dict[uuid.UUID, RemnawaveSubscriptionAccess]

    async def get_subscription_access_by_uuid(
        self,
        user_uuid: uuid.UUID,
    ) -> RemnawaveSubscriptionAccess | None:
        return self.snapshots.get(user_uuid)


class UnavailableSubscriptionGateway:
    async def get_subscription_access_by_uuid(
        self,
        user_uuid: uuid.UUID,
    ) -> RemnawaveSubscriptionAccess | None:
        del user_uuid
        raise RemnawaveRequestError("ConnectError")


class SubscriptionAccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "subscription-access.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._current_account_id: uuid.UUID | None = None

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()

        self._original_gateway_factory = subscription_access_service.get_remnawave_gateway

        self.app = create_app()

        async def override_get_session():
            async with self._session_factory() as session:
                yield session

        async def override_get_current_account():
            if self._current_account_id is None:
                raise AssertionError("current account is not configured")

            async with self._session_factory() as session:
                account = await session.get(Account, self._current_account_id)
                if account is None:
                    raise AssertionError(f"account not found: {self._current_account_id}")
                return account

        self.app.dependency_overrides[get_session] = override_get_session
        self.app.dependency_overrides[get_current_account] = override_get_current_account
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        subscription_access_service.get_remnawave_gateway = self._original_gateway_factory
        self._cache_module._cache = self._original_cache
        await self._engine.dispose()
        self._tmpdir.cleanup()

    async def _create_account(self, **values) -> Account:
        async with self._session_factory() as session:
            account = Account(**values)
            session.add(account)
            await session.commit()
            await session.refresh(account)
            return account

    async def test_subscription_access_returns_remote_snapshot_and_then_cache(self) -> None:
        account = await self._create_account(email="access@example.com")
        self._current_account_id = account.id

        remote_snapshot = RemnawaveSubscriptionAccess(
            user_uuid=account.id,
            short_uuid="abc12345",
            username="acc_test",
            status="ACTIVE",
            user_status="ACTIVE",
            is_active=True,
            expires_at=datetime.now(UTC) + timedelta(days=12),
            days_left=12,
            subscription_url="https://panel.test/sub/abc12345",
            links=[
                "vless://test-one#RU%20Moscow",
                "vmess://test-two#DE%20Berlin",
            ],
            ssconf_links={"shadowrocket": "https://panel.test/ssconf"},
            traffic_used_bytes=1024,
            traffic_limit_bytes=2048,
            lifetime_traffic_used_bytes=4096,
        )
        subscription_access_service.get_remnawave_gateway = lambda: FakeSubscriptionGateway(
            snapshots={account.id: remote_snapshot}
        )

        response = await self.client.get("/api/v1/subscriptions/access")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "remote")
        self.assertTrue(body["available"])
        self.assertEqual(body["short_uuid"], "abc12345")
        self.assertEqual(len(body["links"]), 2)
        self.assertEqual(body["ssconf_links"]["shadowrocket"], "https://panel.test/ssconf")

        subscription_access_service.get_remnawave_gateway = lambda: UnavailableSubscriptionGateway()
        cached_response = await self.client.get("/api/v1/subscriptions/access")
        self.assertEqual(cached_response.status_code, 200)
        cached_body = cached_response.json()
        self.assertEqual(cached_body["source"], "cache")
        self.assertEqual(cached_body["subscription_url"], "https://panel.test/sub/abc12345")
        self.assertEqual(cached_body["links"], body["links"])

    async def test_subscription_access_uses_local_fallback_when_remote_unavailable(self) -> None:
        expires_at = datetime.now(UTC) + timedelta(days=5)
        account = await self._create_account(
            email="fallback@example.com",
            subscription_url="https://panel.test/sub/local123",
            subscription_status="ACTIVE",
            subscription_expires_at=expires_at,
        )
        self._current_account_id = account.id
        subscription_access_service.get_remnawave_gateway = lambda: UnavailableSubscriptionGateway()

        response = await self.client.get("/api/v1/subscriptions/access")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "local_fallback")
        self.assertTrue(body["available"])
        self.assertEqual(body["subscription_url"], "https://panel.test/sub/local123")
        self.assertTrue(body["is_active"])

    async def test_subscription_access_returns_none_when_no_remote_or_local_snapshot(self) -> None:
        account = await self._create_account(email="empty@example.com")
        self._current_account_id = account.id
        subscription_access_service.get_remnawave_gateway = lambda: UnavailableSubscriptionGateway()

        response = await self.client.get("/api/v1/subscriptions/access")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "none")
        self.assertFalse(body["available"])
        self.assertEqual(body["links"], [])
