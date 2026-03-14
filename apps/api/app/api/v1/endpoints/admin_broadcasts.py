from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin, require_superuser_admin
from app.db.models import (
    Admin,
    Broadcast,
    BroadcastChannel,
    BroadcastDeliveryStatus,
    BroadcastRunStatus,
    BroadcastRunType,
    BroadcastStatus,
)
from app.db.session import get_session
from app.schemas.admin import (
    AdminBroadcastEstimateRequest,
    AdminBroadcastEstimateResponse,
    AdminBroadcastListResponse,
    AdminBroadcastRunDeliveryResponse,
    AdminBroadcastRunDetailResponse,
    AdminBroadcastRunListResponse,
    AdminBroadcastRunResponse,
    AdminBroadcastResponse,
    AdminBroadcastRuntimeActionRequest,
    AdminBroadcastScheduleRequest,
    AdminBroadcastTestSendRequest,
    AdminBroadcastTestSendResponse,
    AdminBroadcastUpsertRequest,
)
from app.services.broadcasts import (
    BroadcastConflictError,
    BroadcastNotFoundError,
    BroadcastValidationError,
    cancel_broadcast,
    delete_broadcast_draft,
    estimate_broadcast_audience,
    get_broadcast_run,
    get_latest_broadcast_run,
    create_broadcast_draft,
    get_broadcast,
    launch_broadcast_now,
    list_broadcasts,
    list_broadcast_run_deliveries,
    list_broadcast_runs,
    pause_broadcast,
    resume_broadcast,
    schedule_broadcast_launch,
    send_broadcast_test,
    update_broadcast_draft,
)


router = APIRouter()


