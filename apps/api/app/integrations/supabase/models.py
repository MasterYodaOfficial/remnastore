from typing import Any
from datetime import datetime

from pydantic import BaseModel, Field


class SupabaseIdentity(BaseModel):
    id: str | None = None
    provider: str
    identity_data: dict[str, Any] = Field(default_factory=dict)
    user_id: str | None = None

    @property
    def provider_uid(self) -> str | None:
        for key in ("sub", "provider_id", "id", "user_id"):
            value = self.identity_data.get(key)
            if isinstance(value, str) and value:
                return value

        if self.user_id:
            return self.user_id
        return self.id


class SupabaseUser(BaseModel):
    id: str
    email: str | None = None
    email_confirmed_at: datetime | None = None
    app_metadata: dict[str, Any] = Field(default_factory=dict)
    user_metadata: dict[str, Any] = Field(default_factory=dict)
    identities: list[SupabaseIdentity] = Field(default_factory=list)

    @property
    def display_name(self) -> str | None:
        for key in ("full_name", "name", "display_name", "user_name", "preferred_username"):
            value = self.user_metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @property
    def locale(self) -> str | None:
        for key in ("locale", "language", "preferred_language"):
            value = self.user_metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None