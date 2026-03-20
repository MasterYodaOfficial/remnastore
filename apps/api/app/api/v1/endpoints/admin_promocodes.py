from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import api_error, api_error_from_exception
from app.api.dependencies import get_current_admin
from app.db.models import (
    Admin,
    PromoCampaign,
    PromoCampaignStatus,
    PromoCode,
    PromoRedemption,
    PromoRedemptionContext,
    PromoRedemptionStatus,
)
from app.db.session import get_session
from app.schemas.admin import (
    AdminPromoCampaignCreateRequest,
    AdminPromoCampaignListResponse,
    AdminPromoCampaignResponse,
    AdminPromoCampaignUpdateRequest,
    AdminPromoCodeBatchCreateRequest,
    AdminPromoCodeBatchCreateResponse,
    AdminPromoCodeCreateRequest,
    AdminPromoCodeExportResponse,
    AdminPromoCodeImportRequest,
    AdminPromoCodeImportResponse,
    AdminPromoCodeListResponse,
    AdminPromoCodeResponse,
    AdminPromoCodeUpdateRequest,
    AdminPromoRedemptionListResponse,
    AdminPromoRedemptionResponse,
)
from app.services.i18n import translate
from app.services.admin_promocodes import (
    AdminPromoCampaignNotFoundError,
    AdminPromoConflictError,
    AdminPromoCodeNotFoundError,
    AdminPromoValidationError,
    create_promo_campaign,
    create_promo_code,
    export_promo_codes,
    generate_promo_codes_batch,
    import_promo_codes,
    list_promo_campaigns,
    list_promo_codes,
    list_promo_redemptions,
    update_promo_campaign,
    update_promo_code,
)


router = APIRouter()

_ADMIN_PROMO_ERROR_TRANSLATIONS: dict[str, str] = {
    "admin_promo_validation_failed": "api.admin.errors.promo_validation_failed",
}


def _admin_promo_service_error(status_code: int, exc: Exception):
    error_code = getattr(exc, "code", None)
    detail_key = (
        _ADMIN_PROMO_ERROR_TRANSLATIONS.get(error_code)
        if isinstance(error_code, str)
        else None
    )
    if detail_key is not None:
        exc.args = (translate(detail_key),)
    return api_error_from_exception(
        status_code,
        exc,
        error_code=error_code if isinstance(error_code, str) else None,
    )


async def _count_campaign_codes(session: AsyncSession, campaign_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count(PromoCode.id)).where(PromoCode.campaign_id == campaign_id)
        )
        or 0
    )


async def _count_campaign_redemptions(session: AsyncSession, campaign_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count(PromoRedemption.id)).where(
                PromoRedemption.campaign_id == campaign_id
            )
        )
        or 0
    )


async def _count_code_redemptions(session: AsyncSession, code_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count(PromoRedemption.id)).where(
                PromoRedemption.promo_code_id == code_id
            )
        )
        or 0
    )


def _build_campaign_response(
    campaign: PromoCampaign,
    *,
    codes_count: int = 0,
    redemptions_count: int = 0,
) -> AdminPromoCampaignResponse:
    return AdminPromoCampaignResponse(
        id=campaign.id,
        name=campaign.name,
        description=campaign.description,
        status=campaign.status,
        effect_type=campaign.effect_type,
        effect_value=campaign.effect_value,
        currency=campaign.currency,
        plan_codes=campaign.plan_codes,
        first_purchase_only=campaign.first_purchase_only,
        requires_active_subscription=campaign.requires_active_subscription,
        requires_no_active_subscription=campaign.requires_no_active_subscription,
        starts_at=campaign.starts_at,
        ends_at=campaign.ends_at,
        total_redemptions_limit=campaign.total_redemptions_limit,
        per_account_redemptions_limit=campaign.per_account_redemptions_limit,
        created_by_admin_id=campaign.created_by_admin_id,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        codes_count=codes_count,
        redemptions_count=redemptions_count,
    )


def _build_code_response(
    promo_code: PromoCode,
    *,
    redemptions_count: int = 0,
) -> AdminPromoCodeResponse:
    return AdminPromoCodeResponse(
        id=promo_code.id,
        campaign_id=promo_code.campaign_id,
        code=promo_code.code,
        is_active=promo_code.is_active,
        assigned_account_id=promo_code.assigned_account_id,
        max_redemptions=promo_code.max_redemptions,
        created_by_admin_id=promo_code.created_by_admin_id,
        created_at=promo_code.created_at,
        redemptions_count=redemptions_count,
    )


