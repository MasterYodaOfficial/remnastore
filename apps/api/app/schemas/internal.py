from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import (
    AccountStatus,
    BroadcastContentType,
    BroadcastRunStatus,
    BroadcastStatus,
)


class TelegramAccountAccessResponse(BaseModel):
    telegram_id: int
    exists: bool
    status: AccountStatus | None = None
    fully_blocked: bool
    telegram_bot_blocked: bool = False


class BotAdminBroadcastRequest(BaseModel):
    admin_telegram_id: int
    source_chat_id: int
    source_message_ids: list[int] = Field(..., min_length=1, max_length=100)
    media_group_id: str | None = None


class BotAdminBroadcastPreviewResponse(BaseModel):
    content_type: BroadcastContentType = BroadcastContentType.TELEGRAM_COPY
    telegram_message_ids: list[str]


class BotAdminBroadcastLaunchResponse(BaseModel):
    broadcast_id: int
    status: BroadcastStatus
    latest_run_status: BroadcastRunStatus | None = None
    estimated_telegram_recipients: int
    pending_deliveries: int = 0
    delivered_deliveries: int = 0
    failed_deliveries: int = 0
    skipped_deliveries: int = 0


class BotAdminBroadcastStatusItem(BaseModel):
    broadcast_id: int
    title: str
    content_type: BroadcastContentType
    status: BroadcastStatus
    latest_run_status: BroadcastRunStatus | None = None
    estimated_telegram_recipients: int
    pending_deliveries: int = 0
    delivered_deliveries: int = 0
    failed_deliveries: int = 0
    skipped_deliveries: int = 0
    updated_at: datetime
    launched_at: datetime | None = None


class BotAdminBroadcastStatusListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[BotAdminBroadcastStatusItem]
