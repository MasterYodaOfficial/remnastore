from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DeviceQuantityRequest(BaseModel):
    quantity: int = Field(ge=1, le=100)


class DevicePurchaseRequest(BaseModel):
    quote_token: str = Field(min_length=1, max_length=30000)
    idempotency_key: str = Field(min_length=1, max_length=128)


class DeviceRenewalRequest(BaseModel):
    extra_count: int = Field(ge=0, le=100)


class DeviceRemoveRequest(BaseModel):
    hwid: str = Field(min_length=1, max_length=512)


class DevicePlanQuoteRequest(BaseModel):
    extra_devices: int | None = Field(default=None, ge=0, le=100)
    promo_code: str | None = None


class DeviceItem(BaseModel):
    hwid: str
    platform: str | None = None
    os_version: str | None = None
    device_model: str | None = None
    user_agent: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DevicesStateResponse(BaseModel):
    base_limit: int
    extra_count: int
    renewal_extra_count: int
    limit: int
    devices: list[DeviceItem] | None
    expires_at: datetime | None
    can_purchase: bool
    sync_pending: bool
    is_active: bool
    limit_sync_status: Literal["synced", "pending", "unavailable", "conflict"]
    panel_limit: int | None
