from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.models import LedgerEntryType


class LedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: UUID
    entry_type: LedgerEntryType
    amount: int
    currency: str
    balance_before: int
    balance_after: int
    reference_type: str | None = None
    reference_id: str | None = None
    comment: str | None = None
    idempotency_key: str | None = None
    created_by_account_id: UUID | None = None
    created_by_admin_id: UUID | None = None
    created_at: datetime


class LedgerHistoryResponse(BaseModel):
    items: list[LedgerEntryResponse]
    total: int
    limit: int
    offset: int
