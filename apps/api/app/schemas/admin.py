from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.db.models.account import AccountStatus, AuthProvider
from app.db.models.broadcast import (
    BroadcastAudienceSegment,
    BroadcastChannel,
    BroadcastContentType,
    BroadcastStatus,
)
from app.db.models.ledger import LedgerEntryType
from app.db.models.withdrawal import WithdrawalDestinationType, WithdrawalStatus
from app.domain.payments import PaymentFlowType, PaymentProvider, PaymentStatus
from app.services.broadcasts import BroadcastValidationError, validate_telegram_html_subset


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
    blocked_accounts: int
    new_accounts_last_7d: int
    total_wallet_balance: int
    total_referral_earnings: int
    pending_withdrawals_amount: int
    paid_withdrawals_amount_last_30d: int
    successful_payments_last_30d: int
    successful_payments_amount_last_30d: int
    wallet_topups_amount_last_30d: int
    direct_plan_revenue_last_30d: int


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
    idempotency_key: str | None = None
    created_by_account_id: UUID | None = None
    created_by_admin_id: UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminAccountLedgerHistoryResponse(BaseModel):
    items: list[AdminAccountLedgerEntryResponse]
    total: int
    limit: int
    offset: int


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


class AdminAccountStatusChangeRequest(BaseModel):
    status: AccountStatus
    comment: str = Field(..., min_length=1, max_length=500)
    idempotency_key: str = Field(..., min_length=1, max_length=255)

    @field_validator("comment", "idempotency_key")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class AdminAccountStatusChangeResponse(BaseModel):
    account_id: UUID
    previous_status: AccountStatus
    status: AccountStatus
    audit_log_id: int


class AdminWithdrawalQueueItemResponse(BaseModel):
    id: int
    account_id: UUID
    account_email: str | None = None
    account_display_name: str | None = None
    account_telegram_id: int | None = None
    account_username: str | None = None
    account_status: AccountStatus
    amount: int
    destination_type: WithdrawalDestinationType
    destination_value: str
    user_comment: str | None = None
    admin_comment: str | None = None
    status: WithdrawalStatus
    created_at: datetime
    processed_at: datetime | None = None


class AdminWithdrawalQueueResponse(BaseModel):
    items: list[AdminWithdrawalQueueItemResponse]
    total: int
    limit: int
    offset: int


class AdminWithdrawalStatusChangeRequest(BaseModel):
    status: WithdrawalStatus
    comment: str = Field(..., min_length=1, max_length=500)
    idempotency_key: str = Field(..., min_length=1, max_length=255)

    @field_validator("comment", "idempotency_key")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class AdminWithdrawalStatusChangeResponse(BaseModel):
    withdrawal_id: int
    account_id: UUID
    previous_status: WithdrawalStatus
    status: WithdrawalStatus
    admin_comment: str | None = None
    processed_at: datetime | None = None
    released_ledger_entry_id: int | None = None
    audit_log_id: int


class AdminBroadcastButtonRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=64)
    url: str = Field(..., min_length=1, max_length=1024)

    @field_validator("text", "url")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()


class AdminBroadcastButtonResponse(BaseModel):
    text: str
    url: str


class AdminBroadcastAudienceRequest(BaseModel):
    segment: BroadcastAudienceSegment = BroadcastAudienceSegment.ALL
    exclude_blocked: bool = True


class AdminBroadcastAudienceResponse(BaseModel):
    segment: BroadcastAudienceSegment
    exclude_blocked: bool


class AdminBroadcastUpsertRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    title: str = Field(..., min_length=1, max_length=255)
    body_html: str = Field(..., min_length=1, max_length=4096)
    content_type: BroadcastContentType = BroadcastContentType.TEXT
    image_url: str | None = Field(default=None, max_length=1024)
    channels: list[BroadcastChannel] = Field(default_factory=lambda: [BroadcastChannel.IN_APP])
    buttons: list[AdminBroadcastButtonRequest] = Field(default_factory=list)
    audience: AdminBroadcastAudienceRequest = Field(default_factory=AdminBroadcastAudienceRequest)

    @field_validator("name", "title")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()

    @field_validator("body_html")
    @classmethod
    def validate_body_html(cls, value: str) -> str:
        try:
            return validate_telegram_html_subset(value)
        except BroadcastValidationError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, value: list[BroadcastChannel]) -> list[BroadcastChannel]:
        if not value:
            raise ValueError("at least one channel is required")

        unique_channels: list[BroadcastChannel] = []
        for channel in value:
            if channel not in unique_channels:
                unique_channels.append(channel)
        return unique_channels

    @field_validator("buttons")
    @classmethod
    def validate_buttons_count(cls, value: list[AdminBroadcastButtonRequest]) -> list[AdminBroadcastButtonRequest]:
        if len(value) > 3:
            raise ValueError("buttons must contain at most 3 items")
        return value


class AdminBroadcastResponse(BaseModel):
    id: int
    name: str
    title: str
    body_html: str
    content_type: BroadcastContentType
    image_url: str | None = None
    channels: list[BroadcastChannel]
    buttons: list[AdminBroadcastButtonResponse]
    audience: AdminBroadcastAudienceResponse
    status: BroadcastStatus
    estimated_total_accounts: int
    estimated_in_app_recipients: int
    estimated_telegram_recipients: int
    created_by_admin_id: UUID
    updated_by_admin_id: UUID
    scheduled_at: datetime | None = None
    launched_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminBroadcastListResponse(BaseModel):
    items: list[AdminBroadcastResponse]
    total: int
    limit: int
    offset: int
