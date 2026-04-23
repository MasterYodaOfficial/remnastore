import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_internal_api_token
from app.core.audit import build_request_audit_context, log_audit_event
from app.core.config import settings
from app.db.models import AccountStatus
from app.db.session import get_session
from app.schemas.admin import AdminDashboardSummaryResponse
from app.schemas.bot import (
    BotDashboardResponse,
    BotPlanActionRequest,
    BotPlanListResponse,
    BotPlanPaymentResponse,
)
from app.schemas.internal import TelegramAccountAccessResponse
from app.schemas.internal import (
    BotAdminBroadcastLaunchResponse,
    BotAdminBroadcastPreviewResponse,
    BotAdminBroadcastRequest,
    BotAdminBroadcastStatusItem,
    BotAdminBroadcastStatusListResponse,
)
from app.services.admin_dashboard import get_admin_dashboard_summary
from app.services.accounts import (
    get_account_by_telegram_id,
    mark_telegram_account_reachable,
)
from app.services.broadcasts import (
    BroadcastContentType,
    BroadcastValidationError,
    create_and_launch_bot_admin_broadcast,
    get_bot_admin_actor,
    get_latest_broadcast_run,
    list_broadcasts,
    send_bot_admin_broadcast_preview,
)
from app.services.bot_menu import (
    BotMenuAccountNotFoundError,
    BotMenuServiceError,
    activate_trial_for_telegram_account,
    create_telegram_stars_plan_payment_for_telegram_account,
    create_yookassa_plan_payment_for_telegram_account,
    get_bot_dashboard,
    get_bot_plans,
)
from app.services.payments import (
    PaymentAccountBlockedError,
    PaymentConflictError,
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
)
from app.services.i18n import translate
from app.services.plans import SubscriptionPlanError
from app.services.subscriptions import RemnawaveSyncError, TrialEligibilityError

router = APIRouter()


def _verify_bot_admin_telegram_id(telegram_id: int) -> None:
    if telegram_id not in settings.bot_admin_id_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="telegram admin access denied",
        )


async def _build_bot_admin_broadcast_status_item(
    session: AsyncSession,
    *,
    broadcast,
) -> BotAdminBroadcastStatusItem:
    latest_run = await get_latest_broadcast_run(session, broadcast_id=broadcast.id)
    counters = latest_run.counters if latest_run is not None else None
    return BotAdminBroadcastStatusItem(
        broadcast_id=broadcast.id,
        title=broadcast.title,
        content_type=broadcast.content_type,
        status=broadcast.status,
        latest_run_status=latest_run.run.status if latest_run is not None else None,
        estimated_telegram_recipients=broadcast.estimated_telegram_recipients,
        pending_deliveries=counters.pending_deliveries if counters is not None else 0,
        delivered_deliveries=(
            counters.delivered_deliveries if counters is not None else 0
        ),
        failed_deliveries=counters.failed_deliveries if counters is not None else 0,
        skipped_deliveries=counters.skipped_deliveries if counters is not None else 0,
        updated_at=broadcast.updated_at,
        launched_at=broadcast.launched_at,
    )


