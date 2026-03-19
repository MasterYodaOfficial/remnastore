from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.models.account import AccountStatus, AuthProvider
from app.db.models.broadcast import (
    BroadcastAudienceSegment,
    BroadcastChannel,
    BroadcastContentType,
    BroadcastDeliveryStatus,
    BroadcastRunStatus,
    BroadcastRunType,
    BroadcastStatus,
)
from app.db.models.ledger import LedgerEntryType
from app.db.models.promo import (
    PromoCampaignStatus,
    PromoEffectType,
    PromoRedemptionContext,
    PromoRedemptionStatus,
)
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


class AdminReferralChainReferrerResponse(BaseModel):
    account_id: UUID
    email: str | None = None
    display_name: str | None = None
    telegram_id: int | None = None
    username: str | None = None
    referral_code: str | None = None
    status: AccountStatus | None = None
    attributed_at: datetime


class AdminReferralChainItemResponse(BaseModel):
    attribution_id: int
    account_id: UUID
    email: str | None = None
    display_name: str | None = None
    telegram_id: int | None = None
    username: str | None = None
    referral_code: str | None = None
    status: AccountStatus | None = None
    subscription_status: str | None = None
    subscription_expires_at: datetime | None = None
    attributed_at: datetime
    reward_status: Literal["pending", "rewarded"]
    reward_amount: int
    reward_rate: float | None = None
    purchase_amount: int | None = None
    reward_created_at: datetime | None = None


class AdminReferralChainResponse(BaseModel):
    effective_reward_rate: float
    referrer: AdminReferralChainReferrerResponse | None = None
    direct_referrals: list[AdminReferralChainItemResponse]
    direct_referrals_count: int
    rewarded_direct_referrals_count: int
    pending_direct_referrals_count: int


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
    referral_chain: AdminReferralChainResponse
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


class AdminPromoCampaignCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    status: PromoCampaignStatus = PromoCampaignStatus.DRAFT
    effect_type: PromoEffectType
    effect_value: int
    currency: str = Field(default="RUB", min_length=1, max_length=8)
    plan_codes: list[str] | None = None
    first_purchase_only: bool = False
    requires_active_subscription: bool = False
    requires_no_active_subscription: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    total_redemptions_limit: int | None = Field(default=None, ge=1)
    per_account_redemptions_limit: int | None = Field(default=None, ge=1)

    @field_validator("name", "currency")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()

    @field_validator("description")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("plan_codes")
    @classmethod
    def validate_plan_codes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None

        normalized: list[str] = []
        for item in value:
            code = item.strip()
            if not code:
                raise ValueError("plan codes must not contain blank values")
            if code not in normalized:
                normalized.append(code)
        return normalized or None

    @model_validator(mode="after")
    def validate_window(self) -> "AdminPromoCampaignCreateRequest":
        if self.starts_at is not None and self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class AdminPromoCampaignResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    status: PromoCampaignStatus
    effect_type: PromoEffectType
    effect_value: int
    currency: str
    plan_codes: list[str] | None = None
    first_purchase_only: bool
    requires_active_subscription: bool
    requires_no_active_subscription: bool
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    total_redemptions_limit: int | None = None
    per_account_redemptions_limit: int | None = None
    created_by_admin_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    codes_count: int = 0
    redemptions_count: int = 0


class AdminPromoCampaignListResponse(BaseModel):
    items: list[AdminPromoCampaignResponse]
    total: int
    limit: int
    offset: int


class AdminPromoCampaignUpdateRequest(AdminPromoCampaignCreateRequest):
    pass


class AdminPromoCodeCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    max_redemptions: int | None = Field(default=None, ge=1)
    assigned_account_id: UUID | None = None
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("code must not be blank")
        return value.strip()


class AdminPromoCodeResponse(BaseModel):
    id: int
    campaign_id: int
    code: str
    is_active: bool
    assigned_account_id: UUID | None = None
    max_redemptions: int | None = None
    created_by_admin_id: UUID | None = None
    created_at: datetime
    redemptions_count: int = 0


class AdminPromoCodeListResponse(BaseModel):
    items: list[AdminPromoCodeResponse]
    total: int
    limit: int
    offset: int


class AdminPromoCodeUpdateRequest(BaseModel):
    max_redemptions: int | None = Field(default=None, ge=1)
    assigned_account_id: UUID | None = None
    is_active: bool = True


