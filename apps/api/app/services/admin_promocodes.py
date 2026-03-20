from __future__ import annotations

import re
import secrets
import string
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    PromoCampaign,
    PromoCampaignStatus,
    PromoCode,
    PromoEffectType,
    PromoRedemption,
    PromoRedemptionStatus,
)
from app.services.plans import get_subscription_plans

GENERATED_PROMO_CODE_ALPHABET = string.ascii_uppercase + string.digits


class AdminPromoServiceError(Exception):
    default_code: str | None = None

    def __init__(self, detail: str, *, code: str | None = None) -> None:
        super().__init__(detail)
        self.code = code or self.default_code


class AdminPromoValidationError(AdminPromoServiceError):
    default_code = "admin_promo_validation_failed"


class AdminPromoCampaignNotFoundError(AdminPromoServiceError):
    default_code = "admin_promo_campaign_not_found"


class AdminPromoCodeNotFoundError(AdminPromoServiceError):
    default_code = "admin_promo_code_not_found"


class AdminPromoConflictError(AdminPromoServiceError):
    default_code = "admin_promo_conflict"


def _normalize_required_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise AdminPromoValidationError(f"{field_name} is required")
    if len(normalized) > max_length:
        raise AdminPromoValidationError(f"{field_name} is too long")
    return normalized


def _normalize_optional_text(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise AdminPromoValidationError("description is too long")
    return normalized


def _normalize_currency(value: str) -> str:
    normalized = _normalize_required_text(
        value, field_name="currency", max_length=8
    ).upper()
    return normalized


def _normalize_plan_codes(plan_codes: Sequence[str] | None) -> list[str] | None:
    if plan_codes is None:
        return None

    normalized: list[str] = []
    seen: set[str] = set()
    available_plan_codes = {plan.code for plan in get_subscription_plans()}
    for raw_code in plan_codes:
        code = _normalize_required_text(raw_code, field_name="plan_code", max_length=64)
        if code in seen:
            continue
        if code not in available_plan_codes:
            raise AdminPromoValidationError(f"unknown subscription plan: {code}")
        normalized.append(code)
        seen.add(code)

    return normalized or None


def _normalize_optional_positive_int(
    value: int | None,
    *,
    field_name: str,
) -> int | None:
    if value is None:
        return None
    if value <= 0:
        raise AdminPromoValidationError(f"{field_name} must be positive")
    return value


def _normalize_promo_code(code: str) -> str:
    normalized = _normalize_required_text(
        code, field_name="code", max_length=64
    ).upper()
    allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if any(char not in allowed_chars for char in normalized):
        raise AdminPromoValidationError(
            "code may contain only A-Z, 0-9, hyphen, and underscore"
        )
    return normalized


def _normalize_optional_code_prefix(prefix: str | None) -> str | None:
    if prefix is None:
        return None
    normalized = prefix.strip().upper()
    if not normalized:
        return None
    allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if any(char not in allowed_chars for char in normalized):
        raise AdminPromoValidationError(
            "prefix may contain only A-Z, 0-9, hyphen, and underscore"
        )
    normalized = normalized.rstrip("-_")
    return normalized or None


def _parse_import_codes_text(codes_text: str) -> list[str]:
    raw_items = re.split(r"[\n,;]+", codes_text)
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        stripped = raw_item.strip()
        if not stripped:
            continue
        code = _normalize_promo_code(stripped)
        if code in seen:
            continue
        normalized.append(code)
        seen.add(code)
    if not normalized:
        raise AdminPromoValidationError("no promo codes found in import payload")
    return normalized


def _validate_campaign_constraints(
    *,
    effect_type: PromoEffectType,
    effect_value: int,
    starts_at: datetime | None,
    ends_at: datetime | None,
    requires_active_subscription: bool,
    requires_no_active_subscription: bool,
    total_redemptions_limit: int | None,
    per_account_redemptions_limit: int | None,
) -> None:
    if ends_at is not None and starts_at is not None and ends_at <= starts_at:
        raise AdminPromoValidationError("ends_at must be later than starts_at")

    if requires_active_subscription and requires_no_active_subscription:
        raise AdminPromoValidationError(
            "requires_active_subscription and requires_no_active_subscription are mutually exclusive"
        )

    if (
        total_redemptions_limit is not None
        and per_account_redemptions_limit is not None
    ):
        if per_account_redemptions_limit > total_redemptions_limit:
            raise AdminPromoValidationError(
                "per_account_redemptions_limit must not exceed total_redemptions_limit"
            )

    if effect_type == PromoEffectType.PERCENT_DISCOUNT:
        if effect_value <= 0 or effect_value > 100:
            raise AdminPromoValidationError(
                "percent_discount value must be between 1 and 100"
            )
        return

    if effect_type == PromoEffectType.FIXED_PRICE:
        if effect_value < 0:
            raise AdminPromoValidationError(
                "fixed_price value must be zero or positive"
            )
        return

    if effect_value <= 0:
        raise AdminPromoValidationError(f"{effect_type.value} value must be positive")


async def create_promo_campaign(
    session: AsyncSession,
    *,
    admin_id: UUID,
    name: str,
    description: str | None,
    status: PromoCampaignStatus,
    effect_type: PromoEffectType,
    effect_value: int,
    currency: str,
    plan_codes: Sequence[str] | None,
    first_purchase_only: bool,
    requires_active_subscription: bool,
    requires_no_active_subscription: bool,
    starts_at: datetime | None,
    ends_at: datetime | None,
    total_redemptions_limit: int | None,
    per_account_redemptions_limit: int | None,
) -> PromoCampaign:
    normalized_name = _normalize_required_text(name, field_name="name", max_length=255)
    normalized_description = _normalize_optional_text(description, max_length=2000)
    normalized_currency = _normalize_currency(currency)
    normalized_plan_codes = _normalize_plan_codes(plan_codes)
    normalized_total_limit = _normalize_optional_positive_int(
        total_redemptions_limit,
        field_name="total_redemptions_limit",
    )
    normalized_per_account_limit = _normalize_optional_positive_int(
        per_account_redemptions_limit,
        field_name="per_account_redemptions_limit",
    )

    _validate_campaign_constraints(
        effect_type=effect_type,
        effect_value=effect_value,
        starts_at=starts_at,
        ends_at=ends_at,
        requires_active_subscription=requires_active_subscription,
        requires_no_active_subscription=requires_no_active_subscription,
        total_redemptions_limit=normalized_total_limit,
        per_account_redemptions_limit=normalized_per_account_limit,
    )

    campaign = PromoCampaign(
        name=normalized_name,
        description=normalized_description,
        status=status,
        effect_type=effect_type,
        effect_value=effect_value,
        currency=normalized_currency,
        plan_codes=normalized_plan_codes,
        first_purchase_only=first_purchase_only,
        requires_active_subscription=requires_active_subscription,
        requires_no_active_subscription=requires_no_active_subscription,
        starts_at=starts_at,
        ends_at=ends_at,
        total_redemptions_limit=normalized_total_limit,
        per_account_redemptions_limit=normalized_per_account_limit,
        created_by_admin_id=admin_id,
    )
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)
    return campaign


