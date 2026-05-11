import unittest
import uuid
from unittest.mock import patch

from app.db.models import PromoEffectType, PromoRedemption
from app.services.promos import (
    PromoConflictError,
    PromoValidationError,
    _compute_discounted_amount,
    _validate_existing_redemption,
    normalize_promo_code,
    resolve_plan_checkout_amount,
)


class PromoLogicUnitTests(unittest.TestCase):
    def test_normalize_promo_code_trims_and_uppercases(self) -> None:
        self.assertEqual(normalize_promo_code(" spring20 "), "SPRING20")

    def test_normalize_promo_code_rejects_blank_input(self) -> None:
        with self.assertRaises(PromoValidationError) as captured:
            normalize_promo_code("   ")

        self.assertEqual(captured.exception.code, "code_required")

    def test_compute_discounted_amount_supports_core_discount_modes(self) -> None:
        self.assertEqual(
            _compute_discounted_amount(
                effect_type=PromoEffectType.PERCENT_DISCOUNT,
                effect_value=25,
                base_amount=1000,
                currency="RUB",
                campaign_currency="RUB",
            ),
            (750, 250),
        )
        self.assertEqual(
            _compute_discounted_amount(
                effect_type=PromoEffectType.FIXED_DISCOUNT,
                effect_value=150,
                base_amount=1000,
                currency="RUB",
                campaign_currency="RUB",
            ),
            (850, 150),
        )
        self.assertEqual(
            _compute_discounted_amount(
                effect_type=PromoEffectType.FIXED_PRICE,
                effect_value=700,
                base_amount=1000,
                currency="RUB",
                campaign_currency="RUB",
            ),
            (700, 300),
        )

    def test_compute_discounted_amount_rejects_invalid_currency_or_price(self) -> None:
        with self.assertRaises(PromoValidationError) as captured:
            _compute_discounted_amount(
                effect_type=PromoEffectType.FIXED_DISCOUNT,
                effect_value=100,
                base_amount=1000,
                currency="XTR",
                campaign_currency="RUB",
            )
        self.assertEqual(captured.exception.code, "currency_mismatch")

        with self.assertRaises(PromoValidationError) as captured:
            _compute_discounted_amount(
                effect_type=PromoEffectType.FIXED_PRICE,
                effect_value=1000,
                base_amount=1000,
                currency="RUB",
                campaign_currency="RUB",
            )
        self.assertEqual(captured.exception.code, "no_price_improvement")

        with self.assertRaises(PromoValidationError) as captured:
            _compute_discounted_amount(
                effect_type=PromoEffectType.EXTRA_DAYS,
                effect_value=7,
                base_amount=1000,
                currency="RUB",
                campaign_currency="RUB",
            )
        self.assertEqual(captured.exception.code, "unsupported_discount_effect")

    def test_validate_existing_redemption_rejects_conflicting_idempotent_reuse(
        self,
    ) -> None:
        account_id = uuid.uuid4()
        redemption = PromoRedemption(
            account_id=account_id,
            promo_code_id=10,
            plan_code="plan_1m",
            effect_type=PromoEffectType.PERCENT_DISCOUNT,
            effect_value=20,
            original_amount=1000,
            discount_amount=200,
            final_amount=800,
            granted_duration_days=30,
        )

        with self.assertRaises(PromoConflictError) as captured:
            _validate_existing_redemption(
                redemption,
                account_id=uuid.uuid4(),
                promo_code_id=10,
                plan_code="plan_1m",
                effect_type=PromoEffectType.PERCENT_DISCOUNT,
                effect_value=20,
                original_amount=1000,
                discount_amount=200,
                final_amount=800,
                granted_duration_days=30,
            )
        self.assertEqual(captured.exception.code, "idempotency_account_conflict")

        with self.assertRaises(PromoConflictError) as captured:
            _validate_existing_redemption(
                redemption,
                account_id=account_id,
                promo_code_id=10,
                plan_code="plan_3m",
                effect_type=PromoEffectType.PERCENT_DISCOUNT,
                effect_value=20,
                original_amount=1000,
                discount_amount=200,
                final_amount=800,
                granted_duration_days=30,
            )
        self.assertEqual(captured.exception.code, "idempotency_plan_conflict")

        with self.assertRaises(PromoConflictError) as captured:
            _validate_existing_redemption(
                redemption,
                account_id=account_id,
                promo_code_id=10,
                plan_code="plan_1m",
                effect_type=PromoEffectType.PERCENT_DISCOUNT,
                effect_value=10,
                original_amount=1000,
                discount_amount=100,
                final_amount=900,
                granted_duration_days=30,
            )
        self.assertEqual(captured.exception.code, "idempotency_effect_conflict")

    def test_resolve_plan_checkout_amount_supports_rub_and_stars(self) -> None:
        self.assertGreater(
            resolve_plan_checkout_amount(plan_code="plan_1m", currency="RUB"), 0
        )
        self.assertGreater(
            resolve_plan_checkout_amount(plan_code="plan_1m", currency="XTR"), 0
        )

    def test_resolve_plan_checkout_amount_rejects_unsupported_or_missing_stars_price(
        self,
    ) -> None:
        with self.assertRaises(PromoValidationError) as captured:
            resolve_plan_checkout_amount(plan_code="plan_1m", currency="USD")
        self.assertEqual(captured.exception.code, "unsupported_currency")

        with patch(
            "app.services.promos.get_subscription_plan",
            return_value=type("Plan", (), {"price_rub": 100, "price_stars": None})(),
        ):
            with self.assertRaises(Exception) as captured:
                resolve_plan_checkout_amount(plan_code="plan_1m", currency="XTR")

        self.assertEqual(
            getattr(captured.exception, "code", None), "stars_price_not_configured"
        )