class AdminPromoCodeBatchCreateRequest(BaseModel):
    quantity: int = Field(..., ge=1, le=500)
    prefix: str | None = Field(default=None, max_length=32)
    suffix_length: int = Field(default=8, ge=4, le=24)
    max_redemptions: int | None = Field(default=None, ge=1)
    assigned_account_id: UUID | None = None
    is_active: bool = True

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AdminPromoCodeBatchCreateResponse(BaseModel):
    items: list["AdminPromoCodeResponse"]
    created_count: int


class AdminPromoCodeImportRequest(BaseModel):
    codes_text: str = Field(..., min_length=1, max_length=50000)
    max_redemptions: int | None = Field(default=None, ge=1)
    assigned_account_id: UUID | None = None
    is_active: bool = True
    skip_duplicates: bool = True

    @field_validator("codes_text")
    @classmethod
    def validate_codes_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("codes_text must not be blank")
        return normalized


class AdminPromoCodeImportResponse(BaseModel):
    items: list["AdminPromoCodeResponse"]
    created_count: int
    skipped_count: int
    skipped_codes: list[str]


class AdminPromoCodeExportResponse(BaseModel):
    items: list["AdminPromoCodeResponse"]
    exported_count: int


class AdminPromoRedemptionResponse(BaseModel):
    id: int
    campaign_id: int
    promo_code_id: int
    promo_code: str
    account_id: UUID
    status: PromoRedemptionStatus
    redemption_context: PromoRedemptionContext
    plan_code: str | None = None
    effect_type: PromoEffectType
    effect_value: int
    currency: str
    original_amount: int | None = None
    discount_amount: int | None = None
    final_amount: int | None = None
    granted_duration_days: int | None = None
    balance_credit_amount: int | None = None
    payment_id: int | None = None
    subscription_grant_id: int | None = None
    ledger_entry_id: int | None = None
    reference_type: str | None = None
    reference_id: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    applied_at: datetime | None = None


class AdminPromoRedemptionListResponse(BaseModel):
    items: list[AdminPromoRedemptionResponse]
    total: int
    limit: int
    offset: int


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
    manual_account_ids: list[UUID] = Field(default_factory=list)
    manual_emails: list[str] = Field(default_factory=list)
    manual_telegram_ids: list[int] = Field(default_factory=list)
    last_seen_older_than_days: int | None = Field(default=None, ge=1)
    include_never_seen: bool = False
    pending_payment_older_than_minutes: int | None = Field(default=None, ge=1)
    pending_payment_within_last_days: int | None = Field(default=None, ge=1)
    failed_payment_within_last_days: int | None = Field(default=None, ge=1)
    subscription_expired_from_days: int | None = Field(default=None, ge=0)
    subscription_expired_to_days: int | None = Field(default=None, ge=0)
    cooldown_days: int | None = Field(default=None, ge=1)
    cooldown_key: str | None = Field(default=None, min_length=1, max_length=64)
    telegram_quiet_hours_start: str | None = Field(default=None, min_length=1, max_length=5)
    telegram_quiet_hours_end: str | None = Field(default=None, min_length=1, max_length=5)

    @model_validator(mode="after")
    def validate_windows(self) -> "AdminBroadcastAudienceRequest":
        self.manual_account_ids = list(dict.fromkeys(self.manual_account_ids))
        normalized_manual_emails: list[str] = []
        seen_emails: set[str] = set()
        for item in self.manual_emails:
            normalized = item.strip().lower()
            if not normalized or normalized in seen_emails:
                continue
            seen_emails.add(normalized)
            normalized_manual_emails.append(normalized)
        self.manual_emails = normalized_manual_emails
        self.manual_telegram_ids = list(dict.fromkeys(int(item) for item in self.manual_telegram_ids))

        if (
            self.subscription_expired_from_days is not None
            and self.subscription_expired_to_days is not None
            and self.subscription_expired_from_days > self.subscription_expired_to_days
        ):
            raise ValueError(
                "subscription_expired_from_days must be <= subscription_expired_to_days"
            )
        if (self.cooldown_days is None) != (self.cooldown_key is None):
            raise ValueError("cooldown_days and cooldown_key must be provided together")
        if self.cooldown_key is not None:
            self.cooldown_key = self.cooldown_key.strip().lower()
        if (self.telegram_quiet_hours_start is None) != (self.telegram_quiet_hours_end is None):
            raise ValueError(
                "telegram_quiet_hours_start and telegram_quiet_hours_end must be provided together"
            )
        if self.telegram_quiet_hours_start is not None:
            self.telegram_quiet_hours_start = self.telegram_quiet_hours_start.strip()
        if self.telegram_quiet_hours_end is not None:
            self.telegram_quiet_hours_end = self.telegram_quiet_hours_end.strip()
        if (
            self.telegram_quiet_hours_start is not None
            and self.telegram_quiet_hours_end is not None
            and self.telegram_quiet_hours_start == self.telegram_quiet_hours_end
        ):
            raise ValueError("telegram quiet hours start and end must differ")
        if (
            self.segment == BroadcastAudienceSegment.MANUAL_LIST
            and not self.manual_account_ids
            and not self.manual_emails
            and not self.manual_telegram_ids
        ):
            raise ValueError("manual_list audience requires at least one account_id, email or telegram_id")
        if (
            self.segment in {
                BroadcastAudienceSegment.INACTIVE_ACCOUNTS,
                BroadcastAudienceSegment.INACTIVE_PAID_USERS,
            }
            and self.last_seen_older_than_days is None
        ):
            self.last_seen_older_than_days = 7
        return self