def _build_run_response(item) -> AdminBroadcastRunResponse:
    run = item.run
    counters = item.counters
    return AdminBroadcastRunResponse(
        id=run.id,
        broadcast_id=run.broadcast_id,
        run_type=run.run_type,
        status=run.status,
        triggered_by_admin_id=run.triggered_by_admin_id,
        snapshot_total_accounts=run.snapshot_total_accounts,
        snapshot_in_app_targets=run.snapshot_in_app_targets,
        snapshot_telegram_targets=run.snapshot_telegram_targets,
        total_deliveries=counters.total_deliveries,
        pending_deliveries=counters.pending_deliveries,
        delivered_deliveries=counters.delivered_deliveries,
        failed_deliveries=counters.failed_deliveries,
        skipped_deliveries=counters.skipped_deliveries,
        in_app_delivered=counters.in_app_delivered,
        telegram_delivered=counters.telegram_delivered,
        in_app_pending=counters.in_app_pending,
        telegram_pending=counters.telegram_pending,
        started_at=run.started_at,
        completed_at=run.completed_at,
        cancelled_at=run.cancelled_at,
        last_error=run.last_error,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


async def _build_broadcast_response(
    session: AsyncSession,
    broadcast: Broadcast,
) -> AdminBroadcastResponse:
    latest_run = await get_latest_broadcast_run(session, broadcast_id=broadcast.id)
    payload = AdminBroadcastResponse.model_validate(broadcast, from_attributes=True).model_dump()
    payload["latest_run"] = _build_run_response(latest_run) if latest_run is not None else None
    return AdminBroadcastResponse(**payload)


@router.post("/estimate", response_model=AdminBroadcastEstimateResponse)
async def estimate_admin_broadcast(
    payload: AdminBroadcastEstimateRequest,
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminBroadcastEstimateResponse:
    try:
        estimate = await estimate_broadcast_audience(
            session,
            segment=payload.audience.segment,
            exclude_blocked=payload.audience.exclude_blocked,
            channels=payload.channels,
        )
    except BroadcastValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return AdminBroadcastEstimateResponse(
        channels=payload.channels,
        audience=payload.audience.model_dump(),
        estimated_total_accounts=estimate.total_accounts,
        estimated_in_app_recipients=estimate.in_app_recipients,
        estimated_telegram_recipients=estimate.telegram_recipients,
    )


@router.get("", response_model=AdminBroadcastListResponse)
async def list_admin_broadcasts(
    status_filter: BroadcastStatus | None = Query(default=None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminBroadcastListResponse:
    items, total = await list_broadcasts(
        session,
        limit=limit,
        offset=offset,
        status=status_filter,
    )
    response_items = [
        await _build_broadcast_response(session, item)
        for item in items
    ]
    return AdminBroadcastListResponse(
        items=response_items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=AdminBroadcastResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_broadcast(
    payload: AdminBroadcastUpsertRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> AdminBroadcastResponse:
    try:
        broadcast = await create_broadcast_draft(
            session,
            admin_id=current_admin.id,
            name=payload.name,
            title=payload.title,
            body_html=payload.body_html,
            content_type=payload.content_type,
            image_url=payload.image_url,
            channels=payload.channels,
            buttons=[button.model_dump() for button in payload.buttons],
            audience_segment=payload.audience.segment,
            audience_exclude_blocked=payload.audience.exclude_blocked,
        )
    except BroadcastValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await session.commit()
    await session.refresh(broadcast)
    return await _build_broadcast_response(session, broadcast)


@router.get("/runs", response_model=AdminBroadcastRunListResponse)
async def list_admin_broadcast_runs(
    broadcast_id: int | None = Query(default=None),
    status_filter: BroadcastRunStatus | None = Query(default=None, alias="status"),
    run_type: BroadcastRunType | None = Query(default=None),
    channel: BroadcastChannel | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminBroadcastRunListResponse:
    items, total = await list_broadcast_runs(
        session,
        limit=limit,
        offset=offset,
        broadcast_id=broadcast_id,
        status=status_filter,
        run_type=run_type,
        channel=channel,
    )
    return AdminBroadcastRunListResponse(
        items=[_build_run_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}", response_model=AdminBroadcastRunDetailResponse)
async def read_admin_broadcast_run(
    run_id: int,
    status_filter: BroadcastDeliveryStatus | None = Query(default=None, alias="status"),
    channel: BroadcastChannel | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminBroadcastRunDetailResponse:
    run = await get_broadcast_run(session, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="broadcast run not found")

    deliveries, total = await list_broadcast_run_deliveries(
        session,
        run_id=run_id,
        limit=limit,
        offset=offset,
        status=status_filter,
        channel=channel,
    )
    return AdminBroadcastRunDetailResponse(
        run=_build_run_response(run),
        deliveries=[
            AdminBroadcastRunDeliveryResponse(
                id=delivery.id,
                account_id=delivery.account_id,
                account_email=account.email,
                account_display_name=account.display_name,
                account_telegram_id=account.telegram_id,
                account_username=account.username,
                channel=delivery.channel,
                status=delivery.status,
                provider_message_id=delivery.provider_message_id,
                notification_id=delivery.notification_id,
                attempts_count=delivery.attempts_count,
                last_attempt_at=delivery.last_attempt_at,
                next_retry_at=delivery.next_retry_at,
                delivered_at=delivery.delivered_at,
                error_code=delivery.error_code,
                error_message=delivery.error_message,
                created_at=delivery.created_at,
                updated_at=delivery.updated_at,
            )
            for delivery, account in deliveries
        ],
        total_deliveries=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{broadcast_id}", response_model=AdminBroadcastResponse)
async def read_admin_broadcast(
    broadcast_id: int,
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminBroadcastResponse:
    broadcast = await get_broadcast(session, broadcast_id=broadcast_id)
    if broadcast is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="broadcast not found")
    return await _build_broadcast_response(session, broadcast)


@router.delete("/{broadcast_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_broadcast(
    broadcast_id: int,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> Response:
    try:
        await delete_broadcast_draft(
            session,
            broadcast_id=broadcast_id,
            admin_id=current_admin.id,
        )
    except BroadcastNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BroadcastConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{broadcast_id}/test-send", response_model=AdminBroadcastTestSendResponse)
async def test_send_admin_broadcast(
    broadcast_id: int,
    payload: AdminBroadcastTestSendRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> AdminBroadcastTestSendResponse:
    try:
        result = await send_broadcast_test(
            session,
            broadcast_id=broadcast_id,
            admin_id=current_admin.id,
            emails=payload.emails,
            telegram_ids=payload.telegram_ids,
            comment=payload.comment,
            idempotency_key=payload.idempotency_key,
        )
    except BroadcastNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BroadcastConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except BroadcastValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await session.commit()
    return AdminBroadcastTestSendResponse(
        broadcast_id=result.broadcast_id,
        audit_log_id=result.audit_log_id,
        total_targets=result.total_targets,
        sent_targets=result.sent_targets,
        partial_targets=result.partial_targets,
        failed_targets=result.failed_targets,
        skipped_targets=result.skipped_targets,
        resolved_account_targets=result.resolved_account_targets,
        direct_telegram_targets=result.direct_telegram_targets,
        in_app_notifications_created=result.in_app_notifications_created,
        telegram_targets_sent=result.telegram_targets_sent,
        items=[
            {
                "target": item.target,
                "source": item.source,
                "resolution": item.resolution,
                "status": item.status,
                "account_id": item.account_id,
                "telegram_id": item.telegram_id,
                "channels_attempted": item.channels_attempted,
                "in_app_notification_id": item.in_app_notification_id,
                "telegram_message_ids": item.telegram_message_ids,
                "detail": item.detail,
            }
            for item in result.items
        ],
    )


@router.post("/{broadcast_id}/send-now", response_model=AdminBroadcastResponse)
async def send_now_admin_broadcast(
    broadcast_id: int,
    payload: AdminBroadcastRuntimeActionRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(require_superuser_admin),
) -> AdminBroadcastResponse:
    try:
        broadcast = await launch_broadcast_now(
            session,
            broadcast_id=broadcast_id,
            admin_id=current_admin.id,
            comment=payload.comment,
            idempotency_key=payload.idempotency_key,
        )
    except BroadcastNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BroadcastConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except BroadcastValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await session.commit()
    await session.refresh(broadcast)
    return await _build_broadcast_response(session, broadcast)


@router.post("/{broadcast_id}/schedule", response_model=AdminBroadcastResponse)
async def schedule_admin_broadcast(
    broadcast_id: int,
    payload: AdminBroadcastScheduleRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(require_superuser_admin),
) -> AdminBroadcastResponse:
    try:
        broadcast = await schedule_broadcast_launch(
            session,
            broadcast_id=broadcast_id,
            admin_id=current_admin.id,
            scheduled_at=payload.scheduled_at,
            comment=payload.comment,
            idempotency_key=payload.idempotency_key,
        )
    except BroadcastNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BroadcastConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except BroadcastValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await session.commit()
    await session.refresh(broadcast)
    return await _build_broadcast_response(session, broadcast)


@router.post("/{broadcast_id}/pause", response_model=AdminBroadcastResponse)
async def pause_admin_broadcast(
    broadcast_id: int,
    payload: AdminBroadcastRuntimeActionRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(require_superuser_admin),
) -> AdminBroadcastResponse:
    try:
        broadcast = await pause_broadcast(
            session,
            broadcast_id=broadcast_id,
            admin_id=current_admin.id,
            comment=payload.comment,
            idempotency_key=payload.idempotency_key,
        )
    except BroadcastNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BroadcastConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await session.commit()
    await session.refresh(broadcast)
    return await _build_broadcast_response(session, broadcast)


@router.post("/{broadcast_id}/resume", response_model=AdminBroadcastResponse)
async def resume_admin_broadcast(
    broadcast_id: int,
    payload: AdminBroadcastRuntimeActionRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(require_superuser_admin),
) -> AdminBroadcastResponse:
    try:
        broadcast = await resume_broadcast(
            session,
            broadcast_id=broadcast_id,
            admin_id=current_admin.id,
            comment=payload.comment,
            idempotency_key=payload.idempotency_key,
        )
    except BroadcastNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BroadcastConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await session.commit()
    await session.refresh(broadcast)
    return await _build_broadcast_response(session, broadcast)


@router.post("/{broadcast_id}/cancel", response_model=AdminBroadcastResponse)
async def cancel_admin_broadcast(
    broadcast_id: int,
    payload: AdminBroadcastRuntimeActionRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(require_superuser_admin),
) -> AdminBroadcastResponse:
    try:
        broadcast = await cancel_broadcast(
            session,
            broadcast_id=broadcast_id,
            admin_id=current_admin.id,
            comment=payload.comment,
            idempotency_key=payload.idempotency_key,
        )
    except BroadcastNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BroadcastConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await session.commit()
    await session.refresh(broadcast)
    return await _build_broadcast_response(session, broadcast)


@router.put("/{broadcast_id}", response_model=AdminBroadcastResponse)
async def update_admin_broadcast(
    broadcast_id: int,
    payload: AdminBroadcastUpsertRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> AdminBroadcastResponse:
    try:
        broadcast = await update_broadcast_draft(
            session,
            broadcast_id=broadcast_id,
            admin_id=current_admin.id,
            name=payload.name,
            title=payload.title,
            body_html=payload.body_html,
            content_type=payload.content_type,
            image_url=payload.image_url,
            channels=payload.channels,
            buttons=[button.model_dump() for button in payload.buttons],
            audience_segment=payload.audience.segment,
            audience_exclude_blocked=payload.audience.exclude_blocked,
        )
    except BroadcastNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BroadcastConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except BroadcastValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await session.commit()
    await session.refresh(broadcast)
    return await _build_broadcast_response(session, broadcast)