@router.get(
    "/telegram-accounts/{telegram_id}/access",
    response_model=TelegramAccountAccessResponse,
)
async def read_telegram_account_access(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> TelegramAccountAccessResponse:
    verify_internal_api_token(authorization)
    account = await get_account_by_telegram_id(session, telegram_id=telegram_id)
    if account is None:
        return TelegramAccountAccessResponse(
            telegram_id=telegram_id,
            exists=False,
            status=None,
            fully_blocked=False,
            telegram_bot_blocked=False,
        )

    return TelegramAccountAccessResponse(
        telegram_id=telegram_id,
        exists=True,
        status=account.status,
        fully_blocked=account.status == AccountStatus.BLOCKED,
        telegram_bot_blocked=account.telegram_bot_blocked_at is not None,
    )


@router.post(
    "/telegram-accounts/{telegram_id}/reachable",
    response_model=TelegramAccountAccessResponse,
)
async def mark_telegram_account_as_reachable(
    telegram_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> TelegramAccountAccessResponse:
    verify_internal_api_token(authorization)
    request_context = build_request_audit_context(request)
    account = await mark_telegram_account_reachable(session, telegram_id=telegram_id)
    await session.commit()

    if account is None:
        log_audit_event(
            "internal.telegram_account.reachable",
            outcome="failure",
            category="business",
            telegram_id=telegram_id,
            reason="account_not_found",
            **request_context,
        )
        return TelegramAccountAccessResponse(
            telegram_id=telegram_id,
            exists=False,
            status=None,
            fully_blocked=False,
            telegram_bot_blocked=False,
        )

    log_audit_event(
        "internal.telegram_account.reachable",
        outcome="success",
        category="business",
        account_id=account.id,
        telegram_id=telegram_id,
        **request_context,
    )
    return TelegramAccountAccessResponse(
        telegram_id=telegram_id,
        exists=True,
        status=account.status,
        fully_blocked=account.status == AccountStatus.BLOCKED,
        telegram_bot_blocked=account.telegram_bot_blocked_at is not None,
    )


@router.get("/bot/dashboard/{telegram_id}", response_model=BotDashboardResponse)
async def read_bot_dashboard(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> BotDashboardResponse:
    verify_internal_api_token(authorization)
    return await get_bot_dashboard(session, telegram_id=telegram_id)


@router.get("/bot/plans", response_model=BotPlanListResponse)
async def read_bot_plans(
    authorization: str | None = Header(default=None),
) -> BotPlanListResponse:
    verify_internal_api_token(authorization)
    try:
        return get_bot_plans()
    except SubscriptionPlanError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


@router.get(
    "/bot/admin/stats/summary",
    response_model=AdminDashboardSummaryResponse,
)
async def read_bot_admin_stats_summary(
    admin_telegram_id: int,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> AdminDashboardSummaryResponse:
    verify_internal_api_token(authorization)
    _verify_bot_admin_telegram_id(admin_telegram_id)
    return AdminDashboardSummaryResponse(**(await get_admin_dashboard_summary(session)))


@router.post(
    "/bot/admin/broadcasts/test",
    response_model=BotAdminBroadcastPreviewResponse,
)
async def test_bot_admin_broadcast(
    payload: BotAdminBroadcastRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> BotAdminBroadcastPreviewResponse:
    verify_internal_api_token(authorization)
    _verify_bot_admin_telegram_id(payload.admin_telegram_id)
    request_context = build_request_audit_context(request)
    try:
        message_ids = await send_bot_admin_broadcast_preview(
            telegram_id=payload.admin_telegram_id,
            source_chat_id=payload.source_chat_id,
            source_message_ids=payload.source_message_ids,
        )
    except BroadcastValidationError as exc:
        log_audit_event(
            "internal.bot.admin.broadcast_test",
            outcome="failure",
            category="business",
            telegram_id=payload.admin_telegram_id,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log_audit_event(
            "internal.bot.admin.broadcast_test",
            outcome="error",
            category="business",
            telegram_id=payload.admin_telegram_id,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    log_audit_event(
        "internal.bot.admin.broadcast_test",
        outcome="success",
        category="business",
        telegram_id=payload.admin_telegram_id,
        source_chat_id=payload.source_chat_id,
        source_message_ids=payload.source_message_ids,
        media_group_id=payload.media_group_id,
        **request_context,
    )
    return BotAdminBroadcastPreviewResponse(
        content_type=BroadcastContentType.TELEGRAM_COPY,
        telegram_message_ids=message_ids,
    )


@router.post(
    "/bot/admin/broadcasts/send-now",
    response_model=BotAdminBroadcastLaunchResponse,
)
async def send_now_bot_admin_broadcast(
    payload: BotAdminBroadcastRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> BotAdminBroadcastLaunchResponse:
    verify_internal_api_token(authorization)
    _verify_bot_admin_telegram_id(payload.admin_telegram_id)
    request_context = build_request_audit_context(request)
    try:
        broadcast = await create_and_launch_bot_admin_broadcast(
            session,
            admin_telegram_id=payload.admin_telegram_id,
            source_chat_id=payload.source_chat_id,
            source_message_ids=payload.source_message_ids,
            comment=f"source_chat_id={payload.source_chat_id}; source_message_ids={payload.source_message_ids}",
            idempotency_key=f"bot-admin:{uuid.uuid4().hex}",
        )
    except BroadcastValidationError as exc:
        await session.rollback()
        log_audit_event(
            "internal.bot.admin.broadcast_send_now",
            outcome="failure",
            category="business",
            telegram_id=payload.admin_telegram_id,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        await session.rollback()
        log_audit_event(
            "internal.bot.admin.broadcast_send_now",
            outcome="error",
            category="business",
            telegram_id=payload.admin_telegram_id,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    latest_run = await get_latest_broadcast_run(session, broadcast_id=broadcast.id)
    await session.commit()

    log_audit_event(
        "internal.bot.admin.broadcast_send_now",
        outcome="success",
        category="business",
        telegram_id=payload.admin_telegram_id,
        broadcast_id=broadcast.id,
        content_type=BroadcastContentType.TELEGRAM_COPY.value,
        estimated_telegram_recipients=broadcast.estimated_telegram_recipients,
        **request_context,
    )
    return BotAdminBroadcastLaunchResponse(
        broadcast_id=broadcast.id,
        status=broadcast.status,
        latest_run_status=latest_run.run.status if latest_run is not None else None,
        estimated_telegram_recipients=broadcast.estimated_telegram_recipients,
        pending_deliveries=(
            latest_run.counters.pending_deliveries if latest_run is not None else 0
        ),
        delivered_deliveries=(
            latest_run.counters.delivered_deliveries if latest_run is not None else 0
        ),
        failed_deliveries=(
            latest_run.counters.failed_deliveries if latest_run is not None else 0
        ),
        skipped_deliveries=(
            latest_run.counters.skipped_deliveries if latest_run is not None else 0
        ),
    )


@router.get(
    "/bot/admin/broadcasts",
    response_model=BotAdminBroadcastStatusListResponse,
)
async def list_bot_admin_broadcast_statuses(
    admin_telegram_id: int,
    limit: int = 5,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> BotAdminBroadcastStatusListResponse:
    verify_internal_api_token(authorization)
    _verify_bot_admin_telegram_id(admin_telegram_id)
    actor_admin = await get_bot_admin_actor(session, telegram_id=admin_telegram_id)
    if actor_admin is None:
        return BotAdminBroadcastStatusListResponse(items=[])
    items, _ = await list_broadcasts(
        session,
        limit=max(1, min(limit, 10)),
        offset=0,
        content_type=BroadcastContentType.TELEGRAM_COPY,
        created_by_admin_id=actor_admin.id,
    )
    return BotAdminBroadcastStatusListResponse(
        items=[
            await _build_bot_admin_broadcast_status_item(session, broadcast=item)
            for item in items
        ]
    )


@router.post(
    "/bot/subscriptions/trial/{telegram_id}", response_model=BotDashboardResponse
)
async def create_bot_trial_subscription(
    telegram_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> BotDashboardResponse:
    verify_internal_api_token(authorization)
    request_context = build_request_audit_context(request)
    try:
        await activate_trial_for_telegram_account(session, telegram_id=telegram_id)
    except BotMenuAccountNotFoundError as exc:
        log_audit_event(
            "internal.bot.trial_activate",
            outcome="failure",
            category="business",
            telegram_id=telegram_id,
            reason="account_not_found",
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except TrialEligibilityError as exc:
        log_audit_event(
            "internal.bot.trial_activate",
            outcome="failure",
            category="business",
            telegram_id=telegram_id,
            reason=exc.reason,
            **request_context,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    except RemnawaveSyncError as exc:
        log_audit_event(
            "internal.bot.trial_activate",
            outcome="error",
            category="business",
            telegram_id=telegram_id,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    log_audit_event(
        "internal.bot.trial_activate",
        outcome="success",
        category="business",
        telegram_id=telegram_id,
        **request_context,
    )
    return await get_bot_dashboard(session, telegram_id=telegram_id)


@router.post(
    "/bot/payments/telegram-stars/plans/{plan_code}",
    response_model=BotPlanPaymentResponse,
)
async def create_bot_telegram_stars_plan_payment(
    plan_code: str,
    payload: BotPlanActionRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> BotPlanPaymentResponse:
    verify_internal_api_token(authorization)
    request_context = build_request_audit_context(request)
    try:
        response = await create_telegram_stars_plan_payment_for_telegram_account(
            session,
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            idempotency_key=payload.idempotency_key,
        )
    except BotMenuAccountNotFoundError as exc:
        log_audit_event(
            "internal.bot.payment_intent.telegram_stars",
            outcome="failure",
            category="business",
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            reason="account_not_found",
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except SubscriptionPlanError as exc:
        log_audit_event(
            "internal.bot.payment_intent.telegram_stars",
            outcome="failure",
            category="business",
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PaymentGatewayConfigurationError as exc:
        log_audit_event(
            "internal.bot.payment_intent.telegram_stars",
            outcome="error",
            category="business",
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except PaymentConflictError as exc:
        log_audit_event(
            "internal.bot.payment_intent.telegram_stars",
            outcome="failure",
            category="business",
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except PaymentAccountBlockedError as exc:
        log_audit_event(
            "internal.bot.payment_intent.telegram_stars",
            outcome="denied",
            category="security",
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except (PaymentGatewayError, BotMenuServiceError) as exc:
        log_audit_event(
            "internal.bot.payment_intent.telegram_stars",
            outcome="error",
            category="business",
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=translate("api.payments.errors.gateway_failed"),
        ) from exc
    log_audit_event(
        "internal.bot.payment_intent.telegram_stars",
        outcome="success",
        category="business",
        telegram_id=payload.telegram_id,
        plan_code=plan_code,
        provider_payment_id=response.provider_payment_id,
        **request_context,
    )
    return response


@router.post(
    "/bot/payments/yookassa/plans/{plan_code}", response_model=BotPlanPaymentResponse
)
async def create_bot_yookassa_plan_payment(
    plan_code: str,
    payload: BotPlanActionRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> BotPlanPaymentResponse:
    verify_internal_api_token(authorization)
    request_context = build_request_audit_context(request)
    try:
        response = await create_yookassa_plan_payment_for_telegram_account(
            session,
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            success_url=None,
            cancel_url=None,
            idempotency_key=payload.idempotency_key,
        )
    except BotMenuAccountNotFoundError as exc:
        log_audit_event(
            "internal.bot.payment_intent.yookassa",
            outcome="failure",
            category="business",
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            reason="account_not_found",
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except SubscriptionPlanError as exc:
        log_audit_event(
            "internal.bot.payment_intent.yookassa",
            outcome="failure",
            category="business",
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PaymentGatewayConfigurationError as exc:
        log_audit_event(
            "internal.bot.payment_intent.yookassa",
            outcome="error",
            category="business",
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except PaymentConflictError as exc:
        log_audit_event(
            "internal.bot.payment_intent.yookassa",
            outcome="failure",
            category="business",
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except PaymentAccountBlockedError as exc:
        log_audit_event(
            "internal.bot.payment_intent.yookassa",
            outcome="denied",
            category="security",
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except (PaymentGatewayError, BotMenuServiceError) as exc:
        log_audit_event(
            "internal.bot.payment_intent.yookassa",
            outcome="error",
            category="business",
            telegram_id=payload.telegram_id,
            plan_code=plan_code,
            reason=str(exc),
            **request_context,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=translate("api.payments.errors.gateway_failed"),
        ) from exc
    log_audit_event(
        "internal.bot.payment_intent.yookassa",
        outcome="success",
        category="business",
        telegram_id=payload.telegram_id,
        plan_code=plan_code,
        provider_payment_id=response.provider_payment_id,
        **request_context,
    )
    return response