def _build_redemption_response(
    redemption: PromoRedemption,
    *,
    promo_code: str,
) -> AdminPromoRedemptionResponse:
    return AdminPromoRedemptionResponse(
        id=redemption.id,
        campaign_id=redemption.campaign_id,
        promo_code_id=redemption.promo_code_id,
        promo_code=promo_code,
        account_id=redemption.account_id,
        status=redemption.status,
        redemption_context=redemption.redemption_context,
        plan_code=redemption.plan_code,
        effect_type=redemption.effect_type,
        effect_value=redemption.effect_value,
        currency=redemption.currency,
        original_amount=redemption.original_amount,
        discount_amount=redemption.discount_amount,
        final_amount=redemption.final_amount,
        granted_duration_days=redemption.granted_duration_days,
        balance_credit_amount=redemption.balance_credit_amount,
        payment_id=redemption.payment_id,
        subscription_grant_id=redemption.subscription_grant_id,
        ledger_entry_id=redemption.ledger_entry_id,
        reference_type=redemption.reference_type,
        reference_id=redemption.reference_id,
        failure_reason=redemption.failure_reason,
        created_at=redemption.created_at,
        applied_at=redemption.applied_at,
    )


@router.get("/campaigns", response_model=AdminPromoCampaignListResponse)
async def read_promo_campaigns(
    status_filter: PromoCampaignStatus | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminPromoCampaignListResponse:
    rows, total = await list_promo_campaigns(
        session,
        limit=limit,
        offset=offset,
        status=status_filter,
    )
    return AdminPromoCampaignListResponse(
        items=[
            _build_campaign_response(
                campaign,
                codes_count=codes_count,
                redemptions_count=redemptions_count,
            )
            for campaign, codes_count, redemptions_count in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/campaigns",
    response_model=AdminPromoCampaignResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_admin_promo_campaign(
    payload: AdminPromoCampaignCreateRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> AdminPromoCampaignResponse:
    try:
        campaign = await create_promo_campaign(
            session,
            admin_id=current_admin.id,
            name=payload.name,
            description=payload.description,
            status=payload.status,
            effect_type=payload.effect_type,
            effect_value=payload.effect_value,
            currency=payload.currency,
            plan_codes=payload.plan_codes,
            first_purchase_only=payload.first_purchase_only,
            requires_active_subscription=payload.requires_active_subscription,
            requires_no_active_subscription=payload.requires_no_active_subscription,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            total_redemptions_limit=payload.total_redemptions_limit,
            per_account_redemptions_limit=payload.per_account_redemptions_limit,
        )
    except AdminPromoValidationError as exc:
        raise _admin_promo_service_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY, exc
        ) from exc

    return _build_campaign_response(campaign)


@router.put("/campaigns/{campaign_id}", response_model=AdminPromoCampaignResponse)
async def update_admin_promo_campaign(
    campaign_id: int,
    payload: AdminPromoCampaignUpdateRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> AdminPromoCampaignResponse:
    try:
        campaign = await update_promo_campaign(
            session,
            campaign_id=campaign_id,
            admin_id=current_admin.id,
            name=payload.name,
            description=payload.description,
            status=payload.status,
            effect_type=payload.effect_type,
            effect_value=payload.effect_value,
            currency=payload.currency,
            plan_codes=payload.plan_codes,
            first_purchase_only=payload.first_purchase_only,
            requires_active_subscription=payload.requires_active_subscription,
            requires_no_active_subscription=payload.requires_no_active_subscription,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            total_redemptions_limit=payload.total_redemptions_limit,
            per_account_redemptions_limit=payload.per_account_redemptions_limit,
        )
    except AdminPromoCampaignNotFoundError as exc:
        exc.args = (translate("api.admin.errors.promo_campaign_not_found"),)
        raise api_error_from_exception(
            status.HTTP_404_NOT_FOUND,
            exc,
            error_code="admin_promo_campaign_not_found",
        ) from exc
    except AdminPromoValidationError as exc:
        raise _admin_promo_service_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY, exc
        ) from exc

    return _build_campaign_response(
        campaign,
        codes_count=await _count_campaign_codes(session, campaign.id),
        redemptions_count=await _count_campaign_redemptions(session, campaign.id),
    )


@router.get("/campaigns/{campaign_id}/codes", response_model=AdminPromoCodeListResponse)
async def read_promo_codes(
    campaign_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminPromoCodeListResponse:
    try:
        rows, total = await list_promo_codes(
            session,
            campaign_id=campaign_id,
            limit=limit,
            offset=offset,
        )
    except AdminPromoCampaignNotFoundError as exc:
        exc.args = (translate("api.admin.errors.promo_campaign_not_found"),)
        raise api_error_from_exception(
            status.HTTP_404_NOT_FOUND,
            exc,
            error_code="admin_promo_campaign_not_found",
        ) from exc

    return AdminPromoCodeListResponse(
        items=[
            _build_code_response(
                promo_code,
                redemptions_count=redemptions_count,
            )
            for promo_code, redemptions_count in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/campaigns/{campaign_id}/codes",
    response_model=AdminPromoCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_admin_promo_code(
    campaign_id: int,
    payload: AdminPromoCodeCreateRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> AdminPromoCodeResponse:
    try:
        promo_code = await create_promo_code(
            session,
            campaign_id=campaign_id,
            admin_id=current_admin.id,
            code=payload.code,
            max_redemptions=payload.max_redemptions,
            assigned_account_id=payload.assigned_account_id,
            is_active=payload.is_active,
        )
    except AdminPromoCampaignNotFoundError as exc:
        exc.args = (translate("api.admin.errors.promo_campaign_not_found"),)
        raise api_error_from_exception(
            status.HTTP_404_NOT_FOUND,
            exc,
            error_code="admin_promo_campaign_not_found",
        ) from exc
    except AdminPromoValidationError as exc:
        raise _admin_promo_service_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY, exc
        ) from exc
    except AdminPromoConflictError as exc:
        exc.args = (translate("api.admin.errors.promo_code_conflict"),)
        raise api_error_from_exception(
            status.HTTP_409_CONFLICT,
            exc,
            error_code="admin_promo_code_conflict",
        ) from exc

    return _build_code_response(promo_code)


@router.post(
    "/campaigns/{campaign_id}/codes/batch",
    response_model=AdminPromoCodeBatchCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def batch_create_admin_promo_codes(
    campaign_id: int,
    payload: AdminPromoCodeBatchCreateRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> AdminPromoCodeBatchCreateResponse:
    try:
        promo_codes = await generate_promo_codes_batch(
            session,
            campaign_id=campaign_id,
            admin_id=current_admin.id,
            quantity=payload.quantity,
            prefix=payload.prefix,
            suffix_length=payload.suffix_length,
            max_redemptions=payload.max_redemptions,
            assigned_account_id=payload.assigned_account_id,
            is_active=payload.is_active,
        )
    except AdminPromoCampaignNotFoundError as exc:
        exc.args = (translate("api.admin.errors.promo_campaign_not_found"),)
        raise api_error_from_exception(
            status.HTTP_404_NOT_FOUND,
            exc,
            error_code="admin_promo_campaign_not_found",
        ) from exc
    except AdminPromoValidationError as exc:
        raise _admin_promo_service_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY, exc
        ) from exc
    except AdminPromoConflictError as exc:
        exc.args = (translate("api.admin.errors.promo_batch_conflict"),)
        raise api_error_from_exception(
            status.HTTP_409_CONFLICT,
            exc,
            error_code="admin_promo_batch_conflict",
        ) from exc

    return AdminPromoCodeBatchCreateResponse(
        items=[_build_code_response(promo_code) for promo_code in promo_codes],
        created_count=len(promo_codes),
    )


@router.post(
    "/campaigns/{campaign_id}/codes/import",
    response_model=AdminPromoCodeImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_admin_promo_codes(
    campaign_id: int,
    payload: AdminPromoCodeImportRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> AdminPromoCodeImportResponse:
    try:
        promo_codes, skipped_codes = await import_promo_codes(
            session,
            campaign_id=campaign_id,
            admin_id=current_admin.id,
            codes_text=payload.codes_text,
            max_redemptions=payload.max_redemptions,
            assigned_account_id=payload.assigned_account_id,
            is_active=payload.is_active,
            skip_duplicates=payload.skip_duplicates,
        )
    except AdminPromoCampaignNotFoundError as exc:
        exc.args = (translate("api.admin.errors.promo_campaign_not_found"),)
        raise api_error_from_exception(
            status.HTTP_404_NOT_FOUND,
            exc,
            error_code="admin_promo_campaign_not_found",
        ) from exc
    except AdminPromoValidationError as exc:
        raise _admin_promo_service_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY, exc
        ) from exc
    except AdminPromoConflictError as exc:
        exc.args = (translate("api.admin.errors.promo_import_conflict"),)
        raise api_error_from_exception(
            status.HTTP_409_CONFLICT,
            exc,
            error_code="admin_promo_import_conflict",
        ) from exc

    return AdminPromoCodeImportResponse(
        items=[_build_code_response(promo_code) for promo_code in promo_codes],
        created_count=len(promo_codes),
        skipped_count=len(skipped_codes),
        skipped_codes=skipped_codes,
    )


@router.get(
    "/campaigns/{campaign_id}/codes/export",
    response_model=AdminPromoCodeExportResponse,
)
async def export_admin_promo_codes(
    campaign_id: int,
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminPromoCodeExportResponse:
    try:
        rows = await export_promo_codes(
            session,
            campaign_id=campaign_id,
        )
    except AdminPromoCampaignNotFoundError as exc:
        exc.args = (translate("api.admin.errors.promo_campaign_not_found"),)
        raise api_error_from_exception(
            status.HTTP_404_NOT_FOUND,
            exc,
            error_code="admin_promo_campaign_not_found",
        ) from exc

    return AdminPromoCodeExportResponse(
        items=[
            _build_code_response(promo_code, redemptions_count=redemptions_count)
            for promo_code, redemptions_count in rows
        ],
        exported_count=len(rows),
    )


@router.put(
    "/campaigns/{campaign_id}/codes/{code_id}",
    response_model=AdminPromoCodeResponse,
)
async def update_admin_promo_code(
    campaign_id: int,
    code_id: int,
    payload: AdminPromoCodeUpdateRequest,
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminPromoCodeResponse:
    try:
        promo_code = await update_promo_code(
            session,
            campaign_id=campaign_id,
            code_id=code_id,
            max_redemptions=payload.max_redemptions,
            assigned_account_id=payload.assigned_account_id,
            is_active=payload.is_active,
        )
    except AdminPromoCampaignNotFoundError as exc:
        exc.args = (translate("api.admin.errors.promo_campaign_not_found"),)
        raise api_error_from_exception(
            status.HTTP_404_NOT_FOUND,
            exc,
            error_code="admin_promo_campaign_not_found",
        ) from exc
    except AdminPromoCodeNotFoundError as exc:
        exc.args = (translate("api.admin.errors.promo_code_not_found"),)
        raise api_error_from_exception(
            status.HTTP_404_NOT_FOUND,
            exc,
            error_code="admin_promo_code_not_found",
        ) from exc
    except AdminPromoValidationError as exc:
        raise _admin_promo_service_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY, exc
        ) from exc

    return _build_code_response(
        promo_code,
        redemptions_count=await _count_code_redemptions(session, promo_code.id),
    )


@router.get(
    "/campaigns/{campaign_id}/redemptions",
    response_model=AdminPromoRedemptionListResponse,
)
async def read_promo_redemptions(
    campaign_id: int,
    status_filter: PromoRedemptionStatus | None = Query(default=None, alias="status"),
    redemption_context: PromoRedemptionContext | None = Query(default=None),
    promo_code_id: int | None = Query(default=None),
    code_query: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminPromoRedemptionListResponse:
    parsed_account_id = None
    if account_id:
        try:
            parsed_account_id = UUID(account_id)
        except ValueError as exc:
            raise api_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                translate("api.admin.errors.promo_invalid_account_id"),
                error_code="admin_promo_invalid_account_id",
            ) from exc
    try:
        rows, total = await list_promo_redemptions(
            session,
            campaign_id=campaign_id,
            limit=limit,
            offset=offset,
            status=status_filter,
            promo_code_id=promo_code_id,
            redemption_context=redemption_context.value
            if redemption_context is not None
            else None,
            code_query=code_query,
            account_id=parsed_account_id,
        )
    except AdminPromoCampaignNotFoundError as exc:
        exc.args = (translate("api.admin.errors.promo_campaign_not_found"),)
        raise api_error_from_exception(
            status.HTTP_404_NOT_FOUND,
            exc,
            error_code="admin_promo_campaign_not_found",
        ) from exc

    return AdminPromoRedemptionListResponse(
        items=[
            _build_redemption_response(redemption, promo_code=promo_code)
            for redemption, promo_code in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
