from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.db.models.account import AccountStatus, AuthProvider
from app.db.models.ledger import LedgerEntryType
from app.db.models.withdrawal import WithdrawalDestinationType, WithdrawalStatus
from app.domain.payments import PaymentFlowType, PaymentProvider, PaymentStatus


class AdminResponse(BaseModel):
    id: UUID
    username: str
    email: str | None = None
    full_name: str | None = None
    is_active: bool
    is_superuser: bool
    last_login_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminLoginRequest(BaseModel):
    login: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)


class AdminAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin: AdminResponse


class AdminDashboardSummaryResponse(BaseModel):
    total_accounts: int
    active_subscriptions: int
    pending_withdrawals: int
    pending_payments: int


class AdminAccountSearchItemResponse(BaseModel):
    id: UUID
    email: str | None = None
    display_name: str | None = None
    telegram_id: int | None = None
    username: str | None = None
    status: AccountStatus
    balance: int
    subscription_status: str | None = None
    subscription_expires_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminAccountSearchResponse(BaseModel):
    items: list[AdminAccountSearchItemResponse]


class AdminAccountAuthIdentityResponse(BaseModel):
    provider: AuthProvider
    provider_uid: str
    email: str | None = None
    display_name: str | None = None
    linked_at: datetime

    model_config = {"from_attributes": True}


class AdminAccountLedgerEntryResponse(BaseModel):
    id: int
    entry_type: LedgerEntryType
    amount: int
    currency: str
    balance_before: int
    balance_after: int
    reference_type: str | None = None
    reference_id: str | None = None
    comment: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminAccountPaymentResponse(BaseModel):
    id: int
    provider: PaymentProvider
    flow_type: PaymentFlowType
    status: PaymentStatus
    amount: int
    currency: str
    plan_code: str | None = None
    description: str | None = None
    created_at: datetime
    finalized_at: datetime | None = None

    model_config = {"from_attributes": True}


class AdminAccountWithdrawalResponse(BaseModel):
    id: int
    amount: int
    destination_type: WithdrawalDestinationType
    destination_value: str
    status: WithdrawalStatus
    user_comment: str | None = None
    admin_comment: str | None = None
    created_at: datetime
    processed_at: datetime | None = None

    model_config = {"from_attributes": True}


class AdminAccountDetailResponse(BaseModel):
    id: UUID
    email: str | None = None
    display_name: str | None = None
    telegram_id: int | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    locale: str | None = None
    status: AccountStatus
    balance: int
    referral_code: str | None = None
    referral_earnings: int
    referrals_count: int
    referred_by_account_id: UUID | None = None
    remnawave_user_uuid: UUID | None = None
    subscription_url: str | None = None
    subscription_status: str | None = None
    subscription_expires_at: datetime | None = None
    subscription_last_synced_at: datetime | None = None
    subscription_is_trial: bool
    trial_used_at: datetime | None = None
    trial_ends_at: datetime | None = None
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    auth_accounts: list[AdminAccountAuthIdentityResponse]
    recent_ledger_entries: list[AdminAccountLedgerEntryResponse]
    recent_payments: list[AdminAccountPaymentResponse]
    recent_withdrawals: list[AdminAccountWithdrawalResponse]
    ledger_entries_count: int
    payments_count: int
    pending_payments_count: int
    withdrawals_count: int
    pending_withdrawals_count: int

    model_config = {"from_attributes": True}


class AdminBalanceAdjustmentRequest(BaseModel):
    amount: int
    comment: str = Field(..., min_length=1, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: int) -> int:
        if value == 0:
            raise ValueError("amount must be non-zero")
        return value

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("comment must not be blank")
        return value


class AdminBalanceAdjustmentResponse(BaseModel):
    account_id: UUID
    balance: int
    ledger_entry: AdminAccountLedgerEntryResponse


class AdminSubscriptionGrantRequest(BaseModel):
    plan_code: str = Field(..., min_length=1, max_length=64)
    comment: str = Field(..., min_length=1, max_length=500)
    idempotency_key: str = Field(..., min_length=1, max_length=255)

    @field_validator("plan_code", "comment", "idempotency_key")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class AdminSubscriptionGrantResponse(BaseModel):
    account_id: UUID
    plan_code: str
    subscription_grant_id: int
    audit_log_id: int
    subscription_status: str | None = None
    subscription_expires_at: datetime | None = None
    subscription_url: str | None = None
