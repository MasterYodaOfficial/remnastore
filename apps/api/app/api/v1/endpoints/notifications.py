from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import api_error_from_exception
from app.api.dependencies import get_current_account
from app.db.models import Account
from app.db.session import get_session
from app.schemas.notification import (
    NotificationListResponse,
    NotificationMarkAllReadResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from app.services.notifications import (
    NotificationNotFoundError,
    get_account_notifications,
    get_account_unread_notifications_count,
    mark_all_notifications_read,
    mark_notification_read,
)


router = APIRouter()


@router.get("", response_model=NotificationListResponse)
async def read_notifications(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    unread_only: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> NotificationListResponse:
    items, total, unread_count = await get_account_notifications(
        session,
        account_id=current_account.id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )
    return NotificationListResponse(
        items=[
            NotificationResponse.model_validate(item, from_attributes=True)
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
        unread_count=unread_count,
    )


@router.get("/unread-count", response_model=NotificationUnreadCountResponse)
async def read_notifications_unread_count(
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> NotificationUnreadCountResponse:
    unread_count = await get_account_unread_notifications_count(
        session,
        account_id=current_account.id,
    )
    return NotificationUnreadCountResponse(unread_count=unread_count)


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def read_notification_mark_read(
    notification_id: int,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> NotificationResponse:
    try:
        notification = await mark_notification_read(
            session,
            account_id=current_account.id,
            notification_id=notification_id,
        )
    except NotificationNotFoundError as exc:
        raise api_error_from_exception(status.HTTP_404_NOT_FOUND, exc) from exc

    await session.commit()
    await session.refresh(notification)
    return NotificationResponse.model_validate(notification, from_attributes=True)


@router.post("/read-all", response_model=NotificationMarkAllReadResponse)
async def read_notifications_mark_all_read(
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> NotificationMarkAllReadResponse:
    updated_count = await mark_all_notifications_read(
        session,
        account_id=current_account.id,
    )
    await session.commit()
    return NotificationMarkAllReadResponse(updated_count=updated_count)
