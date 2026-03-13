from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin
from app.db.models import Admin, BroadcastStatus
from app.db.session import get_session
from app.schemas.admin import (
    AdminBroadcastListResponse,
    AdminBroadcastResponse,
    AdminBroadcastUpsertRequest,
)
from app.services.broadcasts import (
    BroadcastConflictError,
    BroadcastNotFoundError,
    BroadcastValidationError,
    create_broadcast_draft,
    get_broadcast,
    list_broadcasts,
    update_broadcast_draft,
)


router = APIRouter()


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
    return AdminBroadcastListResponse(
        items=[
            AdminBroadcastResponse.model_validate(item, from_attributes=True)
            for item in items
        ],
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
    return AdminBroadcastResponse.model_validate(broadcast, from_attributes=True)


@router.get("/{broadcast_id}", response_model=AdminBroadcastResponse)
async def read_admin_broadcast(
    broadcast_id: int,
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminBroadcastResponse:
    broadcast = await get_broadcast(session, broadcast_id=broadcast_id)
    if broadcast is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="broadcast not found")
    return AdminBroadcastResponse.model_validate(broadcast, from_attributes=True)


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
    return AdminBroadcastResponse.model_validate(broadcast, from_attributes=True)