async def list_promo_campaigns(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: PromoCampaignStatus | None = None,
) -> tuple[list[tuple[PromoCampaign, int, int]], int]:
    code_counts = (
        select(
            PromoCode.campaign_id.label("campaign_id"),
            func.count(PromoCode.id).label("codes_count"),
        )
        .group_by(PromoCode.campaign_id)
        .subquery()
    )
    redemption_counts = (
        select(
            PromoRedemption.campaign_id.label("campaign_id"),
            func.count(PromoRedemption.id).label("redemptions_count"),
        )
        .group_by(PromoRedemption.campaign_id)
        .subquery()
    )

    filters = []
    if status is not None:
        filters.append(PromoCampaign.status == status)

    statement = (
        select(
            PromoCampaign,
            func.coalesce(code_counts.c.codes_count, 0),
            func.coalesce(redemption_counts.c.redemptions_count, 0),
        )
        .outerjoin(code_counts, code_counts.c.campaign_id == PromoCampaign.id)
        .outerjoin(
            redemption_counts, redemption_counts.c.campaign_id == PromoCampaign.id
        )
        .order_by(PromoCampaign.created_at.desc(), PromoCampaign.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if filters:
        statement = statement.where(*filters)

    count_statement = select(func.count()).select_from(PromoCampaign)
    if filters:
        count_statement = count_statement.where(*filters)

    result = await session.execute(statement)
    rows = [
        (campaign, int(codes_count), int(redemptions_count))
        for campaign, codes_count, redemptions_count in result.all()
    ]
    total = int(await session.scalar(count_statement) or 0)
    return rows, total


async def update_promo_campaign(
    session: AsyncSession,
    *,
    campaign_id: int,
    admin_id: UUID,
    name: str,
    description: str | None,
    status: PromoCampaignStatus,
    effect_type: PromoEffectType,
    effect_value: int,
    currency: str,
    plan_codes: Sequence[str] | None,
    first_purchase_only: bool,
    requires_active_subscription: bool,
    requires_no_active_subscription: bool,
    starts_at: datetime | None,
    ends_at: datetime | None,
    total_redemptions_limit: int | None,
    per_account_redemptions_limit: int | None,
) -> PromoCampaign:
    campaign = await session.get(PromoCampaign, campaign_id)
    if campaign is None:
        raise AdminPromoCampaignNotFoundError("promo campaign not found")

    normalized_name = _normalize_required_text(name, field_name="name", max_length=255)
    normalized_description = _normalize_optional_text(description, max_length=2000)
    normalized_currency = _normalize_currency(currency)
    normalized_plan_codes = _normalize_plan_codes(plan_codes)
    normalized_total_limit = _normalize_optional_positive_int(
        total_redemptions_limit,
        field_name="total_redemptions_limit",
    )
    normalized_per_account_limit = _normalize_optional_positive_int(
        per_account_redemptions_limit,
        field_name="per_account_redemptions_limit",
    )

    _validate_campaign_constraints(
        effect_type=effect_type,
        effect_value=effect_value,
        starts_at=starts_at,
        ends_at=ends_at,
        requires_active_subscription=requires_active_subscription,
        requires_no_active_subscription=requires_no_active_subscription,
        total_redemptions_limit=normalized_total_limit,
        per_account_redemptions_limit=normalized_per_account_limit,
    )

    campaign.name = normalized_name
    campaign.description = normalized_description
    campaign.status = status
    campaign.effect_type = effect_type
    campaign.effect_value = effect_value
    campaign.currency = normalized_currency
    campaign.plan_codes = normalized_plan_codes
    campaign.first_purchase_only = first_purchase_only
    campaign.requires_active_subscription = requires_active_subscription
    campaign.requires_no_active_subscription = requires_no_active_subscription
    campaign.starts_at = starts_at
    campaign.ends_at = ends_at
    campaign.total_redemptions_limit = normalized_total_limit
    campaign.per_account_redemptions_limit = normalized_per_account_limit
    campaign.created_by_admin_id = campaign.created_by_admin_id or admin_id

    await session.commit()
    await session.refresh(campaign)
    return campaign


async def create_promo_code(
    session: AsyncSession,
    *,
    campaign_id: int,
    admin_id: UUID,
    code: str,
    max_redemptions: int | None,
    assigned_account_id: UUID | None,
    is_active: bool,
) -> PromoCode:
    campaign = await session.get(PromoCampaign, campaign_id)
    if campaign is None:
        raise AdminPromoCampaignNotFoundError("promo campaign not found")

    normalized_code = _normalize_promo_code(code)
    normalized_max_redemptions = _normalize_optional_positive_int(
        max_redemptions,
        field_name="max_redemptions",
    )

    promo_code = PromoCode(
        campaign_id=campaign.id,
        code=normalized_code,
        max_redemptions=normalized_max_redemptions,
        assigned_account_id=assigned_account_id,
        is_active=is_active,
        created_by_admin_id=admin_id,
    )
    session.add(promo_code)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AdminPromoConflictError("promo code already exists") from exc

    await session.refresh(promo_code)
    return promo_code


async def update_promo_code(
    session: AsyncSession,
    *,
    campaign_id: int,
    code_id: int,
    max_redemptions: int | None,
    assigned_account_id: UUID | None,
    is_active: bool,
) -> PromoCode:
    campaign = await session.get(PromoCampaign, campaign_id)
    if campaign is None:
        raise AdminPromoCampaignNotFoundError("promo campaign not found")

    promo_code = await session.get(PromoCode, code_id)
    if promo_code is None or promo_code.campaign_id != campaign.id:
        raise AdminPromoCodeNotFoundError("promo code not found")

    normalized_max_redemptions = _normalize_optional_positive_int(
        max_redemptions,
        field_name="max_redemptions",
    )

    promo_code.max_redemptions = normalized_max_redemptions
    promo_code.assigned_account_id = assigned_account_id
    promo_code.is_active = is_active

    await session.commit()
    await session.refresh(promo_code)
    return promo_code


async def list_promo_codes(
    session: AsyncSession,
    *,
    campaign_id: int,
    limit: int,
    offset: int,
) -> tuple[list[tuple[PromoCode, int]], int]:
    campaign = await session.get(PromoCampaign, campaign_id)
    if campaign is None:
        raise AdminPromoCampaignNotFoundError("promo campaign not found")

    redemption_counts = (
        select(
            PromoRedemption.promo_code_id.label("promo_code_id"),
            func.count(PromoRedemption.id).label("redemptions_count"),
        )
        .group_by(PromoRedemption.promo_code_id)
        .subquery()
    )

    statement = (
        select(
            PromoCode,
            func.coalesce(redemption_counts.c.redemptions_count, 0),
        )
        .outerjoin(redemption_counts, redemption_counts.c.promo_code_id == PromoCode.id)
        .where(PromoCode.campaign_id == campaign.id)
        .order_by(PromoCode.created_at.desc(), PromoCode.id.desc())
        .limit(limit)
        .offset(offset)
    )
    count_statement = (
        select(func.count())
        .select_from(PromoCode)
        .where(PromoCode.campaign_id == campaign.id)
    )

    result = await session.execute(statement)
    rows = [
        (promo_code, int(redemptions_count))
        for promo_code, redemptions_count in result.all()
    ]
    total = int(await session.scalar(count_statement) or 0)
    return rows, total


async def generate_promo_codes_batch(
    session: AsyncSession,
    *,
    campaign_id: int,
    admin_id: UUID,
    quantity: int,
    prefix: str | None,
    suffix_length: int,
    max_redemptions: int | None,
    assigned_account_id: UUID | None,
    is_active: bool,
) -> list[PromoCode]:
    campaign = await session.get(PromoCampaign, campaign_id)
    if campaign is None:
        raise AdminPromoCampaignNotFoundError("promo campaign not found")

    normalized_prefix = _normalize_optional_code_prefix(prefix)
    normalized_max_redemptions = _normalize_optional_positive_int(
        max_redemptions,
        field_name="max_redemptions",
    )

    if quantity <= 0:
        raise AdminPromoValidationError("quantity must be positive")
    if suffix_length <= 0:
        raise AdminPromoValidationError("suffix_length must be positive")
    if (
        normalized_prefix is not None
        and len(normalized_prefix) + 1 + suffix_length > 64
    ):
        raise AdminPromoValidationError("generated promo code would exceed max length")
    if normalized_prefix is None and suffix_length > 64:
        raise AdminPromoValidationError("generated promo code would exceed max length")

    separator = "-" if normalized_prefix else ""
    generated_codes: list[str] = []
    generated_set: set[str] = set()
    attempts = 0
    max_attempts = max(quantity * 40, 200)

    while len(generated_codes) < quantity and attempts < max_attempts:
        remaining = quantity - len(generated_codes)
        batch_size = min(max(remaining * 3, 8), 512)
        candidate_pool: set[str] = set()
        while len(candidate_pool) < batch_size and attempts < max_attempts:
            suffix = "".join(
                secrets.choice(GENERATED_PROMO_CODE_ALPHABET)
                for _ in range(suffix_length)
            )
            code = (
                f"{normalized_prefix}{separator}{suffix}"
                if normalized_prefix
                else suffix
            )
            attempts += 1
            if code in generated_set:
                continue
            candidate_pool.add(code)

        if not candidate_pool:
            break

        existing_codes = set(
            (
                await session.scalars(
                    select(PromoCode.code).where(
                        PromoCode.code.in_(list(candidate_pool))
                    )
                )
            ).all()
        )
        for code in candidate_pool:
            if code in existing_codes or code in generated_set:
                continue
            generated_codes.append(code)
            generated_set.add(code)
            if len(generated_codes) >= quantity:
                break

    if len(generated_codes) < quantity:
        raise AdminPromoConflictError(
            "could not allocate requested number of unique promo codes"
        )

    promo_codes = [
        PromoCode(
            campaign_id=campaign.id,
            code=code,
            max_redemptions=normalized_max_redemptions,
            assigned_account_id=assigned_account_id,
            is_active=is_active,
            created_by_admin_id=admin_id,
        )
        for code in generated_codes
    ]
    session.add_all(promo_codes)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AdminPromoConflictError(
            "promo code generation conflicted with an existing code"
        ) from exc

    for promo_code in promo_codes:
        await session.refresh(promo_code)
    return promo_codes


async def import_promo_codes(
    session: AsyncSession,
    *,
    campaign_id: int,
    admin_id: UUID,
    codes_text: str,
    max_redemptions: int | None,
    assigned_account_id: UUID | None,
    is_active: bool,
    skip_duplicates: bool,
) -> tuple[list[PromoCode], list[str]]:
    campaign = await session.get(PromoCampaign, campaign_id)
    if campaign is None:
        raise AdminPromoCampaignNotFoundError("promo campaign not found")

    normalized_codes = _parse_import_codes_text(codes_text)
    normalized_max_redemptions = _normalize_optional_positive_int(
        max_redemptions,
        field_name="max_redemptions",
    )

    existing_codes = set(
        (
            await session.scalars(
                select(PromoCode.code).where(PromoCode.code.in_(normalized_codes))
            )
        ).all()
    )

    if existing_codes and not skip_duplicates:
        first_conflict = sorted(existing_codes)[0]
        raise AdminPromoConflictError(f"promo code already exists: {first_conflict}")

    codes_to_create = [code for code in normalized_codes if code not in existing_codes]
    skipped_codes = [code for code in normalized_codes if code in existing_codes]

    promo_codes = [
        PromoCode(
            campaign_id=campaign.id,
            code=code,
            max_redemptions=normalized_max_redemptions,
            assigned_account_id=assigned_account_id,
            is_active=is_active,
            created_by_admin_id=admin_id,
        )
        for code in codes_to_create
    ]

    if not promo_codes:
        return [], skipped_codes

    session.add_all(promo_codes)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AdminPromoConflictError(
            "promo code import conflicted with an existing code"
        ) from exc

    for promo_code in promo_codes:
        await session.refresh(promo_code)
    return promo_codes, skipped_codes


async def export_promo_codes(
    session: AsyncSession,
    *,
    campaign_id: int,
) -> list[tuple[PromoCode, int]]:
    campaign = await session.get(PromoCampaign, campaign_id)
    if campaign is None:
        raise AdminPromoCampaignNotFoundError("promo campaign not found")

    redemption_counts = (
        select(
            PromoRedemption.promo_code_id.label("promo_code_id"),
            func.count(PromoRedemption.id).label("redemptions_count"),
        )
        .group_by(PromoRedemption.promo_code_id)
        .subquery()
    )

    statement = (
        select(
            PromoCode,
            func.coalesce(redemption_counts.c.redemptions_count, 0),
        )
        .outerjoin(redemption_counts, redemption_counts.c.promo_code_id == PromoCode.id)
        .where(PromoCode.campaign_id == campaign.id)
        .order_by(PromoCode.created_at.desc(), PromoCode.id.desc())
    )

    result = await session.execute(statement)
    return [
        (promo_code, int(redemptions_count))
        for promo_code, redemptions_count in result.all()
    ]


async def list_promo_redemptions(
    session: AsyncSession,
    *,
    campaign_id: int,
    limit: int,
    offset: int,
    status: PromoRedemptionStatus | None = None,
    promo_code_id: int | None = None,
    redemption_context: str | None = None,
    code_query: str | None = None,
    account_id: UUID | None = None,
) -> tuple[list[tuple[PromoRedemption, str]], int]:
    campaign = await session.get(PromoCampaign, campaign_id)
    if campaign is None:
        raise AdminPromoCampaignNotFoundError("promo campaign not found")

    filters = [PromoRedemption.campaign_id == campaign.id]
    if status is not None:
        filters.append(PromoRedemption.status == status)
    if promo_code_id is not None:
        filters.append(PromoRedemption.promo_code_id == promo_code_id)
    if redemption_context is not None:
        filters.append(PromoRedemption.redemption_context == redemption_context)
    if account_id is not None:
        filters.append(PromoRedemption.account_id == account_id)
    if code_query is not None and code_query.strip():
        filters.append(func.upper(PromoCode.code).contains(code_query.strip().upper()))

    statement = (
        select(PromoRedemption, PromoCode.code)
        .select_from(PromoRedemption)
        .join(PromoCode, PromoCode.id == PromoRedemption.promo_code_id)
        .where(*filters)
        .order_by(PromoRedemption.created_at.desc(), PromoRedemption.id.desc())
        .limit(limit)
        .offset(offset)
    )
    count_statement = (
        select(func.count())
        .select_from(PromoRedemption)
        .join(PromoCode, PromoCode.id == PromoRedemption.promo_code_id)
        .where(*filters)
    )

    result = await session.execute(statement)
    rows = [(redemption, str(code)) for redemption, code in result.all()]
    total = int(await session.scalar(count_statement) or 0)
    return rows, total