class AdminBroadcastAudienceResponse(BaseModel):
    segment: BroadcastAudienceSegment
    exclude_blocked: bool
    manual_account_ids: list[UUID] = Field(default_factory=list)
    manual_emails: list[str] = Field(default_factory=list)
    manual_telegram_ids: list[int] = Field(default_factory=list)
    last_seen_older_than_days: int | None = None
    include_never_seen: bool = False
    pending_payment_older_than_minutes: int | None = None
    pending_payment_within_last_days: int | None = None
    failed_payment_within_last_days: int | None = None
    subscription_expired_from_days: int | None = None
    subscription_expired_to_days: int | None = None
    cooldown_days: int | None = None
    cooldown_key: str | None = None
    telegram_quiet_hours_start: str | None = None
    telegram_quiet_hours_end: str | None = None


class AdminBroadcastEstimateRequest(BaseModel):
    channels: list[BroadcastChannel] = Field(default_factory=lambda: [BroadcastChannel.IN_APP])
    audience: AdminBroadcastAudienceRequest = Field(default_factory=AdminBroadcastAudienceRequest)

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


class AdminBroadcastEstimateResponse(BaseModel):
    channels: list[BroadcastChannel]
    audience: AdminBroadcastAudienceResponse
    estimated_total_accounts: int
    estimated_in_app_recipients: int
    estimated_telegram_recipients: int


class AdminBroadcastAudiencePreviewRequest(BaseModel):
    channels: list[BroadcastChannel] = Field(default_factory=lambda: [BroadcastChannel.IN_APP])
    audience: AdminBroadcastAudienceRequest = Field(default_factory=AdminBroadcastAudienceRequest)
    limit: int = Field(default=10, ge=1, le=50)

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


class AdminBroadcastAudiencePreviewItemResponse(BaseModel):
    account_id: UUID
    email: str | None = None
    display_name: str | None = None
    username: str | None = None
    telegram_id: int | None = None
    account_status: AccountStatus
    last_seen_at: datetime | None = None
    subscription_expires_at: datetime | None = None
    trial_ends_at: datetime | None = None
    delivery_channels: list[BroadcastChannel]
    delivery_notes: list[str]
    match_reasons: list[str]


class AdminBroadcastAudienceManualListExcludedAccountResponse(BaseModel):
    account_id: UUID
    email: str | None = None
    display_name: str | None = None
    username: str | None = None
    telegram_id: int | None = None
    account_status: AccountStatus
    matched_by: list[str]
    reasons: list[str]


class AdminBroadcastAudienceManualListDiagnosticsResponse(BaseModel):
    requested_account_ids: int
    requested_emails: int
    requested_telegram_ids: int
    matched_accounts: int
    final_accounts: int
    unresolved_account_ids_count: int
    unresolved_account_ids_sample: list[str]
    unresolved_emails_count: int
    unresolved_emails_sample: list[str]
    unresolved_telegram_ids_count: int
    unresolved_telegram_ids_sample: list[int]
    excluded_accounts_count: int
    excluded_blocked_count: int
    excluded_cooldown_count: int
    excluded_accounts_sample: list[AdminBroadcastAudienceManualListExcludedAccountResponse]


class AdminBroadcastAudiencePreviewResponse(BaseModel):
    channels: list[BroadcastChannel]
    audience: AdminBroadcastAudienceResponse
    total_accounts: int
    preview_count: int
    limit: int
    has_more: bool
    items: list[AdminBroadcastAudiencePreviewItemResponse]
    manual_list_diagnostics: AdminBroadcastAudienceManualListDiagnosticsResponse | None = None


class AdminBroadcastAudiencePresetUpsertRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    audience: AdminBroadcastAudienceRequest = Field(default_factory=AdminBroadcastAudienceRequest)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AdminBroadcastAudiencePresetResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    audience: AdminBroadcastAudienceResponse
    created_by_admin_id: UUID
    updated_by_admin_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminBroadcastAudiencePresetListResponse(BaseModel):
    items: list[AdminBroadcastAudiencePresetResponse]
    total: int
    limit: int
    offset: int


class AdminBroadcastTestSendRequest(BaseModel):
    emails: list[str] = Field(default_factory=list)
    telegram_ids: list[int] = Field(default_factory=list)
    comment: str = Field(..., min_length=1, max_length=500)
    idempotency_key: str = Field(..., min_length=1, max_length=255)

    @field_validator("emails")
    @classmethod
    def validate_emails(cls, value: list[str]) -> list[str]:
        normalized_items: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = item.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_items.append(normalized)
        return normalized_items

    @field_validator("telegram_ids")
    @classmethod
    def validate_telegram_ids(cls, value: list[int]) -> list[int]:
        normalized_items: list[int] = []
        seen: set[int] = set()
        for item in value:
            normalized = int(item)
            if normalized in seen:
                continue
            seen.add(normalized)
            normalized_items.append(normalized)
        return normalized_items

    @field_validator("comment", "idempotency_key")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def validate_has_targets(self) -> "AdminBroadcastTestSendRequest":
        if not self.emails and not self.telegram_ids:
            raise ValueError("at least one email or telegram_id target is required")
        return self


class AdminBroadcastTestSendTargetResponse(BaseModel):
    target: str
    source: Literal["email", "telegram_id"]
    resolution: Literal["account", "telegram_direct", "unresolved"]
    status: Literal["sent", "partial", "failed", "skipped"]
    account_id: UUID | None = None
    telegram_id: int | None = None
    channels_attempted: list[BroadcastChannel]
    in_app_notification_id: int | None = None
    telegram_message_ids: list[str]
    detail: str | None = None


class AdminBroadcastTestSendResponse(BaseModel):
    broadcast_id: int
    audit_log_id: int
    total_targets: int
    sent_targets: int
    partial_targets: int
    failed_targets: int
    skipped_targets: int
    resolved_account_targets: int
    direct_telegram_targets: int
    in_app_notifications_created: int
    telegram_targets_sent: int
    items: list[AdminBroadcastTestSendTargetResponse]


class AdminBroadcastRuntimeActionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(..., min_length=1, max_length=255)

    @field_validator("comment")
    @classmethod
    def validate_optional_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()


class AdminBroadcastScheduleRequest(AdminBroadcastRuntimeActionRequest):
    scheduled_at: datetime


class AdminBroadcastRunResponse(BaseModel):
    id: int
    broadcast_id: int
    run_type: BroadcastRunType
    status: BroadcastRunStatus
    triggered_by_admin_id: UUID
    snapshot_total_accounts: int
    snapshot_in_app_targets: int
    snapshot_telegram_targets: int
    total_deliveries: int
    pending_deliveries: int
    delivered_deliveries: int
    failed_deliveries: int
    skipped_deliveries: int
    in_app_delivered: int
    telegram_delivered: int
    in_app_pending: int
    telegram_pending: int
    started_at: datetime
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class AdminBroadcastRunListResponse(BaseModel):
    items: list[AdminBroadcastRunResponse]
    total: int
    limit: int
    offset: int


class AdminBroadcastRunDeliveryResponse(BaseModel):
    id: int
    account_id: UUID
    account_email: str | None = None
    account_display_name: str | None = None
    account_telegram_id: int | None = None
    account_username: str | None = None
    channel: BroadcastChannel
    status: BroadcastDeliveryStatus
    provider_message_id: str | None = None
    notification_id: int | None = None
    attempts_count: int
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
    delivered_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class AdminBroadcastRunDetailResponse(BaseModel):
    run: AdminBroadcastRunResponse
    deliveries: list[AdminBroadcastRunDeliveryResponse]
    total_deliveries: int
    limit: int
    offset: int


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
    latest_run: AdminBroadcastRunResponse | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminBroadcastListResponse(BaseModel):
    items: list[AdminBroadcastResponse]
    total: int
    limit: int
    offset: int
