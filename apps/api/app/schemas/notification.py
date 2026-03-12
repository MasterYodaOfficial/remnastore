from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.db.models.notification import NotificationPriority, NotificationType


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: NotificationType
    title: str
    body: str
    priority: NotificationPriority
    payload: dict | None = None
    action_label: str | None = None
    action_url: str | None = None
    read_at: datetime | None = None
    is_read: bool = False
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _inject_is_read(cls, value: object) -> object:
        if hasattr(value, "read_at") and not isinstance(value, dict):
            return {
                "id": value.id,
                "type": value.type,
                "title": value.title,
                "body": value.body,
                "priority": value.priority,
                "payload": value.payload,
                "action_label": value.action_label,
                "action_url": value.action_url,
                "read_at": value.read_at,
                "is_read": value.read_at is not None,
                "created_at": value.created_at,
            }

        if isinstance(value, dict) and "is_read" not in value:
            value = dict(value)
            value["is_read"] = value.get("read_at") is not None
        return value


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    limit: int
    offset: int
    unread_count: int


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int


class NotificationMarkAllReadResponse(BaseModel):
    updated_count: int
