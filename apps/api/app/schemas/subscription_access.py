from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SubscriptionAccessResponse(BaseModel):
    available: bool
    source: Literal["remote", "cache", "local_fallback", "none"]
    remnawave_user_uuid: UUID | None = None
    short_uuid: str | None = None
    username: str | None = None
    status: str | None = None
    expires_at: datetime | None = None
    is_active: bool = False
    days_left: int | None = None
    subscription_url: str | None = None
    links: list[str] = Field(default_factory=list)
    ssconf_links: dict[str, str] = Field(default_factory=dict)
    traffic_used_bytes: int | None = None
    traffic_limit_bytes: int | None = None
    lifetime_traffic_used_bytes: int | None = None
    refreshed_at: datetime
