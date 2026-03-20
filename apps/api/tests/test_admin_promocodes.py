from __future__ import annotations

from datetime import UTC, datetime, timedelta
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    PromoCode,
    PromoEffectType,
    PromoRedemption,
    PromoRedemptionContext,
    PromoRedemptionStatus,
)
from app.db.session import get_session
from app.main import create_app
from app.services.admin_auth import create_admin
from app.services.i18n import translate


class DummyCache:
    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class AdminPromoEndpointsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "admin-promos.sqlite3"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_path}")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        import app.services.cache as cache_module
        import app.services.admin_auth as admin_auth_service

        self._cache_module = cache_module
        self._original_cache = cache_module._cache
        cache_module._cache = DummyCache()

        self._admin_auth_service = admin_auth_service
        self._original_bootstrap_username = (
            admin_auth_service.settings.admin_bootstrap_username
        )
        self._original_bootstrap_password = (
            admin_auth_service.settings.admin_bootstrap_password
        )
        self._original_bootstrap_email = (
            admin_auth_service.settings.admin_bootstrap_email
        )
        self._original_bootstrap_full_name = (
            admin_auth_service.settings.admin_bootstrap_full_name
        )
        admin_auth_service.settings.admin_bootstrap_username = ""
        admin_auth_service.settings.admin_bootstrap_password = ""
        admin_auth_service.settings.admin_bootstrap_email = ""
        admin_auth_service.settings.admin_bootstrap_full_name = ""

        self.app = create_app()

        async def override_get_session():
            async with self._session_factory() as session:
                yield session

        self.app.dependency_overrides[get_session] = override_get_session
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        self._cache_module._cache = self._original_cache
        self._admin_auth_service.settings.admin_bootstrap_username = (
            self._original_bootstrap_username
        )
        self._admin_auth_service.settings.admin_bootstrap_password = (
            self._original_bootstrap_password
        )
        self._admin_auth_service.settings.admin_bootstrap_email = (
            self._original_bootstrap_email
        )
        self._admin_auth_service.settings.admin_bootstrap_full_name = (
            self._original_bootstrap_full_name
        )
        await self._engine.dispose()
        self._tmpdir.cleanup()

    async def _create_admin_token(self) -> str:
        async with self._session_factory() as session:
            admin = await create_admin(
                session,
                username="root",
                password="secret-password",
                email="root@example.com",
                full_name="Root Admin",
            )
            await session.commit()
            await session.refresh(admin)

        response = await self.client.post(
            "/api/v1/admin/auth/login",
            json={"login": "root", "password": "secret-password"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    async def test_create_list_campaigns_and_codes(self) -> None:
        token = await self._create_admin_token()
        now = datetime.now(UTC)

        campaign_response = await self.client.post(
            "/api/v1/admin/promos/campaigns",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Spring Acquisition 2026",
                "description": "Discount for first purchase",
                "status": "active",
                "effect_type": "percent_discount",
                "effect_value": 20,
                "currency": "rub",
                "plan_codes": ["plan_1m", "plan_3m", "plan_1m"],
                "first_purchase_only": True,
                "requires_no_active_subscription": True,
                "starts_at": now.isoformat(),
                "ends_at": (now + timedelta(days=14)).isoformat(),
                "total_redemptions_limit": 200,
                "per_account_redemptions_limit": 1,
            },
        )

        self.assertEqual(campaign_response.status_code, 201)
        campaign_body = campaign_response.json()
        self.assertEqual(campaign_body["name"], "Spring Acquisition 2026")
        self.assertEqual(campaign_body["status"], "active")
        self.assertEqual(campaign_body["effect_type"], "percent_discount")
        self.assertEqual(campaign_body["currency"], "RUB")
        self.assertEqual(campaign_body["plan_codes"], ["plan_1m", "plan_3m"])
        self.assertEqual(campaign_body["codes_count"], 0)
        campaign_id = campaign_body["id"]

        campaigns_response = await self.client.get(
            "/api/v1/admin/promos/campaigns",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(campaigns_response.status_code, 200)
        campaigns_body = campaigns_response.json()
        self.assertEqual(campaigns_body["total"], 1)
        self.assertEqual(campaigns_body["items"][0]["id"], campaign_id)

        code_response = await self.client.post(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "code": " spring-20 ",
                "max_redemptions": 100,
                "is_active": True,
            },
        )
        self.assertEqual(code_response.status_code, 201)
        code_body = code_response.json()
        self.assertEqual(code_body["campaign_id"], campaign_id)
        self.assertEqual(code_body["code"], "SPRING-20")
        self.assertEqual(code_body["max_redemptions"], 100)
        self.assertEqual(code_body["redemptions_count"], 0)

        codes_response = await self.client.get(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(codes_response.status_code, 200)
        codes_body = codes_response.json()
        self.assertEqual(codes_body["total"], 1)
        self.assertEqual(codes_body["items"][0]["code"], "SPRING-20")

    async def test_create_campaign_rejects_conflicting_subscription_rules(self) -> None:
        token = await self._create_admin_token()

        response = await self.client.post(
            "/api/v1/admin/promos/campaigns",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Broken Rule Set",
                "status": "active",
                "effect_type": "extra_days",
                "effect_value": 7,
                "requires_active_subscription": True,
                "requires_no_active_subscription": True,
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {
                "detail": translate("api.admin.errors.promo_validation_failed"),
                "error_code": "admin_promo_validation_failed",
            },
        )

    async def test_create_code_rejects_invalid_characters_with_error_code(self) -> None:
        token = await self._create_admin_token()

        campaign_response = await self.client.post(
            "/api/v1/admin/promos/campaigns",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Invalid code payload",
                "status": "active",
                "effect_type": "balance_credit",
                "effect_value": 300,
            },
        )
        self.assertEqual(campaign_response.status_code, 201)
        campaign_id = campaign_response.json()["id"]

        response = await self.client.post(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes",
            headers={"Authorization": f"Bearer {token}"},
            json={"code": "bad promo!*"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {
                "detail": translate("api.admin.errors.promo_validation_failed"),
                "error_code": "admin_promo_validation_failed",
            },
        )

    async def test_create_code_rejects_duplicate_normalized_value(self) -> None:
        token = await self._create_admin_token()

        campaign_response = await self.client.post(
            "/api/v1/admin/promos/campaigns",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Balance Bonus",
                "status": "active",
                "effect_type": "balance_credit",
                "effect_value": 300,
            },
        )
        self.assertEqual(campaign_response.status_code, 201)
        campaign_id = campaign_response.json()["id"]

        first_code_response = await self.client.post(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes",
            headers={"Authorization": f"Bearer {token}"},
            json={"code": "bonus-300"},
        )
        self.assertEqual(first_code_response.status_code, 201)

        duplicate_code_response = await self.client.post(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes",
            headers={"Authorization": f"Bearer {token}"},
            json={"code": " BONUS-300 "},
        )
        self.assertEqual(duplicate_code_response.status_code, 409)
        self.assertEqual(
            duplicate_code_response.json(),
            {
                "detail": translate("api.admin.errors.promo_code_conflict"),
                "error_code": "admin_promo_code_conflict",
            },
        )

    async def test_update_campaign_changes_status_effect_and_limits(self) -> None:
        token = await self._create_admin_token()
        campaign_response = await self.client.post(
            "/api/v1/admin/promos/campaigns",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Spring Reactivation",
                "status": "draft",
                "effect_type": "percent_discount",
                "effect_value": 15,
                "plan_codes": ["plan_1m"],
            },
        )
        self.assertEqual(campaign_response.status_code, 201)
        campaign_id = campaign_response.json()["id"]

        update_response = await self.client.put(
            f"/api/v1/admin/promos/campaigns/{campaign_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Spring Reactivation Updated",
                "description": "retention campaign",
                "status": "archived",
                "effect_type": "extra_days",
                "effect_value": 10,
                "currency": "rub",
                "plan_codes": ["plan_1m", "plan_3m"],
                "first_purchase_only": False,
                "requires_active_subscription": True,
                "requires_no_active_subscription": False,
                "total_redemptions_limit": 100,
                "per_account_redemptions_limit": 2,
            },
        )
        self.assertEqual(update_response.status_code, 200)
        updated_body = update_response.json()
        self.assertEqual(updated_body["name"], "Spring Reactivation Updated")
        self.assertEqual(updated_body["status"], "archived")
        self.assertEqual(updated_body["effect_type"], "extra_days")
        self.assertEqual(updated_body["effect_value"], 10)
        self.assertEqual(updated_body["currency"], "RUB")
        self.assertEqual(updated_body["plan_codes"], ["plan_1m", "plan_3m"])
        self.assertTrue(updated_body["requires_active_subscription"])
        self.assertEqual(updated_body["total_redemptions_limit"], 100)
        self.assertEqual(updated_body["per_account_redemptions_limit"], 2)

    async def test_update_code_toggles_activity_and_clears_limit(self) -> None:
        token = await self._create_admin_token()
        campaign_response = await self.client.post(
            "/api/v1/admin/promos/campaigns",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Partner Distribution",
                "status": "active",
                "effect_type": "fixed_discount",
                "effect_value": 250,
            },
        )
        self.assertEqual(campaign_response.status_code, 201)
        campaign_id = campaign_response.json()["id"]

        code_response = await self.client.post(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "code": "PARTNER-250",
                "max_redemptions": 50,
                "is_active": True,
            },
        )
        self.assertEqual(code_response.status_code, 201)
        code_id = code_response.json()["id"]

        update_response = await self.client.put(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes/{code_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "max_redemptions": None,
                "assigned_account_id": None,
                "is_active": False,
            },
        )
        self.assertEqual(update_response.status_code, 200)
        updated_body = update_response.json()
        self.assertFalse(updated_body["is_active"])
        self.assertIsNone(updated_body["max_redemptions"])

        codes_response = await self.client.get(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(codes_response.status_code, 200)
        listed_code = codes_response.json()["items"][0]
        self.assertFalse(listed_code["is_active"])
        self.assertIsNone(listed_code["max_redemptions"])

    async def test_batch_generate_codes_and_list_redemptions(self) -> None:
        token = await self._create_admin_token()
        campaign_response = await self.client.post(
            "/api/v1/admin/promos/campaigns",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Winback Batch",
                "status": "active",
                "effect_type": "fixed_price",
                "effect_value": 99,
            },
        )
        self.assertEqual(campaign_response.status_code, 201)
        campaign_id = campaign_response.json()["id"]

        batch_response = await self.client.post(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes/batch",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "quantity": 4,
                "prefix": "WINBACK",
                "suffix_length": 6,
                "max_redemptions": 1,
                "is_active": True,
            },
        )
        self.assertEqual(batch_response.status_code, 201)
        batch_body = batch_response.json()
        self.assertEqual(batch_body["created_count"], 4)
        self.assertEqual(len(batch_body["items"]), 4)
        generated_codes = [item["code"] for item in batch_body["items"]]
        self.assertEqual(len(set(generated_codes)), 4)
        self.assertTrue(all(code.startswith("WINBACK-") for code in generated_codes))

        async with self._session_factory() as session:
            code_rows = (
                (
                    await session.execute(
                        PromoCode.__table__.select().where(
                            PromoCode.campaign_id == campaign_id
                        )
                    )
                )
                .mappings()
                .all()
            )
            first_code_id = int(code_rows[0]["id"])
            first_code_value = str(code_rows[0]["code"])
            second_code_id = int(code_rows[1]["id"])
            first_account_id = uuid4()
            second_account_id = uuid4()
            now = datetime.now(UTC)
            session.add_all(
                [
                    PromoRedemption(
                        campaign_id=campaign_id,
                        promo_code_id=first_code_id,
                        account_id=first_account_id,
                        status=PromoRedemptionStatus.APPLIED,
                        redemption_context=PromoRedemptionContext.PLAN_PURCHASE,
                        plan_code="plan_1m",
                        effect_type=PromoEffectType.FIXED_PRICE,
                        effect_value=99,
                        currency="RUB",
                        original_amount=299,
                        discount_amount=200,
                        final_amount=99,
                        reference_type="payment",
                        reference_id="payment-1",
                        created_at=now,
                        applied_at=now,
                    ),
                    PromoRedemption(
                        campaign_id=campaign_id,
                        promo_code_id=second_code_id,
                        account_id=second_account_id,
                        status=PromoRedemptionStatus.REJECTED,
                        redemption_context=PromoRedemptionContext.DIRECT,
                        effect_type=PromoEffectType.FIXED_PRICE,
                        effect_value=99,
                        currency="RUB",
                        failure_reason="promo campaign is disabled",
                        reference_type="redeem",
                        reference_id="redeem-2",
                        created_at=now,
                    ),
                ]
            )
            await session.commit()

        redemptions_response = await self.client.get(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/redemptions",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(redemptions_response.status_code, 200)
        redemptions_body = redemptions_response.json()
        self.assertEqual(redemptions_body["total"], 2)
        self.assertEqual(redemptions_body["items"][0]["campaign_id"], campaign_id)
        self.assertIn(redemptions_body["items"][0]["promo_code"], generated_codes)

        filtered_response = await self.client.get(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/redemptions?status=applied",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(filtered_response.status_code, 200)
        filtered_body = filtered_response.json()
        self.assertEqual(filtered_body["total"], 1)
        self.assertEqual(filtered_body["items"][0]["status"], "applied")

        context_response = await self.client.get(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/redemptions?redemption_context=direct",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(context_response.status_code, 200)
        context_body = context_response.json()
        self.assertEqual(context_body["total"], 1)
        self.assertEqual(context_body["items"][0]["redemption_context"], "direct")

        code_query_response = await self.client.get(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/redemptions?code_query={first_code_value}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(code_query_response.status_code, 200)
        code_query_body = code_query_response.json()
        self.assertEqual(code_query_body["total"], 1)
        self.assertEqual(code_query_body["items"][0]["promo_code"], first_code_value)

        account_response = await self.client.get(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/redemptions?account_id={first_account_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(account_response.status_code, 200)
        account_body = account_response.json()
        self.assertEqual(account_body["total"], 1)
        self.assertEqual(account_body["items"][0]["account_id"], str(first_account_id))

        invalid_account_response = await self.client.get(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/redemptions?account_id=not-a-uuid",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(invalid_account_response.status_code, 422)
        self.assertEqual(
            invalid_account_response.json(),
            {
                "detail": translate("api.admin.errors.promo_invalid_account_id"),
                "error_code": "admin_promo_invalid_account_id",
            },
        )

    async def test_import_and_export_promo_codes(self) -> None:
        token = await self._create_admin_token()
        campaign_response = await self.client.post(
            "/api/v1/admin/promos/campaigns",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Affiliate Import",
                "status": "active",
                "effect_type": "percent_discount",
                "effect_value": 25,
            },
        )
        self.assertEqual(campaign_response.status_code, 201)
        campaign_id = campaign_response.json()["id"]

        existing_code_response = await self.client.post(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes",
            headers={"Authorization": f"Bearer {token}"},
            json={"code": "AFF-EXISTING"},
        )
        self.assertEqual(existing_code_response.status_code, 201)

        import_response = await self.client.post(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes/import",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "codes_text": "aff-existing\nAFF-NEW-1, aff-new-2; aff-new-1",
                "max_redemptions": 1,
                "is_active": True,
                "skip_duplicates": True,
            },
        )
        self.assertEqual(import_response.status_code, 201)
        import_body = import_response.json()
        self.assertEqual(import_body["created_count"], 2)
        self.assertEqual(import_body["skipped_count"], 1)
        self.assertEqual(import_body["skipped_codes"], ["AFF-EXISTING"])
        self.assertEqual(
            sorted(item["code"] for item in import_body["items"]),
            ["AFF-NEW-1", "AFF-NEW-2"],
        )

        export_response = await self.client.get(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(export_response.status_code, 200)
        export_body = export_response.json()
        self.assertEqual(export_body["exported_count"], 3)
        self.assertEqual(
            sorted(item["code"] for item in export_body["items"]),
            ["AFF-EXISTING", "AFF-NEW-1", "AFF-NEW-2"],
        )

        conflict_response = await self.client.post(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes/import",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "codes_text": "AFF-NEW-3\nAFF-NEW-1",
                "skip_duplicates": False,
            },
        )
        self.assertEqual(conflict_response.status_code, 409)
        self.assertEqual(
            conflict_response.json(),
            {
                "detail": translate("api.admin.errors.promo_import_conflict"),
                "error_code": "admin_promo_import_conflict",
            },
        )

    async def test_read_codes_returns_error_code_when_campaign_missing(self) -> None:
        token = await self._create_admin_token()

        response = await self.client.get(
            "/api/v1/admin/promos/campaigns/999999/codes",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {
                "detail": translate("api.admin.errors.promo_campaign_not_found"),
                "error_code": "admin_promo_campaign_not_found",
            },
        )

    async def test_update_code_returns_error_code_when_code_missing(self) -> None:
        token = await self._create_admin_token()
        campaign_response = await self.client.post(
            "/api/v1/admin/promos/campaigns",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Missing code target",
                "status": "active",
                "effect_type": "fixed_discount",
                "effect_value": 250,
            },
        )
        self.assertEqual(campaign_response.status_code, 201)
        campaign_id = campaign_response.json()["id"]

        response = await self.client.put(
            f"/api/v1/admin/promos/campaigns/{campaign_id}/codes/999999",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "max_redemptions": None,
                "assigned_account_id": None,
                "is_active": False,
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {
                "detail": translate("api.admin.errors.promo_code_not_found"),
                "error_code": "admin_promo_code_not_found",
            },
        )
