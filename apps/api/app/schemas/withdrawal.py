from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.withdrawal import WithdrawalDestinationType, WithdrawalStatus


class WithdrawalCreateRequest(BaseModel):
    amount: int = Field(gt=0)
    destination_type: WithdrawalDestinationType
    destination_value: str
    user_comment: str | None = None


class WithdrawalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: int
    destination_type: WithdrawalDestinationType
    destination_value: str
    user_comment: str | None
    admin_comment: str | None
    status: WithdrawalStatus
    reserved_ledger_entry_id: int | None
    released_ledger_entry_id: int | None
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WithdrawalListResponse(BaseModel):
    items: list[WithdrawalResponse]
    total: int
    limit: int
    offset: int
    available_for_withdraw: int
    minimum_amount_rub: int
