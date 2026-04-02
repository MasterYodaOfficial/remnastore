from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class RemnawaveNode(BaseModel):
    id: str
    name: str
    status: str | None = None


class RemnawaveWebhookUserData(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    uuid: UUID
    username: str | None = None
    status: str | None = None
    expire_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("expireAt", "expire_at"),
    )
    subscription_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("subscriptionUrl", "subscription_url"),
    )
    telegram_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("telegramId", "telegram_id"),
    )
    email: str | None = None
    tag: str | None = None
    online_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("onlineAt", "online_at"),
    )
    first_connected_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("firstConnectedAt", "first_connected_at"),
    )


class RemnawaveWebhookEnvelope(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    scope: str | None = None
    event: str
    timestamp: datetime | None = None
    data: Any = None

    @property
    def resolved_scope(self) -> str | None:
        if isinstance(self.scope, str):
            normalized_scope = self.scope.strip().lower()
            if normalized_scope:
                return normalized_scope

        prefix, separator, _ = self.event.partition(".")
        if separator:
            normalized_prefix = prefix.strip().lower()
            if normalized_prefix:
                return normalized_prefix
        return None
