import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { DashboardCard } from "./components/DashboardCard";
import { DetailFact } from "./components/DetailFact";
import { parseAdminApiErrorPayload } from "./lib/api-errors";
import {
  formatAccountIdentity,
  formatCompactId,
  parseManualAudienceTargetsInput,
  parseOptionalIntegerInput,
} from "./lib/admin-helpers";
import { t } from "./lib/i18n";
import { apiBaseUrl as API_BASE_URL } from "./runtime-config";

type AdminProfile = {
  id: string;
  username: string;
  email: string | null;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  last_login_at: string | null;
  created_at: string;
};

type AdminDashboardSummary = {
  total_accounts: number;
  active_subscriptions: number;
  accounts_with_telegram: number;
  paying_accounts_last_30d: number;
  pending_withdrawals: number;
  pending_payments: number;
  blocked_accounts: number;
  new_accounts_last_7d: number;
  total_wallet_balance: number;
  total_referral_earnings: number;
  pending_withdrawals_amount: number;
  paid_withdrawals_amount_last_30d: number;
  successful_payments_rub_last_30d: number;
  successful_payments_amount_rub_last_30d: number;
  wallet_topups_amount_last_30d: number;
  direct_plan_purchases_rub_last_30d: number;
  direct_plan_revenue_rub_last_30d: number;
  direct_plan_purchases_stars_last_30d: number;
  direct_plan_revenue_stars_last_30d: number;
};

type AdminAuthResponse = {
  access_token: string;
  token_type: string;
  admin: AdminProfile;
};

type AdminAccountListItem = {
  id: string;
  email: string | null;
  display_name: string | null;
  telegram_id: number | null;
  username: string | null;
  status: "active" | "blocked";
  balance: number;
  subscription_status: string | null;
  subscription_expires_at: string | null;
  referrals_count: number;
  last_seen_at: string | null;
  created_at: string;
};

type AdminAccountListResponse = {
  items: AdminAccountListItem[];
  total: number;
  limit: number;
  offset: number;
};

type AdminAccountAuthIdentity = {
  provider: string;
  provider_uid: string;
  email: string | null;
  display_name: string | null;
  linked_at: string;
};

type AdminAccountLedgerEntry = {
  id: number;
  entry_type: string;
  amount: number;
  currency: string;
  balance_before: number;
  balance_after: number;
  reference_type: string | null;
  reference_id: string | null;
  comment: string | null;
  idempotency_key: string | null;
  created_by_account_id: string | null;
  created_by_admin_id: string | null;
  created_at: string;
};

type AdminAccountLedgerHistoryResponse = {
  items: AdminAccountLedgerEntry[];
  total: number;
  limit: number;
  offset: number;
};

type AdminAccountEventLog = {
  id: number;
  account_id: string | null;
  actor_account_id: string | null;
  actor_admin_id: string | null;
  event_type: string;
  outcome: string;
  source: string | null;
  request_id: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
};

type AdminAccountEventLogHistoryResponse = {
  items: AdminAccountEventLog[];
  total: number;
  limit: number;
  offset: number;
};

type AdminEventAccountSnapshot = {
  id: string | null;
  email: string | null;
  display_name: string | null;
  telegram_id: number | null;
  username: string | null;
  status: "active" | "blocked" | null;
};

type AdminEventAdminSnapshot = {
  id: string | null;
  username: string | null;
  email: string | null;
  full_name: string | null;
};

type AdminGlobalAccountEventLog = {
  id: number;
  account_id: string | null;
  actor_account_id: string | null;
  actor_admin_id: string | null;
  event_type: string;
  outcome: string;
  source: string | null;
  request_id: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
  account: AdminEventAccountSnapshot | null;
  actor_account: AdminEventAccountSnapshot | null;
  actor_admin: AdminEventAdminSnapshot | null;
};

type AdminGlobalAccountEventLogHistoryResponse = {
  items: AdminGlobalAccountEventLog[];
  total: number;
  limit: number;
  offset: number;
};

type AdminAccountPayment = {
  id: number;
  provider: string;
  flow_type: string;
  status: string;
  amount: number;
  currency: string;
  plan_code: string | null;
  description: string | null;
  created_at: string;
  finalized_at: string | null;
};

type AdminAccountWithdrawal = {
  id: number;
  amount: number;
  destination_type: string;
  destination_value: string;
  status: string;
  user_comment: string | null;
  admin_comment: string | null;
  created_at: string;
  processed_at: string | null;
};

type AdminReferralChainReferrer = {
  account_id: string;
  email: string | null;
  display_name: string | null;
  telegram_id: number | null;
  username: string | null;
  referral_code: string | null;
  status: "active" | "blocked" | null;
  attributed_at: string;
};

type AdminReferralChainItem = {
  attribution_id: number;
  account_id: string;
  email: string | null;
  display_name: string | null;
  telegram_id: number | null;
  username: string | null;
  referral_code: string | null;
  status: "active" | "blocked" | null;
  subscription_status: string | null;
  subscription_expires_at: string | null;
  attributed_at: string;
  reward_status: "pending" | "rewarded";
  reward_amount: number;
  reward_rate: number | null;
  purchase_amount: number | null;
  reward_created_at: string | null;
};

type AdminReferralChain = {
  effective_reward_rate: number;
  referrer: AdminReferralChainReferrer | null;
  direct_referrals: AdminReferralChainItem[];
  direct_referrals_count: number;
  rewarded_direct_referrals_count: number;
  pending_direct_referrals_count: number;
};

type AdminAccountDetail = {
  id: string;
  email: string | null;
  display_name: string | null;
  telegram_id: number | null;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  locale: string | null;
  status: "active" | "blocked";
  balance: number;
  referral_code: string | null;
  referral_earnings: number;
  referrals_count: number;
  referred_by_account_id: string | null;
  referral_chain: AdminReferralChain;
  remnawave_user_uuid: string | null;
  subscription_url: string | null;
  subscription_status: string | null;
  subscription_expires_at: string | null;
  subscription_last_synced_at: string | null;
  subscription_is_trial: boolean;
  trial_used_at: string | null;
  trial_ends_at: string | null;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
  auth_accounts: AdminAccountAuthIdentity[];
  recent_ledger_entries: AdminAccountLedgerEntry[];
  recent_payments: AdminAccountPayment[];
  recent_withdrawals: AdminAccountWithdrawal[];
  ledger_entries_count: number;
  payments_count: number;
  pending_payments_count: number;
  withdrawals_count: number;
  pending_withdrawals_count: number;
};

type AdminBalanceAdjustmentResponse = {
  account_id: string;
  balance: number;
  ledger_entry: AdminAccountLedgerEntry;
};

type AdminSubscriptionPlan = {
  code: string;
  name: string;
  price_rub: number;
  price_stars: number | null;
  duration_days: number;
  features: string[];
  device_limit: number | null;
  popular: boolean;
};

type AdminSubscriptionGrantResponse = {
  account_id: string;
  plan_code: string;
  subscription_grant_id: number;
  audit_log_id: number;
  subscription_status: string | null;
  subscription_expires_at: string | null;
  subscription_url: string | null;
};

type AdminAccountStatusChangeResponse = {
  account_id: string;
  previous_status: "active" | "blocked";
  status: "active" | "blocked";
  audit_log_id: number;
};

type AdminWithdrawalQueueItem = {
  id: number;
  account_id: string;
  account_email: string | null;
  account_display_name: string | null;
  account_telegram_id: number | null;
  account_username: string | null;
  account_status: "active" | "blocked";
  amount: number;
  destination_type: string;
  destination_value: string;
  user_comment: string | null;
  admin_comment: string | null;
  status: "new" | "in_progress" | "paid" | "rejected" | "cancelled";
  created_at: string;
  processed_at: string | null;
};

type AdminWithdrawalQueueResponse = {
  items: AdminWithdrawalQueueItem[];
  total: number;
  limit: number;
  offset: number;
};

type AdminWithdrawalStatusChangeResponse = {
  withdrawal_id: number;
  account_id: string;
  previous_status: "new" | "in_progress" | "paid" | "rejected" | "cancelled";
  status: "new" | "in_progress" | "paid" | "rejected" | "cancelled";
  admin_comment: string | null;
  processed_at: string | null;
  released_ledger_entry_id: number | null;
  audit_log_id: number;
};

type AdminBroadcastButton = {
  text: string;
  url: string;
};

type AdminBroadcastAudience = {
  segment:
    | "all"
    | "active"
    | "with_telegram"
    | "paid"
    | "manual_list"
    | "inactive_accounts"
    | "inactive_paid_users"
    | "expired"
    | "abandoned_checkout"
    | "failed_payment"
    | "trial_ended_no_conversion"
    | "paid_before_not_active_now";
  exclude_blocked: boolean;
  manual_account_ids: string[];
  manual_emails: string[];
  manual_telegram_ids: number[];
  last_seen_older_than_days: number | null;
  include_never_seen: boolean;
  pending_payment_older_than_minutes: number | null;
  pending_payment_within_last_days: number | null;
  failed_payment_within_last_days: number | null;
  subscription_expired_from_days: number | null;
  subscription_expired_to_days: number | null;
  cooldown_days: number | null;
  cooldown_key: string | null;
  telegram_quiet_hours_start: string | null;
  telegram_quiet_hours_end: string | null;
};

type AdminBroadcast = {
  id: number;
  name: string;
  title: string;
  body_html: string;
  content_type: "text" | "photo";
  image_url: string | null;
  channels: ("in_app" | "telegram")[];
  buttons: AdminBroadcastButton[];
  audience: AdminBroadcastAudience;
  status: "draft" | "scheduled" | "running" | "paused" | "completed" | "failed" | "cancelled";
  estimated_total_accounts: number;
  estimated_in_app_recipients: number;
  estimated_telegram_recipients: number;
  created_by_admin_id: string;
  updated_by_admin_id: string;
  scheduled_at: string | null;
  launched_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  last_error: string | null;
  latest_run: AdminBroadcastRun | null;
  created_at: string;
  updated_at: string;
};

type AdminBroadcastListResponse = {
  items: AdminBroadcast[];
  total: number;
  limit: number;
  offset: number;
};

type AdminBroadcastEstimate = {
  channels: ("in_app" | "telegram")[];
  audience: AdminBroadcastAudience;
  estimated_total_accounts: number;
  estimated_in_app_recipients: number;
  estimated_telegram_recipients: number;
};

type AdminBroadcastAudiencePreviewItem = {
  account_id: string;
  email: string | null;
  display_name: string | null;
  username: string | null;
  telegram_id: number | null;
  account_status: "active" | "blocked";
  last_seen_at: string | null;
  subscription_expires_at: string | null;
  trial_ends_at: string | null;
  delivery_channels: ("in_app" | "telegram")[];
  delivery_notes: string[];
  match_reasons: string[];
};

type AdminBroadcastAudienceManualListExcludedAccount = {
  account_id: string;
  email: string | null;
  display_name: string | null;
  username: string | null;
  telegram_id: number | null;
  account_status: "active" | "blocked";
  matched_by: string[];
  reasons: string[];
};

type AdminBroadcastAudienceManualListDiagnostics = {
  requested_account_ids: number;
  requested_emails: number;
  requested_telegram_ids: number;
  matched_accounts: number;
  final_accounts: number;
  unresolved_account_ids_count: number;
  unresolved_account_ids_sample: string[];
  unresolved_emails_count: number;
  unresolved_emails_sample: string[];
  unresolved_telegram_ids_count: number;
  unresolved_telegram_ids_sample: number[];
  excluded_accounts_count: number;
  excluded_blocked_count: number;
  excluded_cooldown_count: number;
  excluded_accounts_sample: AdminBroadcastAudienceManualListExcludedAccount[];
};

type AdminBroadcastAudiencePreview = {
  channels: ("in_app" | "telegram")[];
  audience: AdminBroadcastAudience;
  total_accounts: number;
  preview_count: number;
  limit: number;
  has_more: boolean;
  items: AdminBroadcastAudiencePreviewItem[];
  manual_list_diagnostics: AdminBroadcastAudienceManualListDiagnostics | null;
};

type AdminBroadcastAudiencePreset = {
  id: number;
  name: string;
  description: string | null;
  channels: BroadcastChannel[];
  audience: AdminBroadcastAudience;
  created_by_admin_id: string;
  updated_by_admin_id: string;
  created_at: string;
  updated_at: string;
};

type AdminBroadcastAudiencePresetListResponse = {
  items: AdminBroadcastAudiencePreset[];
  total: number;
  limit: number;
  offset: number;
};

type BroadcastAudienceEditorState = {
  segment: BroadcastAudienceSegment;
  excludeBlocked: boolean;
  manualTargetsInput: string;
  lastSeenOlderThanDays: string;
  includeNeverSeen: boolean;
  pendingPaymentOlderThanMinutes: string;
  pendingPaymentWithinLastDays: string;
  failedPaymentWithinLastDays: string;
  subscriptionExpiredFromDays: string;
  subscriptionExpiredToDays: string;
  cooldownDays: string;
  cooldownKey: string;
  telegramQuietHoursStart: string;
  telegramQuietHoursEnd: string;
  sendInApp: boolean;
  sendTelegram: boolean;
};

type AdminBroadcastTestSendTargetResult = {
  target: string;
  source: "email" | "telegram_id";
  resolution: "account" | "telegram_direct" | "unresolved";
  status: "sent" | "partial" | "failed" | "skipped";
  account_id: string | null;
  telegram_id: number | null;
  channels_attempted: ("in_app" | "telegram")[];
  in_app_notification_id: number | null;
  telegram_message_ids: string[];
  detail: string | null;
};

type AdminBroadcastTestSendResponse = {
  broadcast_id: number;
  audit_log_id: number;
  total_targets: number;
  sent_targets: number;
  partial_targets: number;
  failed_targets: number;
  skipped_targets: number;
  resolved_account_targets: number;
  direct_telegram_targets: number;
  in_app_notifications_created: number;
  telegram_targets_sent: number;
  items: AdminBroadcastTestSendTargetResult[];
};

type AdminBroadcastRun = {
  id: number;
  broadcast_id: number;
  run_type: "send_now" | "scheduled";
  status: "running" | "paused" | "completed" | "failed" | "cancelled";
  triggered_by_admin_id: string;
  snapshot_total_accounts: number;
  snapshot_in_app_targets: number;
  snapshot_telegram_targets: number;
  total_deliveries: number;
  pending_deliveries: number;
  delivered_deliveries: number;
  failed_deliveries: number;
  skipped_deliveries: number;
  in_app_delivered: number;
  telegram_delivered: number;
  in_app_pending: number;
  telegram_pending: number;
  started_at: string;
  completed_at: string | null;
  cancelled_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

type AdminBroadcastRunListResponse = {
  items: AdminBroadcastRun[];
  total: number;
  limit: number;
  offset: number;
};

type AdminBroadcastRunDelivery = {
  id: number;
  account_id: string;
  account_email: string | null;
  account_display_name: string | null;
  account_telegram_id: number | null;
  account_username: string | null;
  channel: "in_app" | "telegram";
  status: "pending" | "delivered" | "failed" | "skipped";
  provider_message_id: string | null;
  notification_id: number | null;
  attempts_count: number;
  last_attempt_at: string | null;
  next_retry_at: string | null;
  delivered_at: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

type BroadcastButtonDraft = {
  id: string;
  text: string;
  url: string;
};

type PromoCampaignStatus = "draft" | "active" | "disabled" | "archived";
type PromoEffectType =
  | "percent_discount"
  | "fixed_discount"
  | "fixed_price"
  | "extra_days"
  | "free_days"
  | "balance_credit";
type PromoRedemptionStatus = "pending" | "applied" | "rejected" | "canceled";
type PromoRedemptionContext = "direct" | "plan_purchase" | "subscription_grant" | "balance_credit";

type AdminPromoCampaign = {
  id: number;
  name: string;
  description: string | null;
  status: PromoCampaignStatus;
  effect_type: PromoEffectType;
  effect_value: number;
  currency: string;
  plan_codes: string[] | null;
  first_purchase_only: boolean;
  requires_active_subscription: boolean;
  requires_no_active_subscription: boolean;
  starts_at: string | null;
  ends_at: string | null;
  total_redemptions_limit: number | null;
  per_account_redemptions_limit: number | null;
  created_by_admin_id: string | null;
  created_at: string;
  updated_at: string;
  codes_count: number;
  redemptions_count: number;
};

type AdminPromoCampaignListResponse = {
  items: AdminPromoCampaign[];
  total: number;
  limit: number;
  offset: number;
};

type AdminPromoCode = {
  id: number;
  campaign_id: number;
  code: string;
  is_active: boolean;
  assigned_account_id: string | null;
  max_redemptions: number | null;
  created_by_admin_id: string | null;
  created_at: string;
  redemptions_count: number;
};

type AdminPromoCodeListResponse = {
  items: AdminPromoCode[];
  total: number;
  limit: number;
  offset: number;
};

type AdminPromoCodeBatchCreateResponse = {
  items: AdminPromoCode[];
  created_count: number;
};

type AdminPromoCodeImportResponse = {
  items: AdminPromoCode[];
  created_count: number;
  skipped_count: number;
  skipped_codes: string[];
};

type AdminPromoCodeExportResponse = {
  items: AdminPromoCode[];
  exported_count: number;
};

type AdminPromoRedemption = {
  id: number;
  campaign_id: number;
  promo_code_id: number;
  promo_code: string;
  account_id: string;
  status: PromoRedemptionStatus;
  redemption_context: PromoRedemptionContext;
  plan_code: string | null;
  effect_type: PromoEffectType;
  effect_value: number;
  currency: string;
  original_amount: number | null;
  discount_amount: number | null;
  final_amount: number | null;
  granted_duration_days: number | null;
  balance_credit_amount: number | null;
  payment_id: number | null;
  subscription_grant_id: number | null;
  ledger_entry_id: number | null;
  reference_type: string | null;
  reference_id: string | null;
  failure_reason: string | null;
  created_at: string;
  applied_at: string | null;
};

type AdminPromoRedemptionListResponse = {
  items: AdminPromoRedemption[];
  total: number;
  limit: number;
  offset: number;
};

type BroadcastAudienceSegment = AdminBroadcastAudience["segment"];
type BroadcastContentType = AdminBroadcast["content_type"];
type BroadcastStatus = AdminBroadcast["status"];
type BroadcastChannel = AdminBroadcast["channels"][number];
type BroadcastRunStatus = AdminBroadcastRun["status"];
type BroadcastRunType = AdminBroadcastRun["run_type"];
type PromoCampaignFilter = PromoCampaignStatus | "all";
type PromoRedemptionStatusFilter = PromoRedemptionStatus | "all";
type PromoRedemptionContextFilter = PromoRedemptionContext | "all";

type GlobalEventSearchFilters = {
  eventType: AccountEventTypeFilterOption;
  outcome: AccountEventOutcomeFilterOption;
  source: AccountEventSourceFilterOption;
  requestId: string;
  accountId: string;
  actorAccountId: string;
  actorAdminId: string;
  telegramId: string;
};

type AccountListStatusFilter = "all" | "active" | "blocked";
type AccountListSubscriptionFilter = "all" | "active" | "inactive" | "none";
type AccountListSortBy =
  | "user"
  | "telegram_id"
  | "email"
  | "created_at"
  | "last_seen_at"
  | "balance"
  | "subscription_expires_at"
  | "referrals_count";
type AccountListSortOrder = "asc" | "desc";

type AccountListFilters = {
  userQuery: string;
  telegramQuery: string;
  emailQuery: string;
  status: AccountListStatusFilter;
  subscription: AccountListSubscriptionFilter;
  sortBy: AccountListSortBy;
  sortOrder: AccountListSortOrder;
};

type AdminView =
  | "dashboard"
  | "accounts"
  | "events"
  | "broadcasts"
  | "plans"
  | "withdrawals"
  | "promos";
const TOKEN_KEY = "remnastore_admin_token";
const ADMIN_ACCOUNT_LIST_PAGE_SIZE = 20;
const ACCOUNT_LIST_FILTER_DEBOUNCE_MS = 250;
const ADMIN_LEDGER_HISTORY_PAGE_SIZE = 20;
const ADMIN_ACCOUNT_EVENT_HISTORY_PAGE_SIZE = 20;
const BROADCAST_AUDIENCE_SEGMENTS = [
  "all",
  "active",
  "with_telegram",
  "paid",
  "manual_list",
  "inactive_accounts",
  "inactive_paid_users",
  "expired",
  "abandoned_checkout",
  "failed_payment",
  "trial_ended_no_conversion",
  "paid_before_not_active_now",
] as const;
const BROADCAST_AUDIENCE_PREVIEW_LIMIT = 10;
const BROADCAST_AUDIENCE_PRESET_LIMIT = 100;
const EMPTY_BROADCAST_AUDIENCE_EDITOR_STATE: BroadcastAudienceEditorState = {
  segment: "all",
  excludeBlocked: true,
  manualTargetsInput: "",
  lastSeenOlderThanDays: "",
  includeNeverSeen: false,
  pendingPaymentOlderThanMinutes: "",
  pendingPaymentWithinLastDays: "",
  failedPaymentWithinLastDays: "",
  subscriptionExpiredFromDays: "",
  subscriptionExpiredToDays: "",
  cooldownDays: "",
  cooldownKey: "",
  telegramQuietHoursStart: "",
  telegramQuietHoursEnd: "",
  sendInApp: true,
  sendTelegram: false,
};
const PROMO_CAMPAIGN_STATUS_OPTIONS = ["draft", "active", "disabled", "archived"] as const;
const PROMO_EFFECT_TYPE_OPTIONS = [
  "percent_discount",
  "fixed_discount",
  "fixed_price",
  "extra_days",
  "free_days",
  "balance_credit",
] as const;
const PROMO_REDEMPTION_STATUS_OPTIONS = ["pending", "applied", "rejected", "canceled"] as const;
const PROMO_REDEMPTION_CONTEXT_OPTIONS = [
  "direct",
  "plan_purchase",
  "subscription_grant",
  "balance_credit",
] as const;
const LEDGER_ENTRY_FILTER_OPTIONS = [
  "all",
  "topup_manual",
  "topup_payment",
  "subscription_debit",
  "referral_reward",
  "withdrawal_reserve",
  "withdrawal_release",
  "withdrawal_payout",
  "promo_credit",
  "refund",
  "admin_credit",
  "admin_debit",
  "merge_credit",
  "merge_debit",
] as const;
const ACCOUNT_EVENT_TYPE_FILTER_OPTIONS = [
  "all",
  "auth.telegram_webapp",
  "account.link.telegram_token.created",
  "account.link.browser_token.created",
  "account.link.telegram_confirmed",
  "account.link.browser_completed",
  "admin.account_status_change",
  "admin.balance_adjustment",
  "admin.subscription_grant",
  "admin.withdrawal.status_change",
  "payment.intent.created",
  "payment.topup.applied",
  "payment.finalized",
  "subscription.trial.activated",
  "subscription.remnawave.webhook",
  "subscription.wallet_purchase.staged",
  "subscription.wallet_purchase.applied",
  "subscription.direct_payment.staged",
  "subscription.direct_payment.applied",
  "withdrawal.created",
  "referral.claim",
  "referral.attributed",
  "referral.intent.apply",
  "referral.reward.granted",
] as const;
const ACCOUNT_EVENT_OUTCOME_FILTER_OPTIONS = ["all", "success", "failure", "denied", "error"] as const;
const ACCOUNT_EVENT_SOURCE_FILTER_OPTIONS = [
  "all",
  "api",
  "bot",
  "admin",
  "system",
  "webhook",
  "reconcile",
  "maintenance",
] as const;

type LedgerEntryFilterOption = (typeof LEDGER_ENTRY_FILTER_OPTIONS)[number];
type AccountEventTypeFilterOption = (typeof ACCOUNT_EVENT_TYPE_FILTER_OPTIONS)[number];
type AccountEventOutcomeFilterOption = (typeof ACCOUNT_EVENT_OUTCOME_FILTER_OPTIONS)[number];
type AccountEventSourceFilterOption = (typeof ACCOUNT_EVENT_SOURCE_FILTER_OPTIONS)[number];
const EMPTY_GLOBAL_EVENT_SEARCH_FILTERS: GlobalEventSearchFilters = {
  eventType: "all",
  outcome: "all",
  source: "all",
  requestId: "",
  accountId: "",
  actorAccountId: "",
  actorAdminId: "",
  telegramId: "",
};
const EMPTY_ACCOUNT_LIST_FILTERS: AccountListFilters = {
  userQuery: "",
  telegramQuery: "",
  emailQuery: "",
  status: "all",
  subscription: "all",
  sortBy: "created_at",
  sortOrder: "desc",
};

function normalizeAccountListFilters(filters: AccountListFilters): AccountListFilters {
  return {
    ...filters,
    userQuery: filters.userQuery.trim(),
    telegramQuery: filters.telegramQuery.trim(),
    emailQuery: filters.emailQuery.trim(),
  };
}

function getNextAccountListSortOrder(
  currentFilters: AccountListFilters,
  sortBy: AccountListSortBy,
  defaultOrder: AccountListSortOrder,
): AccountListSortOrder {
  if (currentFilters.sortBy !== sortBy) {
    return defaultOrder;
  }
  return currentFilters.sortOrder === "asc" ? "desc" : "asc";
}

function renderAccountSortIndicator(
  currentFilters: AccountListFilters,
  sortBy: AccountListSortBy,
): string {
  if (currentFilters.sortBy !== sortBy) {
    return "\u2195";
  }
  return currentFilters.sortOrder === "asc" ? "\u2191" : "\u2193";
}

function createBroadcastButtonDraft(button?: AdminBroadcastButton): BroadcastButtonDraft {
  const draftId =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`;

  return {
    id: draftId,
    text: button?.text || "",
    url: button?.url || "",
  };
}

function formatDate(value: string | null): string {
  if (!value) {
    return t("admin.common.noData");
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return t("admin.common.invalidDate");
  }

  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatDateMoscow(value: string | null): string {
  if (!value) {
    return t("admin.common.noData");
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return t("admin.common.invalidDate");
  }

  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Moscow",
  }).format(date);
}

function toMoscowDateTimeInputValue(value: string | null): string {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Moscow",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date);

  const lookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${lookup.year}-${lookup.month}-${lookup.day}T${lookup.hour}:${lookup.minute}`;
}

function formatMoney(value: number, currency = "RUB"): string {
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 0,
  }).format(value) + ` ${currency}`;
}

async function readErrorMessage(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) {
    return `HTTP ${response.status}`;
  }

  try {
    const parsed = JSON.parse(text) as unknown;
    return parseAdminApiErrorPayload(parsed, text).detail;
  } catch {
    return text;
  }
}

async function adminFetch<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

function getDownloadFilename(contentDisposition: string | null): string | null {
  if (!contentDisposition) {
    return null;
  }

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }

  const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  return plainMatch ? plainMatch[1] : null;
}

function humanizeAccountStatus(status: string): string {
  return status === "blocked" ? t("admin.common.blocked") : t("admin.common.active");
}

function humanizeAccountSubscriptionStatus(status: string | null): string {
  switch (status) {
    case null:
      return t("admin.accounts.table.subscriptionStatuses.none");
    case "active":
      return t("admin.accounts.table.subscriptionStatuses.active");
    case "inactive":
      return t("admin.accounts.table.subscriptionStatuses.inactive");
    case "expired":
      return t("admin.accounts.table.subscriptionStatuses.expired");
    default:
      return status;
  }
}

function humanizePaymentStatus(status: string): string {
  switch (status) {
    case "created":
      return t("admin.payments.statuses.created");
    case "pending":
      return t("admin.payments.statuses.pending");
    case "requires_action":
      return t("admin.payments.statuses.requiresAction");
    case "succeeded":
      return t("admin.payments.statuses.succeeded");
    case "failed":
      return t("admin.payments.statuses.failed");
    case "cancelled":
      return t("admin.payments.statuses.cancelled");
    case "expired":
      return t("admin.payments.statuses.expired");
    default:
      return status;
  }
}

function humanizePaymentFlow(flow: string): string {
  return flow === "wallet_topup"
    ? t("admin.payments.flows.walletTopup")
    : t("admin.payments.flows.planPurchase");
}

function humanizeLedgerType(entryType: string): string {
  switch (entryType) {
    case "topup_manual":
      return t("admin.payments.ledgerTypes.topupManual");
    case "topup_payment":
      return t("admin.payments.ledgerTypes.topupPayment");
    case "subscription_debit":
      return t("admin.payments.ledgerTypes.subscriptionDebit");
    case "referral_reward":
      return t("admin.payments.ledgerTypes.referralReward");
    case "withdrawal_reserve":
      return t("admin.payments.ledgerTypes.withdrawalReserve");
    case "withdrawal_release":
      return t("admin.payments.ledgerTypes.withdrawalRelease");
    case "withdrawal_payout":
      return t("admin.payments.ledgerTypes.withdrawalPayout");
    case "promo_credit":
      return t("admin.payments.ledgerTypes.promoCredit");
    case "refund":
      return t("admin.payments.ledgerTypes.refund");
    case "admin_credit":
      return t("admin.payments.ledgerTypes.adminCredit");
    case "admin_debit":
      return t("admin.payments.ledgerTypes.adminDebit");
    case "merge_credit":
      return t("admin.payments.ledgerTypes.mergeCredit");
    case "merge_debit":
      return t("admin.payments.ledgerTypes.mergeDebit");
    default:
      return entryType;
  }
}

function humanizeLedgerEntryFilter(entryType: LedgerEntryFilterOption): string {
  if (entryType === "all") {
    return t("admin.payments.allTypes");
  }
  return humanizeLedgerType(entryType);
}

function describeLedgerEntryContext(entry: AdminAccountLedgerEntry): string {
  const context: string[] = [];

  if (entry.reference_type || entry.reference_id) {
    context.push(`${entry.reference_type || t("admin.payments.reference")} ${entry.reference_id || ""}`.trim());
  }
  if (entry.created_by_admin_id) {
    context.push(t("admin.payments.createdByAdmin"));
  } else if (entry.created_by_account_id) {
    context.push(t("admin.payments.createdByAccount"));
  }
  if (entry.idempotency_key) {
    context.push(`${t("admin.payments.idempotencyKey")} ${entry.idempotency_key}`);
  }

  return context.join(" · ");
}

function humanizeAccountEventType(eventType: string): string {
  switch (eventType) {
    case "auth.telegram_webapp":
      return t("admin.payments.eventTypes.authTelegramWebapp");
    case "account.link.telegram_token.created":
      return t("admin.payments.eventTypes.linkTelegramTokenCreated");
    case "account.link.browser_token.created":
      return t("admin.payments.eventTypes.linkBrowserTokenCreated");
    case "account.link.telegram_confirmed":
      return t("admin.payments.eventTypes.linkTelegramConfirmed");
    case "account.link.browser_completed":
      return t("admin.payments.eventTypes.linkBrowserCompleted");
    case "admin.account_status_change":
      return t("admin.payments.eventTypes.adminAccountStatusChange");
    case "admin.balance_adjustment":
      return t("admin.payments.eventTypes.adminBalanceAdjustment");
    case "admin.subscription_grant":
      return t("admin.payments.eventTypes.adminSubscriptionGrant");
    case "admin.withdrawal.status_change":
      return t("admin.payments.eventTypes.adminWithdrawalStatusChange");
    case "payment.intent.created":
      return t("admin.payments.eventTypes.paymentIntentCreated");
    case "payment.topup.applied":
      return t("admin.payments.eventTypes.paymentTopupApplied");
    case "payment.finalized":
      return t("admin.payments.eventTypes.paymentFinalized");
    case "subscription.trial.activated":
      return t("admin.payments.eventTypes.trialActivated");
    case "subscription.remnawave.webhook":
      return t("admin.payments.eventTypes.remnawaveWebhook");
    case "subscription.wallet_purchase.staged":
      return t("admin.payments.eventTypes.walletPurchaseStaged");
    case "subscription.wallet_purchase.applied":
      return t("admin.payments.eventTypes.walletPurchaseApplied");
    case "subscription.direct_payment.staged":
      return t("admin.payments.eventTypes.directPaymentStaged");
    case "subscription.direct_payment.applied":
      return t("admin.payments.eventTypes.directPaymentApplied");
    case "withdrawal.created":
      return t("admin.payments.eventTypes.withdrawalCreated");
    case "referral.claim":
      return t("admin.payments.eventTypes.referralClaim");
    case "referral.attributed":
      return t("admin.payments.eventTypes.referralAttributed");
    case "referral.intent.apply":
      return t("admin.payments.eventTypes.referralIntentApply");
    case "referral.reward.granted":
      return t("admin.payments.eventTypes.referralRewardGranted");
    default:
      return eventType;
  }
}

function humanizeAccountEventOutcome(outcome: string): string {
  switch (outcome) {
    case "success":
      return t("admin.payments.eventOutcomes.success");
    case "failure":
      return t("admin.payments.eventOutcomes.failure");
    case "denied":
      return t("admin.payments.eventOutcomes.denied");
    case "error":
      return t("admin.payments.eventOutcomes.error");
    default:
      return outcome;
  }
}

function humanizeAccountEventSource(source: string | null): string {
  switch (source) {
    case null:
      return t("admin.common.notSpecified");
    case "api":
      return t("admin.payments.eventSources.api");
    case "bot":
      return t("admin.payments.eventSources.bot");
    case "admin":
      return t("admin.payments.eventSources.admin");
    case "system":
      return t("admin.payments.eventSources.system");
    case "webhook":
      return t("admin.payments.eventSources.webhook");
    case "reconcile":
      return t("admin.payments.eventSources.reconcile");
    case "maintenance":
      return t("admin.payments.eventSources.maintenance");
    default:
      return source;
  }
}

function getAccountEventOutcomePillClass(outcome: string): string {
  switch (outcome) {
    case "success":
      return "status-pill--paid";
    case "failure":
    case "denied":
    case "error":
      return "status-pill--failed";
    default:
      return "status-pill--pending";
  }
}

function formatAccountEventPayloadValue(value: unknown): string {
  if (value === null) {
    return "null";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    const preview = value.slice(0, 3).map((item) => formatAccountEventPayloadValue(item)).join(", ");
    return value.length > 3 ? `${preview}, +${value.length - 3}` : preview;
  }
  try {
    return JSON.stringify(value) || String(value);
  } catch {
    return String(value);
  }
}

function summarizeAccountEventPayload(payload: Record<string, unknown> | null): string | null {
  if (!payload) {
    return null;
  }

  const preferredKeys = [
    "comment",
    "reason",
    "plan_code",
    "amount",
    "currency",
    "status",
    "previous_status",
    "payment_id",
    "withdrawal_id",
    "subscription_grant_id",
    "referral_code",
    "provider",
    "telegram_id",
  ];
  const entries = [
    ...preferredKeys
      .filter((key) => key in payload)
      .map((key) => [key, payload[key]] as const),
    ...Object.entries(payload).filter(([key]) => !preferredKeys.includes(key)),
  ];
  const parts: string[] = [];

  for (const [key, value] of entries) {
    if (parts.length >= 3) {
      break;
    }
    if (value === undefined || value === null || typeof value === "object") {
      continue;
    }
    parts.push(`${key}: ${formatAccountEventPayloadValue(value)}`);
  }

  if (parts.length > 0) {
    return parts.join(" · ");
  }

  return JSON.stringify(payload) || null;
}

function describeAccountEventActor(event: AdminAccountEventLog): string {
  if (event.actor_admin_id) {
    return t("admin.events.actorAdmin", { id: formatCompactId(event.actor_admin_id) });
  }
  if (event.actor_account_id) {
    return t("admin.events.actorAccount", { id: formatCompactId(event.actor_account_id) });
  }
  return t("admin.common.actorMissing");
}

function normalizeGlobalEventSearchFilters(filters: GlobalEventSearchFilters): GlobalEventSearchFilters {
  return {
    eventType: filters.eventType,
    outcome: filters.outcome,
    source: filters.source,
    requestId: filters.requestId.trim(),
    accountId: filters.accountId.trim(),
    actorAccountId: filters.actorAccountId.trim(),
    actorAdminId: filters.actorAdminId.trim(),
    telegramId: filters.telegramId.trim(),
  };
}

function formatAdminIdentity(admin: AdminEventAdminSnapshot | null): string {
  if (!admin) {
    return t("admin.common.adminMissing");
  }
  return admin.full_name || admin.username || admin.email || admin.id || t("admin.common.staff");
}

function describeGlobalEventTargetAccount(event: AdminGlobalAccountEventLog): string {
  if (event.account) {
    return formatAccountIdentity(event.account);
  }
  if (event.account_id) {
    return t("admin.events.actorAccount", { id: formatCompactId(event.account_id) });
  }
  return t("admin.common.targetAccountMissing");
}

function describeGlobalEventActor(event: AdminGlobalAccountEventLog): string {
  if (event.actor_admin) {
    return formatAdminIdentity(event.actor_admin);
  }
  if (event.actor_account) {
    return formatAccountIdentity(event.actor_account);
  }
  if (event.actor_admin_id) {
    return t("admin.events.actorAdmin", { id: formatCompactId(event.actor_admin_id) });
  }
  if (event.actor_account_id) {
    return t("admin.events.actorAccount", { id: formatCompactId(event.actor_account_id) });
  }
  return t("admin.common.actorMissing");
}

function humanizeWithdrawalStatus(status: string): string {
  switch (status) {
    case "new":
      return t("admin.withdrawals.statuses.new");
    case "in_progress":
      return t("admin.withdrawals.statuses.inProgress");
    case "paid":
      return t("admin.withdrawals.statuses.paid");
    case "rejected":
      return t("admin.withdrawals.statuses.rejected");
    case "cancelled":
      return t("admin.withdrawals.statuses.cancelled");
    default:
      return status;
  }
}

function humanizeWithdrawalDestinationType(destinationType: string): string {
  switch (destinationType) {
    case "card":
      return t("admin.withdrawals.destinations.card");
    case "sbp":
      return t("admin.withdrawals.destinations.sbp");
    default:
      return destinationType;
  }
}

function humanizeBroadcastStatus(status: BroadcastStatus): string {
  switch (status) {
    case "draft":
      return t("admin.broadcasts.statuses.draft");
    case "scheduled":
      return t("admin.broadcasts.statuses.scheduled");
    case "running":
      return t("admin.broadcasts.statuses.running");
    case "paused":
      return t("admin.broadcasts.statuses.paused");
    case "completed":
      return t("admin.broadcasts.statuses.completed");
    case "failed":
      return t("admin.broadcasts.statuses.failed");
    case "cancelled":
      return t("admin.broadcasts.statuses.cancelled");
    default:
      return status;
  }
}

function humanizeBroadcastAudienceSegment(segment: BroadcastAudienceSegment): string {
  switch (segment) {
    case "all":
      return t("admin.broadcasts.segments.all");
    case "active":
      return t("admin.broadcasts.segments.active");
    case "with_telegram":
      return t("admin.broadcasts.segments.withTelegram");
    case "paid":
      return t("admin.broadcasts.segments.paid");
    case "manual_list":
      return t("admin.broadcasts.segments.manualList");
    case "inactive_accounts":
      return t("admin.broadcasts.segments.inactiveAccounts");
    case "inactive_paid_users":
      return t("admin.broadcasts.segments.inactivePaidUsers");
    case "expired":
      return t("admin.broadcasts.segments.expired");
    case "abandoned_checkout":
      return t("admin.broadcasts.segments.abandonedCheckout");
    case "failed_payment":
      return t("admin.broadcasts.segments.failedPayment");
    case "trial_ended_no_conversion":
      return t("admin.broadcasts.segments.trialEndedNoConversion");
    case "paid_before_not_active_now":
      return t("admin.broadcasts.segments.paidBeforeNotActiveNow");
    default:
      return segment;
  }
}

function formatBroadcastAudienceSummary(audience: AdminBroadcastAudience): string {
  const parts = [humanizeBroadcastAudienceSegment(audience.segment)];

  if (audience.segment === "manual_list") {
    if (audience.manual_account_ids.length > 0) {
      parts.push(t("admin.broadcasts.summary.manualAccountIds", { count: audience.manual_account_ids.length }));
    }
    if (audience.manual_emails.length > 0) {
      parts.push(t("admin.broadcasts.summary.manualEmails", { count: audience.manual_emails.length }));
    }
    if (audience.manual_telegram_ids.length > 0) {
      parts.push(t("admin.broadcasts.summary.manualTelegramIds", { count: audience.manual_telegram_ids.length }));
    }
  } else if (
    audience.segment === "inactive_accounts" ||
    audience.segment === "inactive_paid_users"
  ) {
    if (audience.last_seen_older_than_days !== null) {
      parts.push(
        t("admin.broadcasts.summary.inactiveOlderThanDays", { days: audience.last_seen_older_than_days }),
      );
    }
    if (audience.include_never_seen) {
      parts.push(t("admin.broadcasts.summary.includeNeverSeen"));
    }
  } else if (audience.segment === "abandoned_checkout") {
    if (audience.pending_payment_older_than_minutes !== null) {
      parts.push(
        t("admin.broadcasts.summary.pendingFromMinutes", {
          minutes: audience.pending_payment_older_than_minutes,
        }),
      );
    }
    if (audience.pending_payment_within_last_days !== null) {
      parts.push(
        t("admin.broadcasts.summary.pendingWithinDays", {
          days: audience.pending_payment_within_last_days,
        }),
      );
    }
  } else if (audience.segment === "failed_payment") {
    if (audience.failed_payment_within_last_days !== null) {
      parts.push(
        t("admin.broadcasts.summary.failedWithinDays", {
          days: audience.failed_payment_within_last_days,
        }),
      );
    }
  } else if (audience.segment === "expired") {
    if (audience.subscription_expired_from_days !== null || audience.subscription_expired_to_days !== null) {
      const fromDays = audience.subscription_expired_from_days;
      const toDays = audience.subscription_expired_to_days;
      if (fromDays !== null && toDays !== null) {
        parts.push(t("admin.broadcasts.summary.expiredFromToDays", { fromDays, toDays }));
      } else if (fromDays !== null) {
        parts.push(t("admin.broadcasts.summary.expiredFromDays", { days: fromDays }));
      } else if (toDays !== null) {
        parts.push(t("admin.broadcasts.summary.expiredToDays", { days: toDays }));
      }
    }
  }

  if (audience.cooldown_days !== null && audience.cooldown_key !== null) {
    parts.push(t("admin.broadcasts.summary.cooldownDays", { days: audience.cooldown_days }));
    parts.push(t("admin.broadcasts.summary.cooldownFamily", { key: audience.cooldown_key }));
  }
  if (audience.telegram_quiet_hours_start !== null && audience.telegram_quiet_hours_end !== null) {
    parts.push(
      t("admin.broadcasts.summary.quietHours", {
        start: audience.telegram_quiet_hours_start,
        end: audience.telegram_quiet_hours_end,
      }),
    );
  }

  return parts.join(" · ");
}

function humanizeBroadcastChannel(channel: BroadcastChannel): string {
  return channel === "telegram"
    ? t("admin.broadcasts.channels.telegram")
    : t("admin.broadcasts.channels.inApp");
}

function humanizeBroadcastChannels(channels: BroadcastChannel[]): string {
  return channels.map((channel) => humanizeBroadcastChannel(channel)).join(" + ");
}

function buildBroadcastChannels(sendInApp: boolean, sendTelegram: boolean): BroadcastChannel[] {
  const channels: BroadcastChannel[] = [];
  if (sendInApp) {
    channels.push("in_app");
  }
  if (sendTelegram) {
    channels.push("telegram");
  }
  return channels;
}

function createBroadcastAudienceEditorState(
  audience: AdminBroadcastAudience,
  channels: BroadcastChannel[],
): BroadcastAudienceEditorState {
  return {
    segment: audience.segment,
    excludeBlocked: audience.exclude_blocked,
    manualTargetsInput: [
      ...audience.manual_account_ids,
      ...audience.manual_emails,
      ...audience.manual_telegram_ids.map((item) => String(item)),
    ].join("\n"),
    lastSeenOlderThanDays:
      audience.last_seen_older_than_days !== null ? String(audience.last_seen_older_than_days) : "",
    includeNeverSeen: audience.include_never_seen,
    pendingPaymentOlderThanMinutes:
      audience.pending_payment_older_than_minutes !== null
        ? String(audience.pending_payment_older_than_minutes)
        : "",
    pendingPaymentWithinLastDays:
      audience.pending_payment_within_last_days !== null
        ? String(audience.pending_payment_within_last_days)
        : "",
    failedPaymentWithinLastDays:
      audience.failed_payment_within_last_days !== null
        ? String(audience.failed_payment_within_last_days)
        : "",
    subscriptionExpiredFromDays:
      audience.subscription_expired_from_days !== null
        ? String(audience.subscription_expired_from_days)
        : "",
    subscriptionExpiredToDays:
      audience.subscription_expired_to_days !== null
        ? String(audience.subscription_expired_to_days)
        : "",
    cooldownDays: audience.cooldown_days !== null ? String(audience.cooldown_days) : "",
    cooldownKey: audience.cooldown_key || "",
    telegramQuietHoursStart: audience.telegram_quiet_hours_start || "",
    telegramQuietHoursEnd: audience.telegram_quiet_hours_end || "",
    sendInApp: channels.includes("in_app"),
    sendTelegram: channels.includes("telegram"),
  };
}

function buildBroadcastAudiencePayloadFromEditor(
  editor: BroadcastAudienceEditorState,
): AdminBroadcastAudience {
  const audience: AdminBroadcastAudience = {
    segment: editor.segment,
    exclude_blocked: editor.excludeBlocked,
    manual_account_ids: [],
    manual_emails: [],
    manual_telegram_ids: [],
    last_seen_older_than_days: null,
    include_never_seen: false,
    pending_payment_older_than_minutes: null,
    pending_payment_within_last_days: null,
    failed_payment_within_last_days: null,
    subscription_expired_from_days: null,
    subscription_expired_to_days: null,
    cooldown_days: null,
    cooldown_key: null,
    telegram_quiet_hours_start: null,
    telegram_quiet_hours_end: null,
  };

  if (editor.segment === "manual_list") {
    const parsedManualTargets = parseManualAudienceTargetsInput(editor.manualTargetsInput);
    if (
      parsedManualTargets.manualAccountIds.length === 0 &&
      parsedManualTargets.manualEmails.length === 0 &&
      parsedManualTargets.manualTelegramIds.length === 0
    ) {
      throw new Error("Для ручного списка добавь хотя бы один ID аккаунта, email или Telegram ID");
    }
    audience.manual_account_ids = parsedManualTargets.manualAccountIds;
    audience.manual_emails = parsedManualTargets.manualEmails;
    audience.manual_telegram_ids = parsedManualTargets.manualTelegramIds;
  } else if (editor.segment === "inactive_accounts" || editor.segment === "inactive_paid_users") {
    audience.last_seen_older_than_days = parseOptionalIntegerInput(
      editor.lastSeenOlderThanDays,
      1,
      "Давность неактивности",
    );
    audience.include_never_seen = editor.includeNeverSeen;
  } else if (editor.segment === "abandoned_checkout") {
    audience.pending_payment_older_than_minutes = parseOptionalIntegerInput(
      editor.pendingPaymentOlderThanMinutes,
      1,
      "Минимальная давность незавершенного платежа",
    );
    audience.pending_payment_within_last_days = parseOptionalIntegerInput(
      editor.pendingPaymentWithinLastDays,
      1,
      "Окно поиска незавершенного платежа",
    );
  } else if (editor.segment === "failed_payment") {
    audience.failed_payment_within_last_days = parseOptionalIntegerInput(
      editor.failedPaymentWithinLastDays,
      1,
      "Окно поиска неуспешной оплаты",
    );
  } else if (editor.segment === "expired") {
    audience.subscription_expired_from_days = parseOptionalIntegerInput(
      editor.subscriptionExpiredFromDays,
      0,
      "Нижняя граница давности окончания подписки",
    );
    audience.subscription_expired_to_days = parseOptionalIntegerInput(
      editor.subscriptionExpiredToDays,
      0,
      "Верхняя граница давности окончания подписки",
    );
    if (
      audience.subscription_expired_from_days !== null &&
      audience.subscription_expired_to_days !== null &&
      audience.subscription_expired_from_days > audience.subscription_expired_to_days
    ) {
      throw new Error("Для истекшей подписки нижняя граница не может быть больше верхней");
    }
  }

  const cooldownDays = parseOptionalIntegerInput(
    editor.cooldownDays,
    1,
    "Пауза между повторными отправками",
  );
  const cooldownKey = editor.cooldownKey.trim().toLowerCase() || null;
  if ((cooldownDays === null) !== (cooldownKey === null)) {
    throw new Error("Для паузы между повторными отправками укажи и срок в днях, и название группы");
  }
  audience.cooldown_days = cooldownDays;
  audience.cooldown_key = cooldownKey;

  const telegramQuietHoursStart = editor.telegramQuietHoursStart.trim() || null;
  const telegramQuietHoursEnd = editor.telegramQuietHoursEnd.trim() || null;
  if ((telegramQuietHoursStart === null) !== (telegramQuietHoursEnd === null)) {
    throw new Error("Для тихих часов Telegram нужно указать и начало, и конец окна");
  }
  if (
    telegramQuietHoursStart !== null &&
    telegramQuietHoursEnd !== null &&
    telegramQuietHoursStart === telegramQuietHoursEnd
  ) {
    throw new Error("Начало и конец тихих часов Telegram не должны совпадать");
  }
  audience.telegram_quiet_hours_start = telegramQuietHoursStart;
  audience.telegram_quiet_hours_end = telegramQuietHoursEnd;

  return audience;
}

function normalizeBroadcastAudienceForComparison(audience: AdminBroadcastAudience): string {
  return JSON.stringify({
    ...audience,
    manual_account_ids: [...audience.manual_account_ids].sort(),
    manual_emails: [...audience.manual_emails].sort(),
    manual_telegram_ids: [...audience.manual_telegram_ids].sort((left, right) => left - right),
  });
}

function hasSameBroadcastAudiencePresetSelection(
  preset: AdminBroadcastAudiencePreset,
  channels: BroadcastChannel[],
  audience: AdminBroadcastAudience,
): boolean {
  return (
    JSON.stringify([...preset.channels].sort()) === JSON.stringify([...channels].sort()) &&
    normalizeBroadcastAudienceForComparison(preset.audience) === normalizeBroadcastAudienceForComparison(audience)
  );
}

function formatRewardRate(value: number): string {
  return `${new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 2,
  }).format(value)}%`;
}

function humanizeReferralRewardStatus(status: AdminReferralChainItem["reward_status"]): string {
  return status === "rewarded"
    ? t("admin.broadcasts.referralRewardStatuses.rewarded")
    : t("admin.broadcasts.referralRewardStatuses.pending");
}

function humanizeBroadcastRunType(runType: BroadcastRunType): string {
  return runType === "scheduled"
    ? t("admin.broadcasts.runTypes.scheduled")
    : t("admin.broadcasts.runTypes.immediate");
}

function humanizeBroadcastRunStatus(status: BroadcastRunStatus): string {
  switch (status) {
    case "running":
      return t("admin.broadcasts.runStatuses.running");
    case "paused":
      return t("admin.broadcasts.runStatuses.paused");
    case "completed":
      return t("admin.broadcasts.runStatuses.completed");
    case "failed":
      return t("admin.broadcasts.runStatuses.failed");
    case "cancelled":
      return t("admin.broadcasts.runStatuses.cancelled");
    default:
      return status;
  }
}

function humanizePromoCampaignStatus(status: PromoCampaignStatus): string {
  switch (status) {
    case "draft":
      return t("admin.promos.campaignStatuses.draft");
    case "active":
      return t("admin.promos.campaignStatuses.active");
    case "disabled":
      return t("admin.promos.campaignStatuses.disabled");
    case "archived":
      return t("admin.promos.campaignStatuses.archived");
    default:
      return status;
  }
}

function humanizePromoEffectType(effectType: PromoEffectType): string {
  switch (effectType) {
    case "percent_discount":
      return t("admin.promos.effectTypes.percentDiscount");
    case "fixed_discount":
      return t("admin.promos.effectTypes.fixedDiscount");
    case "fixed_price":
      return t("admin.promos.effectTypes.fixedPrice");
    case "extra_days":
      return t("admin.promos.effectTypes.extraDays");
    case "free_days":
      return t("admin.promos.effectTypes.freeDays");
    case "balance_credit":
      return t("admin.promos.effectTypes.balanceCredit");
    default:
      return effectType;
  }
}

function promoCampaignStatusPillClass(status: PromoCampaignStatus): string {
  switch (status) {
    case "active":
      return "status-pill status-pill--active";
    case "draft":
      return "status-pill status-pill--draft";
    case "disabled":
      return "status-pill status-pill--cancelled";
    case "archived":
      return "status-pill status-pill--blocked";
    default:
      return "status-pill";
  }
}

function describePromoEffect(effectType: PromoEffectType, effectValue: number, currency: string): string {
  switch (effectType) {
    case "percent_discount":
      return `-${effectValue}%`;
    case "fixed_discount":
      return `-${formatMoney(effectValue, currency)}`;
    case "fixed_price":
      return t("admin.promos.effectDescriptions.fixedPrice", {
        price: formatMoney(effectValue, currency),
      });
    case "extra_days":
      return t("admin.promos.effectDescriptions.extraDays", { days: effectValue });
    case "free_days":
      return t("admin.promos.effectDescriptions.freeDays", { days: effectValue });
    case "balance_credit":
      return `+${formatMoney(effectValue, currency)}`;
    default:
      return String(effectValue);
  }
}

function describePromoCampaignWindow(campaign: Pick<AdminPromoCampaign, "starts_at" | "ends_at">): string {
  if (!campaign.starts_at && !campaign.ends_at) {
    return t("admin.promos.window.none");
  }
  if (campaign.starts_at && campaign.ends_at) {
    return `${formatDateMoscow(campaign.starts_at)} - ${formatDateMoscow(campaign.ends_at)}`;
  }
  if (campaign.starts_at) {
    return t("admin.promos.window.from", { date: formatDateMoscow(campaign.starts_at) });
  }
  return t("admin.promos.window.until", { date: formatDateMoscow(campaign.ends_at) });
}

function humanizePromoRedemptionStatus(status: PromoRedemptionStatus): string {
  switch (status) {
    case "pending":
      return t("admin.promos.redemptionStatuses.pending");
    case "applied":
      return t("admin.promos.redemptionStatuses.applied");
    case "rejected":
      return t("admin.promos.redemptionStatuses.rejected");
    case "canceled":
      return t("admin.promos.redemptionStatuses.canceled");
    default:
      return status;
  }
}

function promoRedemptionStatusPillClass(status: PromoRedemptionStatus): string {
  switch (status) {
    case "applied":
      return "status-pill status-pill--active";
    case "pending":
      return "status-pill status-pill--pending";
    case "rejected":
    case "canceled":
      return "status-pill status-pill--cancelled";
    default:
      return "status-pill";
  }
}

function humanizePromoRedemptionContext(context: PromoRedemptionContext): string {
  switch (context) {
    case "direct":
      return t("admin.promos.redemptionContexts.direct");
    case "plan_purchase":
      return t("admin.promos.redemptionContexts.planPurchase");
    case "subscription_grant":
      return t("admin.promos.redemptionContexts.subscriptionGrant");
    case "balance_credit":
      return t("admin.promos.redemptionContexts.balanceCredit");
    default:
      return context;
  }
}

function describePromoRedemptionOutcome(redemption: AdminPromoRedemption): string {
  if (redemption.final_amount !== null && redemption.original_amount !== null) {
    const discountPart =
      redemption.discount_amount !== null && redemption.discount_amount > 0
        ? t("admin.promos.redemptionOutcome.discountPart", {
            discount: formatMoney(redemption.discount_amount, redemption.currency),
          })
        : "";
    return `${formatMoney(redemption.original_amount, redemption.currency)} -> ${formatMoney(redemption.final_amount, redemption.currency)}${discountPart}`;
  }
  if (redemption.granted_duration_days !== null) {
    return t("admin.promos.redemptionOutcome.grantedDays", {
      days: redemption.granted_duration_days,
    });
  }
  if (redemption.balance_credit_amount !== null) {
    return t("admin.promos.redemptionOutcome.balanceCredit", {
      amount: formatMoney(redemption.balance_credit_amount, redemption.currency),
    });
  }
  return describePromoEffect(redemption.effect_type, redemption.effect_value, redemption.currency);
}

function describePromoSubscriptionRequirement(campaign: AdminPromoCampaign): string {
  if (campaign.requires_active_subscription) {
    return t("admin.promos.workspace.campaignDetail.subscriptionRequirement.active");
  }
  if (campaign.requires_no_active_subscription) {
    return t("admin.promos.workspace.campaignDetail.subscriptionRequirement.inactive");
  }
  return t("admin.promos.workspace.campaignDetail.subscriptionRequirement.any");
}

function describePromoPlanScope(planCodes: string[] | null): string {
  return planCodes?.length ? planCodes.join(", ") : t("admin.promos.workspace.common.allPlans");
}

function describePromoLimit(limit: number | null): string {
  return limit === null ? t("admin.promos.workspace.common.unlimited") : String(limit);
}

function describePromoCodeAssignment(accountId: string | null): string {
  if (!accountId) {
    return t("admin.promos.workspace.codeTable.noBinding");
  }
  return t("admin.promos.workspace.codeTable.accountBinding", {
    accountId: formatCompactId(accountId),
  });
}

function describePromoCodeLimit(limit: number | null): string {
  if (limit === null) {
    return t("admin.promos.workspace.codeTable.noLimit");
  }
  return t("admin.promos.workspace.codeTable.limitValue", { count: limit });
}

function describePromoCodeStatus(isActive: boolean): string {
  return isActive
    ? t("admin.promos.workspace.codeTable.statusActive")
    : t("admin.promos.workspace.codeTable.statusInactive");
}

function describePromoRedemptionReference(redemption: AdminPromoRedemption): string {
  if (redemption.failure_reason) {
    return t("admin.promos.workspace.redemptions.referenceFailure", {
      reason: redemption.failure_reason,
    });
  }
  if (redemption.reference_type || redemption.reference_id) {
    return t("admin.promos.workspace.redemptions.referenceValue", {
      reference: `${redemption.reference_type || t("admin.promos.workspace.redemptions.referenceFallback")} ${redemption.reference_id || ""}`.trim(),
    });
  }
  return t("admin.promos.workspace.redemptions.referenceEmpty");
}

function buildMoscowScheduleIso(value: string): string {
  const normalized = value.trim();
  if (!normalized) {
    return normalized;
  }
  return `${normalized}:00+03:00`;
}

function renderBroadcastPreviewHtml(html: string): string {
  return html.replace(/\n/g, "<br />");
}

function formatPlanFeaturesInput(features: string[]): string {
  return features.join("\n");
}

function parsePlanFeaturesInput(value: string): string[] {
  const normalized: string[] = [];
  const seen = new Set<string>();
  for (const rawLine of value.split("\n")) {
    const feature = rawLine.trim();
    if (!feature || seen.has(feature)) {
      continue;
    }
    normalized.push(feature);
    seen.add(feature);
  }
  return normalized;
}

function formatPlanDuration(days: number): string {
  return t("admin.plans.table.durationValue", { days });
}

function formatPlanStarsPrice(price: number | null): string {
  if (price === null) {
    return t("admin.plans.table.starsEmpty");
  }
  return `${price} XTR`;
}

function formatPlanDeviceLimit(value: number | null): string {
  if (value === null) {
    return t("admin.plans.table.deviceLimitEmpty");
  }
  return t("admin.plans.table.deviceLimitValue", { count: value });
}

function summarizePlanFeatures(features: string[]): string {
  if (features.length === 0) {
    return t("admin.common.noData");
  }

  const preview = features.slice(0, 2).join(" · ");
  const remaining = features.length - 2;
  if (remaining <= 0) {
    return preview;
  }
  return `${preview} ${t("admin.plans.table.moreFeatures", { count: remaining })}`;
}

export default function App() {
  const [token, setToken] = useState<string>(() => localStorage.getItem(TOKEN_KEY) || "");
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [summary, setSummary] = useState<AdminDashboardSummary | null>(null);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState<boolean>(Boolean(token));
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<AdminView>("dashboard");
  const [accountItems, setAccountItems] = useState<AdminAccountListItem[]>([]);
  const [accountTotal, setAccountTotal] = useState(0);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [accountsLoadingMore, setAccountsLoadingMore] = useState(false);
  const [accountsExporting, setAccountsExporting] = useState(false);
  const [accountListDraftFilters, setAccountListDraftFilters] =
    useState<AccountListFilters>({ ...EMPTY_ACCOUNT_LIST_FILTERS });
  const [accountListFilters, setAccountListFilters] =
    useState<AccountListFilters>({ ...EMPTY_ACCOUNT_LIST_FILTERS });
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<AdminAccountDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [ledgerHistoryItems, setLedgerHistoryItems] = useState<AdminAccountLedgerEntry[]>([]);
  const [ledgerHistoryTotal, setLedgerHistoryTotal] = useState(0);
  const [ledgerHistoryFilter, setLedgerHistoryFilter] = useState<LedgerEntryFilterOption>("all");
  const [ledgerHistoryLoading, setLedgerHistoryLoading] = useState(false);
  const [ledgerHistoryLoadingMore, setLedgerHistoryLoadingMore] = useState(false);
  const [accountEventHistoryItems, setAccountEventHistoryItems] = useState<AdminAccountEventLog[]>([]);
  const [accountEventHistoryTotal, setAccountEventHistoryTotal] = useState(0);
  const [accountEventTypeFilter, setAccountEventTypeFilter] =
    useState<AccountEventTypeFilterOption>("all");
  const [accountEventOutcomeFilter, setAccountEventOutcomeFilter] =
    useState<AccountEventOutcomeFilterOption>("all");
  const [accountEventSourceFilter, setAccountEventSourceFilter] =
    useState<AccountEventSourceFilterOption>("all");
  const [accountEventRequestIdInput, setAccountEventRequestIdInput] = useState("");
  const [accountEventRequestIdFilter, setAccountEventRequestIdFilter] = useState("");
  const [accountEventHistoryLoading, setAccountEventHistoryLoading] = useState(false);
  const [accountEventHistoryLoadingMore, setAccountEventHistoryLoadingMore] = useState(false);
  const [globalEventSearchDraft, setGlobalEventSearchDraft] = useState<GlobalEventSearchFilters>({
    ...EMPTY_GLOBAL_EVENT_SEARCH_FILTERS,
  });
  const [globalEventSearchFilters, setGlobalEventSearchFilters] = useState<GlobalEventSearchFilters>({
    ...EMPTY_GLOBAL_EVENT_SEARCH_FILTERS,
  });
  const [globalEventItems, setGlobalEventItems] = useState<AdminGlobalAccountEventLog[]>([]);
  const [globalEventTotal, setGlobalEventTotal] = useState(0);
  const [selectedGlobalEventId, setSelectedGlobalEventId] = useState<number | null>(null);
  const [globalEventLoading, setGlobalEventLoading] = useState(false);
  const [globalEventLoadingMore, setGlobalEventLoadingMore] = useState(false);
  const [subscriptionPlans, setSubscriptionPlans] = useState<AdminSubscriptionPlan[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);
  const [selectedCatalogPlanCode, setSelectedCatalogPlanCode] = useState<string | null>(null);
  const [planSubmitting, setPlanSubmitting] = useState(false);
  const [planDeleting, setPlanDeleting] = useState(false);
  const [planEditorCode, setPlanEditorCode] = useState("");
  const [planEditorName, setPlanEditorName] = useState("");
  const [planEditorPriceRub, setPlanEditorPriceRub] = useState("");
  const [planEditorPriceStars, setPlanEditorPriceStars] = useState("");
  const [planEditorDurationDays, setPlanEditorDurationDays] = useState("");
  const [planEditorDeviceLimit, setPlanEditorDeviceLimit] = useState("");
  const [planEditorPopular, setPlanEditorPopular] = useState(false);
  const [planEditorFeaturesInput, setPlanEditorFeaturesInput] = useState("");
  const [balanceAdjustmentAmount, setBalanceAdjustmentAmount] = useState("");
  const [balanceAdjustmentComment, setBalanceAdjustmentComment] = useState("");
  const [balanceSubmitting, setBalanceSubmitting] = useState(false);
  const [subscriptionGrantPlanCode, setSubscriptionGrantPlanCode] = useState("");
  const [subscriptionGrantComment, setSubscriptionGrantComment] = useState("");
  const [subscriptionSubmitting, setSubscriptionSubmitting] = useState(false);
  const [statusChangeComment, setStatusChangeComment] = useState("");
  const [statusSubmitting, setStatusSubmitting] = useState(false);
  const [withdrawalItems, setWithdrawalItems] = useState<AdminWithdrawalQueueItem[]>([]);
  const [withdrawalTotal, setWithdrawalTotal] = useState(0);
  const [selectedWithdrawalId, setSelectedWithdrawalId] = useState<number | null>(null);
  const [withdrawalsLoading, setWithdrawalsLoading] = useState(false);
  const [withdrawalComment, setWithdrawalComment] = useState("");
  const [withdrawalSubmitting, setWithdrawalSubmitting] = useState(false);
  const [broadcastItems, setBroadcastItems] = useState<AdminBroadcast[]>([]);
  const [broadcastTotal, setBroadcastTotal] = useState(0);
  const [selectedBroadcastId, setSelectedBroadcastId] = useState<number | null>(null);
  const [broadcastSelectionMode, setBroadcastSelectionMode] = useState<"existing" | "new">("existing");
  const [selectedBroadcast, setSelectedBroadcast] = useState<AdminBroadcast | null>(null);
  const [broadcastsLoading, setBroadcastsLoading] = useState(false);
  const [broadcastSubmitting, setBroadcastSubmitting] = useState(false);
  const [broadcastEstimate, setBroadcastEstimate] = useState<AdminBroadcastEstimate | null>(null);
  const [broadcastEstimateLoading, setBroadcastEstimateLoading] = useState(false);
  const [broadcastEstimateError, setBroadcastEstimateError] = useState<string | null>(null);
  const [, setBroadcastAudiencePreview] = useState<AdminBroadcastAudiencePreview | null>(null);
  const [, setBroadcastAudiencePreviewLoading] = useState(false);
  const [, setBroadcastAudiencePreviewError] = useState<string | null>(null);
  const [broadcastAudiencePresetItems, setBroadcastAudiencePresetItems] = useState<AdminBroadcastAudiencePreset[]>([]);
  const [broadcastAudiencePresetTotal, setBroadcastAudiencePresetTotal] = useState(0);
  const [selectedBroadcastAudiencePresetId, setSelectedBroadcastAudiencePresetId] = useState<number | null>(null);
  const [broadcastAudiencePresetLoading, setBroadcastAudiencePresetLoading] = useState(false);
  const [broadcastAudiencePresetSubmitting, setBroadcastAudiencePresetSubmitting] = useState(false);
  const [broadcastAudiencePresetError, setBroadcastAudiencePresetError] = useState<string | null>(null);
  const [broadcastAudiencePresetName, setBroadcastAudiencePresetName] = useState("");
  const [broadcastAudiencePresetDescription, setBroadcastAudiencePresetDescription] = useState("");
  const [broadcastAudiencePresetEditor, setBroadcastAudiencePresetEditor] = useState<BroadcastAudienceEditorState>({
    ...EMPTY_BROADCAST_AUDIENCE_EDITOR_STATE,
  });
  const [, setBroadcastTestEmailsInput] = useState("");
  const [, setBroadcastTestTelegramIdsInput] = useState("");
  const [, setBroadcastTestComment] = useState("");
  const [, setBroadcastTestSubmitting] = useState(false);
  const [, setBroadcastTestResult] = useState<AdminBroadcastTestSendResponse | null>(null);
  const [broadcastRuntimeComment, setBroadcastRuntimeComment] = useState("");
  const [broadcastScheduleAtInput, setBroadcastScheduleAtInput] = useState("");
  const [broadcastRuntimeSubmitting, setBroadcastRuntimeSubmitting] = useState(false);
  const [, setBroadcastRunItems] = useState<AdminBroadcastRun[]>([]);
  const [broadcastRunTotal, setBroadcastRunTotal] = useState(0);
  const [, setSelectedBroadcastRunId] = useState<number | null>(null);
  const [, setSelectedBroadcastRun] = useState<AdminBroadcastRun | null>(null);
  const [, setBroadcastRunsLoading] = useState(false);
  const [, setBroadcastRunDetailLoading] = useState(false);
  const [, setBroadcastRunDeliveries] = useState<AdminBroadcastRunDelivery[]>([]);
  const [, setBroadcastRunDeliveriesTotal] = useState(0);
  const [, setBroadcastRunStatusFilter] = useState<BroadcastRunStatus | "all">("all");
  const [, setBroadcastRunTypeFilter] = useState<BroadcastRunType | "all">("all");
  const [, setBroadcastRunChannelFilter] = useState<BroadcastChannel | "all">("all");
  const [broadcastName, setBroadcastName] = useState("");
  const [broadcastTitle, setBroadcastTitle] = useState("");
  const [broadcastBodyHtml, setBroadcastBodyHtml] = useState("");
  const [broadcastContentType, setBroadcastContentType] = useState<BroadcastContentType>("text");
  const [broadcastImageUrl, setBroadcastImageUrl] = useState("");
  const [broadcastButtonDrafts, setBroadcastButtonDrafts] = useState<BroadcastButtonDraft[]>([]);
  const [broadcastAudienceSegment, setBroadcastAudienceSegment] = useState<BroadcastAudienceSegment>("all");
  const [broadcastAudienceExcludeBlocked, setBroadcastAudienceExcludeBlocked] = useState(true);
  const [broadcastManualAudienceTargetsInput, setBroadcastManualAudienceTargetsInput] = useState("");
  const [broadcastLastSeenOlderThanDays, setBroadcastLastSeenOlderThanDays] = useState("");
  const [broadcastIncludeNeverSeen, setBroadcastIncludeNeverSeen] = useState(false);
  const [broadcastPendingPaymentOlderThanMinutes, setBroadcastPendingPaymentOlderThanMinutes] = useState("");
  const [broadcastPendingPaymentWithinLastDays, setBroadcastPendingPaymentWithinLastDays] = useState("");
  const [broadcastFailedPaymentWithinLastDays, setBroadcastFailedPaymentWithinLastDays] = useState("");
  const [broadcastSubscriptionExpiredFromDays, setBroadcastSubscriptionExpiredFromDays] = useState("");
  const [broadcastSubscriptionExpiredToDays, setBroadcastSubscriptionExpiredToDays] = useState("");
  const [broadcastCooldownDays, setBroadcastCooldownDays] = useState("");
  const [broadcastCooldownKey, setBroadcastCooldownKey] = useState("");
  const [broadcastTelegramQuietHoursStart, setBroadcastTelegramQuietHoursStart] = useState("");
  const [broadcastTelegramQuietHoursEnd, setBroadcastTelegramQuietHoursEnd] = useState("");
  const [broadcastSendInApp, setBroadcastSendInApp] = useState(true);
  const [broadcastSendTelegram, setBroadcastSendTelegram] = useState(false);
  const [broadcastEditorDirty, setBroadcastEditorDirty] = useState(false);
  const [broadcastFormSourceId, setBroadcastFormSourceId] = useState<number | null>(null);
  const [broadcastWorkspaceRefreshing, setBroadcastWorkspaceRefreshing] = useState(false);
  const [promoCampaignItems, setPromoCampaignItems] = useState<AdminPromoCampaign[]>([]);
  const [promoCampaignTotal, setPromoCampaignTotal] = useState(0);
  const [promoCampaignStatusFilter, setPromoCampaignStatusFilter] = useState<PromoCampaignFilter>("all");
  const [selectedPromoCampaignId, setSelectedPromoCampaignId] = useState<number | null>(null);
  const [promoCampaignsLoading, setPromoCampaignsLoading] = useState(false);
  const [promoCampaignSubmitting, setPromoCampaignSubmitting] = useState(false);
  const [promoCampaignEditingId, setPromoCampaignEditingId] = useState<number | null>(null);
  const [promoCodeItems, setPromoCodeItems] = useState<AdminPromoCode[]>([]);
  const [promoCodeTotal, setPromoCodeTotal] = useState(0);
  const [promoCodesLoading, setPromoCodesLoading] = useState(false);
  const [promoCodeSubmitting, setPromoCodeSubmitting] = useState(false);
  const [promoCodeActionId, setPromoCodeActionId] = useState<number | null>(null);
  const [promoRedemptionItems, setPromoRedemptionItems] = useState<AdminPromoRedemption[]>([]);
  const [promoRedemptionTotal, setPromoRedemptionTotal] = useState(0);
  const [promoRedemptionsLoading, setPromoRedemptionsLoading] = useState(false);
  const [promoCampaignName, setPromoCampaignName] = useState("");
  const [promoCampaignDescription, setPromoCampaignDescription] = useState("");
  const [promoCampaignStatus, setPromoCampaignStatus] = useState<PromoCampaignStatus>("draft");
  const [promoEffectType, setPromoEffectType] = useState<PromoEffectType>("percent_discount");
  const [promoEffectValue, setPromoEffectValue] = useState("");
  const [promoCurrency, setPromoCurrency] = useState("RUB");
  const [promoSelectedPlanCodes, setPromoSelectedPlanCodes] = useState<string[]>([]);
  const [promoFirstPurchaseOnly, setPromoFirstPurchaseOnly] = useState(false);
  const [promoRequiresActiveSubscription, setPromoRequiresActiveSubscription] = useState(false);
  const [promoRequiresNoActiveSubscription, setPromoRequiresNoActiveSubscription] = useState(false);
  const [promoStartsAtInput, setPromoStartsAtInput] = useState("");
  const [promoEndsAtInput, setPromoEndsAtInput] = useState("");
  const [promoTotalRedemptionsLimit, setPromoTotalRedemptionsLimit] = useState("");
  const [promoPerAccountRedemptionsLimit, setPromoPerAccountRedemptionsLimit] = useState("");
  const [promoCodeValue, setPromoCodeValue] = useState("");
  const [promoCodeMaxRedemptions, setPromoCodeMaxRedemptions] = useState("");
  const [promoCodeAssignedAccountId, setPromoCodeAssignedAccountId] = useState("");
  const [promoCodeIsActive, setPromoCodeIsActive] = useState(true);
  const [promoBatchQuantity, setPromoBatchQuantity] = useState("10");
  const [promoBatchPrefix, setPromoBatchPrefix] = useState("");
  const [promoBatchSuffixLength, setPromoBatchSuffixLength] = useState("8");
  const [promoBatchMaxRedemptions, setPromoBatchMaxRedemptions] = useState("");
  const [promoBatchAssignedAccountId, setPromoBatchAssignedAccountId] = useState("");
  const [promoBatchIsActive, setPromoBatchIsActive] = useState(true);
  const [promoBatchSubmitting, setPromoBatchSubmitting] = useState(false);
  const [promoLastGeneratedCodes, setPromoLastGeneratedCodes] = useState<string[]>([]);
  const [promoImportCodesText, setPromoImportCodesText] = useState("");
  const [promoImportMaxRedemptions, setPromoImportMaxRedemptions] = useState("");
  const [promoImportAssignedAccountId, setPromoImportAssignedAccountId] = useState("");
  const [promoImportIsActive, setPromoImportIsActive] = useState(true);
  const [promoImportSkipDuplicates, setPromoImportSkipDuplicates] = useState(true);
  const [promoImportSubmitting, setPromoImportSubmitting] = useState(false);
  const [promoImportSkippedCodes, setPromoImportSkippedCodes] = useState<string[]>([]);
  const [promoExportSubmitting, setPromoExportSubmitting] = useState(false);
  const [promoExportText, setPromoExportText] = useState("");
  const [promoRedemptionStatusFilter, setPromoRedemptionStatusFilter] =
    useState<PromoRedemptionStatusFilter>("all");
  const [promoRedemptionContextFilter, setPromoRedemptionContextFilter] =
    useState<PromoRedemptionContextFilter>("all");
  const [promoRedemptionCodeQueryInput, setPromoRedemptionCodeQueryInput] = useState("");
  const [promoRedemptionAccountIdInput, setPromoRedemptionAccountIdInput] = useState("");
  const [promoRedemptionAppliedStatusFilter, setPromoRedemptionAppliedStatusFilter] =
    useState<PromoRedemptionStatusFilter>("all");
  const [promoRedemptionAppliedContextFilter, setPromoRedemptionAppliedContextFilter] =
    useState<PromoRedemptionContextFilter>("all");
  const [promoRedemptionAppliedCodeQuery, setPromoRedemptionAppliedCodeQuery] = useState("");
  const [promoRedemptionAppliedAccountId, setPromoRedemptionAppliedAccountId] = useState("");

  const cards = useMemo(() => {
    if (!summary) {
      return [];
    }
    return [
      {
        label: t("admin.cards.accountsLabel"),
        value: summary.total_accounts,
        hint: t("admin.cards.accountsHint"),
      },
      {
        label: t("admin.cards.activeSubscriptionsLabel"),
        value: summary.active_subscriptions,
        hint: t("admin.cards.activeSubscriptionsHint"),
      },
      {
        label: t("admin.cards.payingCustomersLast30dLabel"),
        value: summary.paying_accounts_last_30d,
        hint: t("admin.cards.payingCustomersLast30dHint"),
      },
      {
        label: t("admin.cards.telegramLinkedLabel"),
        value: summary.accounts_with_telegram,
        hint: t("admin.cards.telegramLinkedHint"),
      },
    ];
  }, [summary]);
  const financeCards = useMemo(() => {
    if (!summary) {
      return [];
    }
    return [
      {
        label: t("admin.cards.walletBalanceLabel"),
        value: formatMoney(summary.total_wallet_balance),
        hint: t("admin.cards.walletBalanceHint"),
      },
      {
        label: t("admin.cards.withdrawalReserveLabel"),
        value: formatMoney(summary.pending_withdrawals_amount),
        hint: t("admin.cards.withdrawalReserveHint"),
      },
      {
        label: t("admin.cards.pendingWithdrawalsLabel"),
        value: summary.pending_withdrawals,
        hint: t("admin.cards.pendingWithdrawalsHint", {
          count: summary.pending_withdrawals,
        }),
      },
      {
        label: t("admin.cards.paymentsRubLast30dLabel"),
        value: formatMoney(summary.successful_payments_amount_rub_last_30d),
        hint: t("admin.cards.paymentsRubLast30dHint", {
          count: summary.successful_payments_rub_last_30d,
        }),
      },
      {
        label: t("admin.cards.starsRevenueLast30dLabel"),
        value: formatMoney(summary.direct_plan_revenue_stars_last_30d, "XTR"),
        hint: t("admin.cards.starsRevenueLast30dHint", {
          count: summary.direct_plan_purchases_stars_last_30d,
        }),
      },
      {
        label: t("admin.cards.withdrawalsLast30dLabel"),
        value: formatMoney(summary.paid_withdrawals_amount_last_30d),
        hint: t("admin.cards.withdrawalsLast30dHint"),
      },
    ];
  }, [summary]);
  const activityCards = useMemo(() => {
    if (!summary) {
      return [];
    }
    return [
      {
        label: t("admin.cards.newAccountsLast7dLabel"),
        value: summary.new_accounts_last_7d,
        hint: t("admin.cards.newAccountsLast7dHint"),
      },
      {
        label: t("admin.cards.blockedAccountsLabel"),
        value: summary.blocked_accounts,
        hint: t("admin.cards.blockedAccountsHint"),
      },
      {
        label: t("admin.cards.pendingPaymentsLabel"),
        value: summary.pending_payments,
        hint: t("admin.cards.pendingPaymentsHint"),
      },
      {
        label: t("admin.cards.topupsLast30dLabel"),
        value: formatMoney(summary.wallet_topups_amount_last_30d),
        hint: t("admin.cards.topupsLast30dHint"),
      },
      {
        label: t("admin.cards.planRevenueRubLast30dLabel"),
        value: formatMoney(summary.direct_plan_revenue_rub_last_30d),
        hint: t("admin.cards.planRevenueRubLast30dHint", {
          count: summary.direct_plan_purchases_rub_last_30d,
        }),
      },
      {
        label: t("admin.cards.referralEarningsLabel"),
        value: formatMoney(summary.total_referral_earnings),
        hint: t("admin.cards.referralEarningsHint"),
      },
    ];
  }, [summary]);

  const selectedGrantPlan = useMemo(
    () => subscriptionPlans.find((plan) => plan.code === subscriptionGrantPlanCode) || null,
    [subscriptionGrantPlanCode, subscriptionPlans],
  );
  const selectedCatalogPlan = useMemo(
    () => subscriptionPlans.find((plan) => plan.code === selectedCatalogPlanCode) || null,
    [selectedCatalogPlanCode, subscriptionPlans],
  );
  const plansOverview = useMemo(
    () => ({
      total: subscriptionPlans.length,
      popular: subscriptionPlans.filter((plan) => plan.popular).length,
      starsEnabled: subscriptionPlans.filter((plan) => plan.price_stars !== null).length,
      longestDuration: subscriptionPlans.reduce(
        (maxDuration, plan) => Math.max(maxDuration, plan.duration_days),
        0,
      ),
    }),
    [subscriptionPlans],
  );
  const planEditorMode = selectedCatalogPlanCode === null ? "create" : "edit";
  const selectedWithdrawal = useMemo(
    () => withdrawalItems.find((item) => item.id === selectedWithdrawalId) || null,
    [selectedWithdrawalId, withdrawalItems],
  );
  const withdrawalStats = useMemo(
    () => ({
      newCount: withdrawalItems.filter((item) => item.status === "new").length,
      inProgressCount: withdrawalItems.filter((item) => item.status === "in_progress").length,
    }),
    [withdrawalItems],
  );
  const hasMoreAccounts = accountItems.length < accountTotal;
  const accountListFiltersActive = Boolean(
    accountListDraftFilters.userQuery.trim() ||
      accountListDraftFilters.telegramQuery.trim() ||
      accountListDraftFilters.emailQuery.trim() ||
      accountListDraftFilters.status !== EMPTY_ACCOUNT_LIST_FILTERS.status ||
      accountListDraftFilters.subscription !== EMPTY_ACCOUNT_LIST_FILTERS.subscription ||
      accountListDraftFilters.sortBy !== EMPTY_ACCOUNT_LIST_FILTERS.sortBy ||
      accountListDraftFilters.sortOrder !== EMPTY_ACCOUNT_LIST_FILTERS.sortOrder,
  );
  const hasMoreLedgerHistory = ledgerHistoryItems.length < ledgerHistoryTotal;
  const hasMoreAccountEventHistory = accountEventHistoryItems.length < accountEventHistoryTotal;
  const accountEventFiltersActive = Boolean(
    accountEventTypeFilter !== "all" ||
      accountEventOutcomeFilter !== "all" ||
      accountEventSourceFilter !== "all" ||
      accountEventRequestIdFilter,
  );
  const selectedGlobalEvent = useMemo(
    () => globalEventItems.find((item) => item.id === selectedGlobalEventId) || null,
    [globalEventItems, selectedGlobalEventId],
  );
  const hasMoreGlobalEvents = globalEventItems.length < globalEventTotal;
  const globalEventFiltersActive = Boolean(
    globalEventSearchFilters.eventType !== "all" ||
      globalEventSearchFilters.outcome !== "all" ||
      globalEventSearchFilters.source !== "all" ||
      globalEventSearchFilters.requestId ||
      globalEventSearchFilters.accountId ||
      globalEventSearchFilters.actorAccountId ||
      globalEventSearchFilters.actorAdminId ||
      globalEventSearchFilters.telegramId,
  );
  const broadcastEditorMode = selectedBroadcastId ? "edit" : "create";
  const broadcastIsDraft = !selectedBroadcast || selectedBroadcast.status === "draft";
  const showBroadcastEditor = broadcastIsDraft;
  const showBroadcastRuntime = Boolean(
    selectedBroadcast &&
      selectedBroadcast.status !== "completed" &&
      selectedBroadcast.status !== "failed" &&
      selectedBroadcast.status !== "cancelled",
  );
  const canManageBroadcastRuntime = Boolean(profile?.is_superuser && selectedBroadcastId !== null);
  const broadcastChannels = useMemo(
    () => buildBroadcastChannels(broadcastSendInApp, broadcastSendTelegram),
    [broadcastSendInApp, broadcastSendTelegram],
  );
  const broadcastAudiencePresetChannels = useMemo(
    () =>
      buildBroadcastChannels(
        broadcastAudiencePresetEditor.sendInApp,
        broadcastAudiencePresetEditor.sendTelegram,
      ),
    [broadcastAudiencePresetEditor.sendInApp, broadcastAudiencePresetEditor.sendTelegram],
  );
  const broadcastEstimateSnapshot = useMemo<AdminBroadcastEstimate | null>(() => {
    if (broadcastEstimate) {
      return broadcastEstimate;
    }
    if (!selectedBroadcast) {
      return null;
    }
    return {
      channels: selectedBroadcast.channels,
      audience: selectedBroadcast.audience,
      estimated_total_accounts: selectedBroadcast.estimated_total_accounts,
      estimated_in_app_recipients: selectedBroadcast.estimated_in_app_recipients,
      estimated_telegram_recipients: selectedBroadcast.estimated_telegram_recipients,
    };
  }, [broadcastEstimate, selectedBroadcast]);
  const broadcastDraftCount = useMemo(
    () => broadcastItems.filter((item) => item.status === "draft").length,
    [broadcastItems],
  );
  const broadcastActiveCount = useMemo(
    () =>
      broadcastItems.filter(
        (item) => item.status === "scheduled" || item.status === "running" || item.status === "paused",
      ).length,
    [broadcastItems],
  );
  const broadcastAudiencePreviewSummary = useMemo(() => {
    try {
      return formatBroadcastAudienceSummary(buildBroadcastAudiencePayload());
    } catch {
      return humanizeBroadcastAudienceSegment(broadcastAudienceSegment);
    }
  }, [
    broadcastAudienceExcludeBlocked,
    broadcastCooldownDays,
    broadcastCooldownKey,
    broadcastIncludeNeverSeen,
    broadcastLastSeenOlderThanDays,
    broadcastManualAudienceTargetsInput,
    broadcastTelegramQuietHoursStart,
    broadcastTelegramQuietHoursEnd,
    broadcastAudienceSegment,
    broadcastFailedPaymentWithinLastDays,
    broadcastPendingPaymentOlderThanMinutes,
    broadcastPendingPaymentWithinLastDays,
    broadcastSubscriptionExpiredFromDays,
    broadcastSubscriptionExpiredToDays,
  ]);
  const selectedBroadcastAudiencePreset = useMemo(
    () =>
      broadcastAudiencePresetItems.find((item) => item.id === selectedBroadcastAudiencePresetId) || null,
    [broadcastAudiencePresetItems, selectedBroadcastAudiencePresetId],
  );
  const broadcastAudiencePresetEditorSummary = useMemo(() => {
    try {
      return formatBroadcastAudienceSummary(
        buildBroadcastAudiencePayloadFromEditor(broadcastAudiencePresetEditor),
      );
    } catch {
      return humanizeBroadcastAudienceSegment(broadcastAudiencePresetEditor.segment);
    }
  }, [broadcastAudiencePresetEditor]);
  const matchedBroadcastAudiencePreset = useMemo(() => {
    try {
      const currentAudience = buildBroadcastAudiencePayload();
      return (
        broadcastAudiencePresetItems.find((item) =>
          hasSameBroadcastAudiencePresetSelection(item, broadcastChannels, currentAudience),
        ) || null
      );
    } catch {
      return null;
    }
  }, [
    broadcastAudienceExcludeBlocked,
    broadcastAudiencePresetItems,
    broadcastChannels,
    broadcastCooldownDays,
    broadcastCooldownKey,
    broadcastFailedPaymentWithinLastDays,
    broadcastIncludeNeverSeen,
    broadcastLastSeenOlderThanDays,
    broadcastManualAudienceTargetsInput,
    broadcastPendingPaymentOlderThanMinutes,
    broadcastPendingPaymentWithinLastDays,
    broadcastSubscriptionExpiredFromDays,
    broadcastSubscriptionExpiredToDays,
    broadcastTelegramQuietHoursEnd,
    broadcastTelegramQuietHoursStart,
    broadcastAudienceSegment,
  ]);
  const selectedPromoCampaign = useMemo(
    () => promoCampaignItems.find((campaign) => campaign.id === selectedPromoCampaignId) || null,
    [promoCampaignItems, selectedPromoCampaignId],
  );
  const promoCampaignEditorMode = promoCampaignEditingId === null ? "create" : "edit";
  const promoOverview = useMemo(
    () => ({
      draft: promoCampaignItems.filter((campaign) => campaign.status === "draft").length,
      active: promoCampaignItems.filter((campaign) => campaign.status === "active").length,
      totalCodes: promoCampaignItems.reduce((accumulator, campaign) => accumulator + campaign.codes_count, 0),
      totalRedemptions: promoCampaignItems.reduce(
        (accumulator, campaign) => accumulator + campaign.redemptions_count,
        0,
      ),
    }),
    [promoCampaignItems],
  );
  const promoRedemptionFiltersActive = useMemo(
    () =>
      promoRedemptionAppliedStatusFilter !== "all" ||
      promoRedemptionAppliedContextFilter !== "all" ||
      promoRedemptionAppliedCodeQuery.length > 0 ||
      promoRedemptionAppliedAccountId.length > 0,
    [
      promoRedemptionAppliedAccountId,
      promoRedemptionAppliedCodeQuery,
      promoRedemptionAppliedContextFilter,
      promoRedemptionAppliedStatusFilter,
    ],
  );

  function resetBroadcastEditorForm() {
    setBroadcastName("");
    setBroadcastTitle("");
    setBroadcastBodyHtml("");
    setBroadcastContentType("text");
    setBroadcastImageUrl("");
    setBroadcastButtonDrafts([]);
    setBroadcastAudienceSegment("all");
    setBroadcastAudienceExcludeBlocked(true);
    setBroadcastManualAudienceTargetsInput("");
    setBroadcastLastSeenOlderThanDays("");
    setBroadcastIncludeNeverSeen(false);
    setBroadcastPendingPaymentOlderThanMinutes("");
    setBroadcastPendingPaymentWithinLastDays("");
    setBroadcastFailedPaymentWithinLastDays("");
    setBroadcastSubscriptionExpiredFromDays("");
    setBroadcastSubscriptionExpiredToDays("");
    setBroadcastCooldownDays("");
    setBroadcastCooldownKey("");
    setBroadcastTelegramQuietHoursStart("");
    setBroadcastTelegramQuietHoursEnd("");
    setBroadcastSendInApp(true);
    setBroadcastSendTelegram(false);
    setBroadcastEditorDirty(false);
    setBroadcastFormSourceId(null);
  }

  function applyBroadcastAudienceToEditor(
    audience: AdminBroadcastAudience,
    channels: BroadcastChannel[] = ["in_app"],
  ) {
    const nextState = createBroadcastAudienceEditorState(audience, channels);
    setBroadcastAudienceSegment(nextState.segment);
    setBroadcastAudienceExcludeBlocked(nextState.excludeBlocked);
    setBroadcastManualAudienceTargetsInput(nextState.manualTargetsInput);
    setBroadcastLastSeenOlderThanDays(nextState.lastSeenOlderThanDays);
    setBroadcastIncludeNeverSeen(nextState.includeNeverSeen);
    setBroadcastPendingPaymentOlderThanMinutes(nextState.pendingPaymentOlderThanMinutes);
    setBroadcastPendingPaymentWithinLastDays(nextState.pendingPaymentWithinLastDays);
    setBroadcastFailedPaymentWithinLastDays(nextState.failedPaymentWithinLastDays);
    setBroadcastSubscriptionExpiredFromDays(nextState.subscriptionExpiredFromDays);
    setBroadcastSubscriptionExpiredToDays(nextState.subscriptionExpiredToDays);
    setBroadcastCooldownDays(nextState.cooldownDays);
    setBroadcastCooldownKey(nextState.cooldownKey);
    setBroadcastTelegramQuietHoursStart(nextState.telegramQuietHoursStart);
    setBroadcastTelegramQuietHoursEnd(nextState.telegramQuietHoursEnd);
    setBroadcastSendInApp(nextState.sendInApp);
    setBroadcastSendTelegram(nextState.sendTelegram);
  }

  function resetPromoCampaignForm() {
    setPromoCampaignEditingId(null);
    setPromoCampaignName("");
    setPromoCampaignDescription("");
    setPromoCampaignStatus("draft");
    setPromoEffectType("percent_discount");
    setPromoEffectValue("");
    setPromoCurrency("RUB");
    setPromoSelectedPlanCodes([]);
    setPromoFirstPurchaseOnly(false);
    setPromoRequiresActiveSubscription(false);
    setPromoRequiresNoActiveSubscription(false);
    setPromoStartsAtInput("");
    setPromoEndsAtInput("");
    setPromoTotalRedemptionsLimit("");
    setPromoPerAccountRedemptionsLimit("");
  }

  function resetSubscriptionPlanEditor() {
    setSelectedCatalogPlanCode(null);
    setPlanEditorCode("");
    setPlanEditorName("");
    setPlanEditorPriceRub("");
    setPlanEditorPriceStars("");
    setPlanEditorDurationDays("");
    setPlanEditorDeviceLimit("");
    setPlanEditorPopular(false);
    setPlanEditorFeaturesInput("");
  }

  function hydrateSubscriptionPlanEditor(plan: AdminSubscriptionPlan) {
    setSelectedCatalogPlanCode(plan.code);
    setPlanEditorCode(plan.code);
    setPlanEditorName(plan.name);
    setPlanEditorPriceRub(String(plan.price_rub));
    setPlanEditorPriceStars(plan.price_stars !== null ? String(plan.price_stars) : "");
    setPlanEditorDurationDays(String(plan.duration_days));
    setPlanEditorDeviceLimit(plan.device_limit !== null ? String(plan.device_limit) : "");
    setPlanEditorPopular(plan.popular);
    setPlanEditorFeaturesInput(formatPlanFeaturesInput(plan.features));
  }

  function resetPromoCodeForm() {
    setPromoCodeValue("");
    setPromoCodeMaxRedemptions("");
    setPromoCodeAssignedAccountId("");
    setPromoCodeIsActive(true);
  }

  function resetPromoBatchForm() {
    setPromoBatchQuantity("10");
    setPromoBatchPrefix("");
    setPromoBatchSuffixLength("8");
    setPromoBatchMaxRedemptions("");
    setPromoBatchAssignedAccountId("");
    setPromoBatchIsActive(true);
  }

  function resetPromoImportForm() {
    setPromoImportCodesText("");
    setPromoImportMaxRedemptions("");
    setPromoImportAssignedAccountId("");
    setPromoImportIsActive(true);
    setPromoImportSkipDuplicates(true);
  }

  function hydratePromoCampaignForm(campaign: AdminPromoCampaign) {
    setPromoCampaignEditingId(campaign.id);
    setPromoCampaignName(campaign.name);
    setPromoCampaignDescription(campaign.description || "");
    setPromoCampaignStatus(campaign.status);
    setPromoEffectType(campaign.effect_type);
    setPromoEffectValue(String(campaign.effect_value));
    setPromoCurrency(campaign.currency);
    setPromoSelectedPlanCodes(campaign.plan_codes || []);
    setPromoFirstPurchaseOnly(campaign.first_purchase_only);
    setPromoRequiresActiveSubscription(campaign.requires_active_subscription);
    setPromoRequiresNoActiveSubscription(campaign.requires_no_active_subscription);
    setPromoStartsAtInput(toMoscowDateTimeInputValue(campaign.starts_at));
    setPromoEndsAtInput(toMoscowDateTimeInputValue(campaign.ends_at));
    setPromoTotalRedemptionsLimit(
      campaign.total_redemptions_limit !== null ? String(campaign.total_redemptions_limit) : "",
    );
    setPromoPerAccountRedemptionsLimit(
      campaign.per_account_redemptions_limit !== null ? String(campaign.per_account_redemptions_limit) : "",
    );
  }

  function hydrateBroadcastEditorForm(broadcast: AdminBroadcast) {
    setBroadcastName(broadcast.name);
    setBroadcastTitle(broadcast.title);
    setBroadcastBodyHtml(broadcast.body_html);
    setBroadcastContentType(broadcast.content_type);
    setBroadcastImageUrl(broadcast.image_url || "");
    setBroadcastButtonDrafts(broadcast.buttons.map((button) => createBroadcastButtonDraft(button)));
    applyBroadcastAudienceToEditor(broadcast.audience, broadcast.channels);
    setBroadcastEditorDirty(false);
    setBroadcastFormSourceId(broadcast.id);
  }

  function markBroadcastEditorDirty() {
    setBroadcastEditorDirty(true);
  }

  function confirmDiscardBroadcastEditorChanges(): boolean {
    if (!broadcastEditorDirty) {
      return true;
    }
    return window.confirm(
      "Есть несохраненные изменения в черновике рассылки. Сбросить их и продолжить?",
    );
  }

  const loadDashboard = useCallback(
    async (activeToken: string) => {
      const [admin, dashboard] = await Promise.all([
        adminFetch<AdminProfile>("/api/v1/admin/auth/me", activeToken),
        adminFetch<AdminDashboardSummary>("/api/v1/admin/dashboard/summary", activeToken),
      ]);
      setProfile(admin);
      setSummary(dashboard);
    },
    [],
  );

  const loadAccounts = useCallback(
    async (
      activeToken: string,
      options?: {
        offset?: number;
        append?: boolean;
        filters?: AccountListFilters;
      },
    ): Promise<AdminAccountListResponse | null> => {
      const offset = options?.offset ?? 0;
      const append = options?.append ?? false;
      const filters = normalizeAccountListFilters(options?.filters ?? accountListFilters);
      const searchParams = new URLSearchParams({
        limit: String(ADMIN_ACCOUNT_LIST_PAGE_SIZE),
        offset: String(offset),
        sort_by: filters.sortBy,
        sort_order: filters.sortOrder,
      });

      if (filters.userQuery) {
        searchParams.set("user_query", filters.userQuery);
      }
      if (filters.telegramQuery) {
        searchParams.set("telegram_query", filters.telegramQuery);
      }
      if (filters.emailQuery) {
        searchParams.set("email_query", filters.emailQuery);
      }
      if (filters.status !== "all") {
        searchParams.set("status", filters.status);
      }
      if (filters.subscription !== "all") {
        searchParams.set("subscription_state", filters.subscription);
      }

      if (append) {
        setAccountsLoadingMore(true);
      } else {
        setAccountsLoading(true);
      }

      try {
        const response = await adminFetch<AdminAccountListResponse>(
          `/api/v1/admin/accounts?${searchParams.toString()}`,
          activeToken,
        );
        setAccountItems((currentItems) => (append ? [...currentItems, ...response.items] : response.items));
        setAccountTotal(response.total);
        return response;
      } catch (fetchError) {
        if (!append) {
          setAccountItems([]);
          setAccountTotal(0);
        }
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить список пользователей");
        return null;
      } finally {
        if (append) {
          setAccountsLoadingMore(false);
        } else {
          setAccountsLoading(false);
        }
      }
    },
    [accountListFilters],
  );

  const loadAccountDetail = useCallback(
    async (accountId: string, activeToken: string): Promise<AdminAccountDetail | null> => {
      setDetailLoading(true);
      try {
        const detail = await adminFetch<AdminAccountDetail>(`/api/v1/admin/accounts/${accountId}`, activeToken);
        setSelectedAccount(detail);
        setSelectedAccountId(accountId);
        return detail;
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить карточку пользователя");
        setSelectedAccount(null);
        return null;
      } finally {
        setDetailLoading(false);
      }
    },
    [],
  );

  const loadLedgerHistory = useCallback(
    async (
      accountId: string,
      activeToken: string,
      options?: {
        offset?: number;
        append?: boolean;
        entryType?: LedgerEntryFilterOption;
      },
    ): Promise<AdminAccountLedgerHistoryResponse | null> => {
      const offset = options?.offset ?? 0;
      const append = options?.append ?? false;
      const entryType = options?.entryType ?? ledgerHistoryFilter;
      const searchParams = new URLSearchParams({
        limit: String(ADMIN_LEDGER_HISTORY_PAGE_SIZE),
        offset: String(offset),
      });

      if (entryType !== "all") {
        searchParams.set("entry_type", entryType);
      }

      if (append) {
        setLedgerHistoryLoadingMore(true);
      } else {
        setLedgerHistoryLoading(true);
      }

      try {
        const response = await adminFetch<AdminAccountLedgerHistoryResponse>(
          `/api/v1/admin/accounts/${accountId}/ledger-entries?${searchParams.toString()}`,
          activeToken,
        );
        setLedgerHistoryItems((currentItems) => (append ? [...currentItems, ...response.items] : response.items));
        setLedgerHistoryTotal(response.total);
        return response;
      } catch (fetchError) {
        if (!append) {
          setLedgerHistoryItems([]);
          setLedgerHistoryTotal(0);
        }
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить ledger history");
        return null;
      } finally {
        if (append) {
          setLedgerHistoryLoadingMore(false);
        } else {
          setLedgerHistoryLoading(false);
        }
      }
    },
    [ledgerHistoryFilter],
  );

  const loadAccountEventHistory = useCallback(
    async (
      accountId: string,
      activeToken: string,
      options?: {
        offset?: number;
        append?: boolean;
        eventType?: AccountEventTypeFilterOption;
        outcome?: AccountEventOutcomeFilterOption;
        source?: AccountEventSourceFilterOption;
        requestId?: string;
      },
    ): Promise<AdminAccountEventLogHistoryResponse | null> => {
      const offset = options?.offset ?? 0;
      const append = options?.append ?? false;
      const eventType = options?.eventType ?? accountEventTypeFilter;
      const outcome = options?.outcome ?? accountEventOutcomeFilter;
      const source = options?.source ?? accountEventSourceFilter;
      const requestId = (options?.requestId ?? accountEventRequestIdFilter).trim();
      const searchParams = new URLSearchParams({
        limit: String(ADMIN_ACCOUNT_EVENT_HISTORY_PAGE_SIZE),
        offset: String(offset),
      });

      if (eventType !== "all") {
        searchParams.append("event_type", eventType);
      }
      if (outcome !== "all") {
        searchParams.append("outcome", outcome);
      }
      if (source !== "all") {
        searchParams.append("source", source);
      }
      if (requestId) {
        searchParams.set("request_id", requestId);
      }

      if (append) {
        setAccountEventHistoryLoadingMore(true);
      } else {
        setAccountEventHistoryLoading(true);
      }

      try {
        const response = await adminFetch<AdminAccountEventLogHistoryResponse>(
          `/api/v1/admin/accounts/${accountId}/event-logs?${searchParams.toString()}`,
          activeToken,
        );
        setAccountEventHistoryItems((currentItems) =>
          append ? [...currentItems, ...response.items] : response.items,
        );
        setAccountEventHistoryTotal(response.total);
        return response;
      } catch (fetchError) {
        if (!append) {
          setAccountEventHistoryItems([]);
          setAccountEventHistoryTotal(0);
        }
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить timeline событий");
        return null;
      } finally {
        if (append) {
          setAccountEventHistoryLoadingMore(false);
        } else {
          setAccountEventHistoryLoading(false);
        }
      }
    },
    [
      accountEventOutcomeFilter,
      accountEventRequestIdFilter,
      accountEventSourceFilter,
      accountEventTypeFilter,
    ],
  );

  const loadGlobalEventSearch = useCallback(
    async (
      activeToken: string,
      options?: {
        offset?: number;
        append?: boolean;
        filters?: GlobalEventSearchFilters;
      },
    ): Promise<AdminGlobalAccountEventLogHistoryResponse | null> => {
      const offset = options?.offset ?? 0;
      const append = options?.append ?? false;
      const filters = normalizeGlobalEventSearchFilters(options?.filters ?? globalEventSearchFilters);
      const searchParams = new URLSearchParams({
        limit: String(ADMIN_ACCOUNT_EVENT_HISTORY_PAGE_SIZE),
        offset: String(offset),
      });

      if (filters.eventType !== "all") {
        searchParams.append("event_type", filters.eventType);
      }
      if (filters.outcome !== "all") {
        searchParams.append("outcome", filters.outcome);
      }
      if (filters.source !== "all") {
        searchParams.append("source", filters.source);
      }
      if (filters.requestId) {
        searchParams.set("request_id", filters.requestId);
      }
      if (filters.accountId) {
        searchParams.set("account_id", filters.accountId);
      }
      if (filters.actorAccountId) {
        searchParams.set("actor_account_id", filters.actorAccountId);
      }
      if (filters.actorAdminId) {
        searchParams.set("actor_admin_id", filters.actorAdminId);
      }
      if (filters.telegramId) {
        searchParams.set("telegram_id", filters.telegramId);
      }

      if (append) {
        setGlobalEventLoadingMore(true);
      } else {
        setGlobalEventLoading(true);
      }

      try {
        const response = await adminFetch<AdminGlobalAccountEventLogHistoryResponse>(
          `/api/v1/admin/accounts/event-logs/search?${searchParams.toString()}`,
          activeToken,
        );
        setGlobalEventItems((currentItems) => (append ? [...currentItems, ...response.items] : response.items));
        setGlobalEventTotal(response.total);
        setSelectedGlobalEventId((currentSelection) =>
          response.items.some((item) => item.id === currentSelection)
            ? currentSelection
            : (append ? currentSelection : (response.items[0]?.id ?? null)),
        );
        return response;
      } catch (fetchError) {
        if (!append) {
          setGlobalEventItems([]);
          setGlobalEventTotal(0);
          setSelectedGlobalEventId(null);
        }
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить глобальный event search");
        return null;
      } finally {
        if (append) {
          setGlobalEventLoadingMore(false);
        } else {
          setGlobalEventLoading(false);
        }
      }
    },
    [globalEventSearchFilters],
  );

  const loadSubscriptionPlans = useCallback(
    async (activeToken: string): Promise<AdminSubscriptionPlan[]> => {
      setPlansLoading(true);
      try {
        const plans = await adminFetch<AdminSubscriptionPlan[]>(
          "/api/v1/admin/plans",
          activeToken,
        );
        setSubscriptionPlans(plans);
        setSelectedCatalogPlanCode((currentSelection) =>
          plans.some((plan) => plan.code === currentSelection) ? currentSelection : null,
        );
        return plans;
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить тарифы");
        return [];
      } finally {
        setPlansLoading(false);
      }
    },
    [],
  );

  const loadWithdrawals = useCallback(
    async (activeToken: string): Promise<AdminWithdrawalQueueItem[]> => {
      setWithdrawalsLoading(true);
      try {
        const response = await adminFetch<AdminWithdrawalQueueResponse>(
          "/api/v1/admin/withdrawals?limit=50&offset=0",
          activeToken,
        );
        setWithdrawalItems(response.items);
        setWithdrawalTotal(response.total);
        setSelectedWithdrawalId((currentSelection) =>
          response.items.some((item) => item.id === currentSelection) ? currentSelection : (response.items[0]?.id ?? null),
        );
        return response.items;
      } catch (fetchError) {
        setWithdrawalItems([]);
        setWithdrawalTotal(0);
        setSelectedWithdrawalId(null);
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить очередь выводов");
        return [];
      } finally {
        setWithdrawalsLoading(false);
      }
    },
    [],
  );

  const loadBroadcasts = useCallback(
    async (activeToken: string): Promise<AdminBroadcast[]> => {
      setBroadcastsLoading(true);
      try {
        const response = await adminFetch<AdminBroadcastListResponse>(
          "/api/v1/admin/broadcasts?limit=50&offset=0",
          activeToken,
        );
        setBroadcastItems(response.items);
        setBroadcastTotal(response.total);
        setSelectedBroadcastId((currentSelection) =>
          response.items.some((item) => item.id === currentSelection)
            ? currentSelection
            : broadcastSelectionMode === "new"
              ? null
              : (response.items[0]?.id ?? null),
        );
        return response.items;
      } catch (fetchError) {
        setBroadcastItems([]);
        setBroadcastTotal(0);
        setSelectedBroadcastId(null);
        setSelectedBroadcast(null);
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить рассылки");
        return [];
      } finally {
        setBroadcastsLoading(false);
      }
    },
    [broadcastSelectionMode],
  );

  const loadBroadcastAudiencePresets = useCallback(
    async (activeToken: string): Promise<AdminBroadcastAudiencePreset[]> => {
      setBroadcastAudiencePresetLoading(true);
      try {
        const response = await adminFetch<AdminBroadcastAudiencePresetListResponse>(
          `/api/v1/admin/broadcasts/audiences?limit=${BROADCAST_AUDIENCE_PRESET_LIMIT}&offset=0`,
          activeToken,
        );
        setBroadcastAudiencePresetItems(response.items);
        setBroadcastAudiencePresetTotal(response.total);
        setSelectedBroadcastAudiencePresetId((currentSelection) =>
          response.items.some((item) => item.id === currentSelection) ? currentSelection : null,
        );
        setBroadcastAudiencePresetError(null);
        return response.items;
      } catch (fetchError) {
        setBroadcastAudiencePresetItems([]);
        setBroadcastAudiencePresetTotal(0);
        setSelectedBroadcastAudiencePresetId(null);
        setBroadcastAudiencePresetError(
          fetchError instanceof Error ? fetchError.message : "Не удалось загрузить сохраненные аудитории",
        );
        return [];
      } finally {
        setBroadcastAudiencePresetLoading(false);
      }
    },
    [],
  );

  const loadBroadcastDetail = useCallback(
    async (broadcastId: number, activeToken: string): Promise<AdminBroadcast | null> => {
      try {
        const broadcast = await adminFetch<AdminBroadcast>(
          `/api/v1/admin/broadcasts/${broadcastId}`,
          activeToken,
        );
        setSelectedBroadcast(broadcast);
        setBroadcastEstimate({
          channels: broadcast.channels,
          audience: broadcast.audience,
          estimated_total_accounts: broadcast.estimated_total_accounts,
          estimated_in_app_recipients: broadcast.estimated_in_app_recipients,
          estimated_telegram_recipients: broadcast.estimated_telegram_recipients,
        });
        setBroadcastEstimateError(null);
        return broadcast;
      } catch (fetchError) {
        setSelectedBroadcast(null);
        setBroadcastEstimate(null);
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить черновик рассылки");
        return null;
      }
    },
    [],
  );

  const loadBroadcastRuns = useCallback(
    async (activeToken: string): Promise<AdminBroadcastRun[]> => {
      setBroadcastRunsLoading(true);
      try {
        const response = await adminFetch<AdminBroadcastRunListResponse>(
          "/api/v1/admin/broadcasts/runs?limit=20&offset=0",
          activeToken,
        );
        setBroadcastRunItems(response.items);
        setBroadcastRunTotal(response.total);
        return response.items;
      } catch (fetchError) {
        setBroadcastRunItems([]);
        setBroadcastRunTotal(0);
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить журнал запусков");
        return [];
      } finally {
        setBroadcastRunsLoading(false);
      }
    },
    [],
  );

  const loadPromoCampaigns = useCallback(
    async (
      activeToken: string,
      options?: {
        statusFilter?: PromoCampaignFilter;
      },
    ): Promise<AdminPromoCampaign[]> => {
      setPromoCampaignsLoading(true);
      try {
        const statusFilter = options?.statusFilter ?? promoCampaignStatusFilter;
        const params = new URLSearchParams({
          limit: "100",
          offset: "0",
        });
        if (statusFilter !== "all") {
          params.set("status", statusFilter);
        }
        const response = await adminFetch<AdminPromoCampaignListResponse>(
          `/api/v1/admin/promos/campaigns?${params.toString()}`,
          activeToken,
        );
        setPromoCampaignItems(response.items);
        setPromoCampaignTotal(response.total);
        setSelectedPromoCampaignId((currentSelection) =>
          response.items.some((item) => item.id === currentSelection)
            ? currentSelection
            : (response.items[0]?.id ?? null),
        );
        return response.items;
      } catch (fetchError) {
        setPromoCampaignItems([]);
        setPromoCampaignTotal(0);
        setSelectedPromoCampaignId(null);
        setPromoCodeItems([]);
        setPromoCodeTotal(0);
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить кампании промокодов");
        return [];
      } finally {
        setPromoCampaignsLoading(false);
      }
    },
    [promoCampaignStatusFilter],
  );

  const loadPromoCodes = useCallback(
    async (campaignId: number, activeToken: string): Promise<AdminPromoCode[]> => {
      setPromoCodesLoading(true);
      try {
        const response = await adminFetch<AdminPromoCodeListResponse>(
          `/api/v1/admin/promos/campaigns/${campaignId}/codes?limit=200&offset=0`,
          activeToken,
        );
        setPromoCodeItems(response.items);
        setPromoCodeTotal(response.total);
        return response.items;
      } catch (fetchError) {
        setPromoCodeItems([]);
        setPromoCodeTotal(0);
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить коды кампании");
        return [];
      } finally {
        setPromoCodesLoading(false);
      }
    },
    [],
  );

  const loadPromoRedemptions = useCallback(
    async (
      campaignId: number,
      activeToken: string,
      options?: {
        statusFilter?: PromoRedemptionStatusFilter;
        contextFilter?: PromoRedemptionContextFilter;
        codeQuery?: string;
        accountId?: string;
      },
    ): Promise<AdminPromoRedemption[]> => {
      setPromoRedemptionsLoading(true);
      try {
        const statusFilter = options?.statusFilter ?? "all";
        const contextFilter = options?.contextFilter ?? "all";
        const codeQuery = options?.codeQuery?.trim() || "";
        const accountId = options?.accountId?.trim() || "";
        const params = new URLSearchParams({
          limit: "100",
          offset: "0",
        });
        if (statusFilter !== "all") {
          params.set("status", statusFilter);
        }
        if (contextFilter !== "all") {
          params.set("redemption_context", contextFilter);
        }
        if (codeQuery) {
          params.set("code_query", codeQuery);
        }
        if (accountId) {
          params.set("account_id", accountId);
        }
        const response = await adminFetch<AdminPromoRedemptionListResponse>(
          `/api/v1/admin/promos/campaigns/${campaignId}/redemptions?${params.toString()}`,
          activeToken,
        );
        setPromoRedemptionItems(response.items);
        setPromoRedemptionTotal(response.total);
        return response.items;
      } catch (fetchError) {
        setPromoRedemptionItems([]);
        setPromoRedemptionTotal(0);
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить историю активаций");
        return [];
      } finally {
        setPromoRedemptionsLoading(false);
      }
    },
    [],
  );

  function updateAccountListSnapshot(
    account: Pick<AdminAccountDetail, "id" | "balance" | "status" | "subscription_status" | "subscription_expires_at">,
  ) {
    setAccountItems((items) =>
      items.map((item) =>
        item.id === account.id
          ? {
              ...item,
              balance: account.balance,
              status: account.status,
              subscription_status: account.subscription_status,
              subscription_expires_at: account.subscription_expires_at,
            }
          : item,
      ),
    );
  }

  useEffect(() => {
    if (!token) {
      setLoading(false);
      setProfile(null);
      setSummary(null);
      setSubscriptionPlans([]);
      setAccountItems([]);
      setAccountTotal(0);
      setAccountsLoading(false);
      setAccountsLoadingMore(false);
      setAccountsExporting(false);
      setAccountListDraftFilters({ ...EMPTY_ACCOUNT_LIST_FILTERS });
      setAccountListFilters({ ...EMPTY_ACCOUNT_LIST_FILTERS });
      setSelectedAccountId(null);
      setSelectedAccount(null);
      setLedgerHistoryItems([]);
      setLedgerHistoryTotal(0);
      setAccountEventHistoryItems([]);
      setAccountEventHistoryTotal(0);
      setAccountEventTypeFilter("all");
      setAccountEventOutcomeFilter("all");
      setAccountEventSourceFilter("all");
      setAccountEventRequestIdInput("");
      setAccountEventRequestIdFilter("");
      setGlobalEventSearchDraft({ ...EMPTY_GLOBAL_EVENT_SEARCH_FILTERS });
      setGlobalEventSearchFilters({ ...EMPTY_GLOBAL_EVENT_SEARCH_FILTERS });
      setGlobalEventItems([]);
      setGlobalEventTotal(0);
      setSelectedGlobalEventId(null);
      setWithdrawalItems([]);
      setWithdrawalTotal(0);
      setSelectedWithdrawalId(null);
      setWithdrawalComment("");
      setBroadcastItems([]);
      setBroadcastTotal(0);
      setSelectedBroadcastId(null);
      setSelectedBroadcast(null);
      setBroadcastEstimate(null);
      setBroadcastEstimateLoading(false);
      setBroadcastEstimateError(null);
      setBroadcastAudiencePresetItems([]);
      setBroadcastAudiencePresetTotal(0);
      setSelectedBroadcastAudiencePresetId(null);
      setBroadcastAudiencePresetLoading(false);
      setBroadcastAudiencePresetSubmitting(false);
      setBroadcastAudiencePresetError(null);
      setBroadcastAudiencePresetName("");
      setBroadcastAudiencePresetDescription("");
      setBroadcastTestEmailsInput("");
      setBroadcastTestTelegramIdsInput("");
      setBroadcastTestComment("");
      setBroadcastTestSubmitting(false);
      setBroadcastTestResult(null);
      setBroadcastRuntimeComment("");
      setBroadcastScheduleAtInput("");
      setBroadcastRuntimeSubmitting(false);
      setBroadcastRunItems([]);
      setBroadcastRunTotal(0);
      setSelectedBroadcastRunId(null);
      setSelectedBroadcastRun(null);
      setBroadcastRunsLoading(false);
      setBroadcastRunDetailLoading(false);
      setBroadcastRunDeliveries([]);
      setBroadcastRunDeliveriesTotal(0);
      setBroadcastRunStatusFilter("all");
      setBroadcastRunTypeFilter("all");
      setBroadcastRunChannelFilter("all");
      setBroadcastName("");
      setBroadcastTitle("");
      setBroadcastBodyHtml("");
      setBroadcastContentType("text");
      setBroadcastImageUrl("");
      setBroadcastButtonDrafts([]);
      setBroadcastAudienceSegment("all");
      setBroadcastAudienceExcludeBlocked(true);
      setBroadcastManualAudienceTargetsInput("");
      setBroadcastLastSeenOlderThanDays("");
      setBroadcastIncludeNeverSeen(false);
      setBroadcastPendingPaymentOlderThanMinutes("");
      setBroadcastPendingPaymentWithinLastDays("");
      setBroadcastFailedPaymentWithinLastDays("");
      setBroadcastSubscriptionExpiredFromDays("");
      setBroadcastSubscriptionExpiredToDays("");
      setBroadcastCooldownDays("");
      setBroadcastCooldownKey("");
      setBroadcastTelegramQuietHoursStart("");
      setBroadcastTelegramQuietHoursEnd("");
      setBroadcastSendInApp(true);
      setBroadcastSendTelegram(false);
      setBroadcastEditorDirty(false);
      setBroadcastFormSourceId(null);
      setBroadcastWorkspaceRefreshing(false);
      setPromoCampaignItems([]);
      setPromoCampaignTotal(0);
      setPromoCampaignStatusFilter("all");
      setSelectedPromoCampaignId(null);
      setPromoCampaignsLoading(false);
      setPromoCampaignSubmitting(false);
      setPromoCampaignEditingId(null);
      setPromoCodeItems([]);
      setPromoCodeTotal(0);
      setPromoCodesLoading(false);
      setPromoCodeSubmitting(false);
      setPromoCodeActionId(null);
      setPromoRedemptionItems([]);
      setPromoRedemptionTotal(0);
      setPromoRedemptionsLoading(false);
      setPromoBatchSubmitting(false);
      setPromoLastGeneratedCodes([]);
      setPromoImportSubmitting(false);
      setPromoImportSkippedCodes([]);
      setPromoExportSubmitting(false);
      setPromoExportText("");
      setPromoRedemptionStatusFilter("all");
      setPromoRedemptionContextFilter("all");
      setPromoRedemptionCodeQueryInput("");
      setPromoRedemptionAccountIdInput("");
      setPromoRedemptionAppliedStatusFilter("all");
      setPromoRedemptionAppliedContextFilter("all");
      setPromoRedemptionAppliedCodeQuery("");
      setPromoRedemptionAppliedAccountId("");
      resetPromoCampaignForm();
      resetPromoCodeForm();
      resetPromoBatchForm();
      resetPromoImportForm();
      setNotice(null);
      return;
    }

    let cancelled = false;

    async function bootstrap() {
      try {
        setLoading(true);
        setError(null);
        await loadDashboard(token);
      } catch (fetchError) {
        if (cancelled) {
          return;
        }
        localStorage.removeItem(TOKEN_KEY);
        setToken("");
        setProfile(null);
        setSummary(null);
        setAccountItems([]);
        setAccountTotal(0);
        setAccountsExporting(false);
        setAccountListDraftFilters({ ...EMPTY_ACCOUNT_LIST_FILTERS });
        setAccountListFilters({ ...EMPTY_ACCOUNT_LIST_FILTERS });
        setSelectedAccountId(null);
        setSelectedAccount(null);
        setLedgerHistoryItems([]);
        setLedgerHistoryTotal(0);
        setAccountEventHistoryItems([]);
        setAccountEventHistoryTotal(0);
        setGlobalEventItems([]);
        setGlobalEventTotal(0);
        setSelectedGlobalEventId(null);
        setNotice(null);
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить админку");
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, [loadDashboard, token]);

  useEffect(() => {
    if (
      !token ||
      (activeView !== "accounts" && activeView !== "promos" && activeView !== "plans") ||
      subscriptionPlans.length > 0
    ) {
      return;
    }

    void loadSubscriptionPlans(token);
  }, [activeView, loadSubscriptionPlans, subscriptionPlans.length, token]);

  useEffect(() => {
    if (!token || activeView !== "accounts") {
      return;
    }

    void loadAccounts(token, {
      offset: 0,
      append: false,
      filters: accountListFilters,
    });
  }, [activeView, accountListFilters, loadAccounts, token]);

  useEffect(() => {
    if (activeView !== "accounts") {
      return;
    }

    const timer = window.setTimeout(() => {
      setAccountListFilters(normalizeAccountListFilters(accountListDraftFilters));
    }, ACCOUNT_LIST_FILTER_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [accountListDraftFilters, activeView]);

  useEffect(() => {
    if (!token || activeView !== "withdrawals") {
      return;
    }

    void loadWithdrawals(token);
  }, [activeView, loadWithdrawals, token]);

  useEffect(() => {
    if (!token || activeView !== "broadcasts") {
      return;
    }

    void loadBroadcasts(token);
    void loadBroadcastAudiencePresets(token);
    void loadBroadcastRuns(token);
  }, [activeView, loadBroadcastAudiencePresets, loadBroadcastRuns, loadBroadcasts, token]);

  useEffect(() => {
    if (!token || activeView !== "promos") {
      return;
    }

    void loadPromoCampaigns(token);
  }, [activeView, loadPromoCampaigns, token]);

  useEffect(() => {
    if (!token || activeView !== "events") {
      return;
    }

    void loadGlobalEventSearch(token, {
      offset: 0,
      append: false,
      filters: globalEventSearchFilters,
    });
  }, [activeView, globalEventSearchFilters, loadGlobalEventSearch, token]);

  useEffect(() => {
    if (!token || activeView !== "broadcasts") {
      return;
    }
    if (selectedBroadcastId === null) {
      setSelectedBroadcast(null);
      return;
    }

    void loadBroadcastDetail(selectedBroadcastId, token);
  }, [activeView, loadBroadcastDetail, selectedBroadcastId, token]);

  useEffect(() => {
    if (!token || activeView !== "promos") {
      return;
    }
    if (selectedPromoCampaignId === null) {
      setPromoCodeItems([]);
      setPromoCodeTotal(0);
      return;
    }

    void loadPromoCodes(selectedPromoCampaignId, token);
  }, [activeView, loadPromoCodes, selectedPromoCampaignId, token]);

  useEffect(() => {
    if (!token || activeView !== "promos") {
      return;
    }
    if (selectedPromoCampaignId === null) {
      setPromoRedemptionItems([]);
      setPromoRedemptionTotal(0);
      return;
    }

    void loadPromoRedemptions(selectedPromoCampaignId, token, {
      statusFilter: promoRedemptionAppliedStatusFilter,
      contextFilter: promoRedemptionAppliedContextFilter,
      codeQuery: promoRedemptionAppliedCodeQuery,
      accountId: promoRedemptionAppliedAccountId,
    });
  }, [
    activeView,
    loadPromoRedemptions,
    promoRedemptionAppliedAccountId,
    promoRedemptionAppliedCodeQuery,
    promoRedemptionAppliedContextFilter,
    promoRedemptionAppliedStatusFilter,
    selectedPromoCampaignId,
    token,
  ]);

  useEffect(() => {
    if (!token || activeView !== "accounts" || !selectedAccountId) {
      return;
    }

    void loadLedgerHistory(selectedAccountId, token, {
      offset: 0,
      append: false,
      entryType: ledgerHistoryFilter,
    });
  }, [activeView, ledgerHistoryFilter, loadLedgerHistory, selectedAccountId, token]);

  useEffect(() => {
    if (!token || activeView !== "accounts" || !selectedAccountId) {
      return;
    }

    void loadAccountEventHistory(selectedAccountId, token, {
      offset: 0,
      append: false,
      eventType: accountEventTypeFilter,
      outcome: accountEventOutcomeFilter,
      source: accountEventSourceFilter,
      requestId: accountEventRequestIdFilter,
    });
  }, [
    accountEventOutcomeFilter,
    accountEventRequestIdFilter,
    accountEventSourceFilter,
    accountEventTypeFilter,
    activeView,
    loadAccountEventHistory,
    selectedAccountId,
    token,
  ]);

  useEffect(() => {
    if (subscriptionGrantPlanCode || subscriptionPlans.length === 0) {
      return;
    }

    const defaultPlan = subscriptionPlans.find((plan) => plan.popular) || subscriptionPlans[0];
    if (defaultPlan) {
      setSubscriptionGrantPlanCode(defaultPlan.code);
    }
  }, [subscriptionGrantPlanCode, subscriptionPlans]);

  useEffect(() => {
    setBalanceAdjustmentAmount("");
    setBalanceAdjustmentComment("");
    setSubscriptionGrantComment("");
    setStatusChangeComment("");
  }, [selectedAccountId]);

  useEffect(() => {
    setLedgerHistoryItems([]);
    setLedgerHistoryTotal(0);
    setAccountEventHistoryItems([]);
    setAccountEventHistoryTotal(0);
  }, [selectedAccountId]);

  useEffect(() => {
    setWithdrawalComment("");
  }, [selectedWithdrawalId]);

  useEffect(() => {
    resetPromoCodeForm();
    resetPromoBatchForm();
    setPromoLastGeneratedCodes([]);
  }, [selectedPromoCampaignId]);

  useEffect(() => {
    if (!selectedBroadcast) {
      setBroadcastEstimate(null);
      setBroadcastEstimateError(null);
      setBroadcastAudiencePreview(null);
      setBroadcastAudiencePreviewError(null);
      setBroadcastTestResult(null);
      setBroadcastRuntimeComment("");
      setBroadcastScheduleAtInput("");
      return;
    }

    if (broadcastFormSourceId === selectedBroadcast.id && broadcastEditorDirty) {
      return;
    }

    hydrateBroadcastEditorForm(selectedBroadcast);
    setBroadcastEstimate({
      channels: selectedBroadcast.channels,
      audience: selectedBroadcast.audience,
      estimated_total_accounts: selectedBroadcast.estimated_total_accounts,
      estimated_in_app_recipients: selectedBroadcast.estimated_in_app_recipients,
      estimated_telegram_recipients: selectedBroadcast.estimated_telegram_recipients,
    });
    setBroadcastEstimateError(null);
    setBroadcastAudiencePreview(null);
    setBroadcastAudiencePreviewError(null);
    setBroadcastTestResult(null);
    setBroadcastRuntimeComment("");
    setBroadcastScheduleAtInput(toMoscowDateTimeInputValue(selectedBroadcast.scheduled_at));
  }, [broadcastEditorDirty, broadcastFormSourceId, selectedBroadcast]);

  useEffect(() => {
    if (selectedBroadcastAudiencePreset) {
      setBroadcastAudiencePresetName(selectedBroadcastAudiencePreset.name);
      setBroadcastAudiencePresetDescription(selectedBroadcastAudiencePreset.description || "");
      setBroadcastAudiencePresetEditor(
        createBroadcastAudienceEditorState(
          selectedBroadcastAudiencePreset.audience,
          selectedBroadcastAudiencePreset.channels,
        ),
      );
      return;
    }

    if (selectedBroadcastAudiencePresetId === null) {
      return;
    }

    setSelectedBroadcastAudiencePresetId(null);
    setBroadcastAudiencePresetName("");
    setBroadcastAudiencePresetDescription("");
    setBroadcastAudiencePresetEditor({ ...EMPTY_BROADCAST_AUDIENCE_EDITOR_STATE });
  }, [selectedBroadcastAudiencePreset, selectedBroadcastAudiencePresetId]);

  useEffect(() => {
    if (!token || activeView !== "broadcasts") {
      return;
    }

    if (broadcastChannels.length === 0) {
      setBroadcastEstimate(null);
      setBroadcastEstimateLoading(false);
      setBroadcastEstimateError("Выбери хотя бы один канал доставки, чтобы посчитать аудиторию.");
      setBroadcastAudiencePreview(null);
      setBroadcastAudiencePreviewLoading(false);
      setBroadcastAudiencePreviewError("Выбери хотя бы один канал доставки, чтобы увидеть sample аудитории.");
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        setBroadcastEstimateLoading(true);
        setBroadcastAudiencePreviewLoading(true);
        try {
          const audience = buildBroadcastAudiencePayload();
          const [estimateResult, previewResult] = await Promise.allSettled([
            adminFetch<AdminBroadcastEstimate>("/api/v1/admin/broadcasts/estimate", token, {
              method: "POST",
              body: JSON.stringify({
                channels: broadcastChannels,
                audience,
              }),
            }),
            adminFetch<AdminBroadcastAudiencePreview>("/api/v1/admin/broadcasts/preview", token, {
              method: "POST",
              body: JSON.stringify({
                channels: broadcastChannels,
                audience,
                limit: BROADCAST_AUDIENCE_PREVIEW_LIMIT,
              }),
            }),
          ]);
          if (cancelled) {
            return;
          }

          if (estimateResult.status === "fulfilled") {
            setBroadcastEstimate(estimateResult.value);
            setBroadcastEstimateError(null);
          } else {
            setBroadcastEstimateError(
              estimateResult.reason instanceof Error
                ? estimateResult.reason.message
                : "Не удалось пересчитать аудиторию",
            );
          }

          if (previewResult.status === "fulfilled") {
            setBroadcastAudiencePreview(previewResult.value);
            setBroadcastAudiencePreviewError(null);
          } else {
            setBroadcastAudiencePreview(null);
            setBroadcastAudiencePreviewError(
              previewResult.reason instanceof Error
                ? previewResult.reason.message
                : "Не удалось загрузить sample аудитории",
            );
          }
        } catch (estimateError) {
          if (cancelled) {
            return;
          }
          setBroadcastEstimateError(
            estimateError instanceof Error ? estimateError.message : "Не удалось пересчитать аудиторию",
          );
          setBroadcastAudiencePreview(null);
          setBroadcastAudiencePreviewError(
            estimateError instanceof Error ? estimateError.message : "Не удалось загрузить sample аудитории",
          );
        } finally {
          if (!cancelled) {
            setBroadcastEstimateLoading(false);
            setBroadcastAudiencePreviewLoading(false);
          }
        }
      })();
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [
    activeView,
    broadcastAudienceExcludeBlocked,
    broadcastCooldownDays,
    broadcastCooldownKey,
    broadcastIncludeNeverSeen,
    broadcastLastSeenOlderThanDays,
    broadcastManualAudienceTargetsInput,
    broadcastTelegramQuietHoursStart,
    broadcastTelegramQuietHoursEnd,
    broadcastFailedPaymentWithinLastDays,
    broadcastPendingPaymentOlderThanMinutes,
    broadcastPendingPaymentWithinLastDays,
    broadcastAudienceSegment,
    broadcastChannels,
    broadcastSubscriptionExpiredFromDays,
    broadcastSubscriptionExpiredToDays,
    token,
  ]);

  useEffect(() => {
    if (!token || activeView !== "broadcasts") {
      return;
    }

    void loadBroadcastRuns(token);
  }, [activeView, loadBroadcastRuns, token]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          login,
          password,
        }),
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }

      const body = (await response.json()) as AdminAuthResponse;
      localStorage.setItem(TOKEN_KEY, body.access_token);
      setToken(body.access_token);
      setProfile(body.admin);
      setPassword("");
      setNotice(null);
      await loadDashboard(body.access_token);
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Не удалось войти");
    } finally {
      setSubmitting(false);
    }
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setProfile(null);
    setSummary(null);
    setSubscriptionPlans([]);
    setAccountItems([]);
    setAccountTotal(0);
    setAccountsLoading(false);
    setAccountsLoadingMore(false);
    setAccountsExporting(false);
    setAccountListDraftFilters({ ...EMPTY_ACCOUNT_LIST_FILTERS });
    setAccountListFilters({ ...EMPTY_ACCOUNT_LIST_FILTERS });
    setSelectedAccountId(null);
    setSelectedAccount(null);
    setLedgerHistoryItems([]);
    setLedgerHistoryTotal(0);
    setAccountEventHistoryItems([]);
    setAccountEventHistoryTotal(0);
    setAccountEventTypeFilter("all");
    setAccountEventOutcomeFilter("all");
    setAccountEventSourceFilter("all");
    setAccountEventRequestIdInput("");
    setAccountEventRequestIdFilter("");
    setGlobalEventSearchDraft({ ...EMPTY_GLOBAL_EVENT_SEARCH_FILTERS });
    setGlobalEventSearchFilters({ ...EMPTY_GLOBAL_EVENT_SEARCH_FILTERS });
    setGlobalEventItems([]);
    setGlobalEventTotal(0);
    setSelectedGlobalEventId(null);
    setWithdrawalItems([]);
    setWithdrawalTotal(0);
    setSelectedWithdrawalId(null);
    setWithdrawalComment("");
    setBroadcastItems([]);
    setBroadcastTotal(0);
    setBroadcastSelectionMode("existing");
    setSelectedBroadcastId(null);
    setSelectedBroadcast(null);
    setBroadcastEstimate(null);
    setBroadcastEstimateLoading(false);
    setBroadcastEstimateError(null);
    setBroadcastAudiencePreview(null);
    setBroadcastAudiencePreviewLoading(false);
    setBroadcastAudiencePreviewError(null);
    setBroadcastTestEmailsInput("");
    setBroadcastTestTelegramIdsInput("");
    setBroadcastTestComment("");
    setBroadcastTestSubmitting(false);
    setBroadcastTestResult(null);
    setBroadcastRuntimeComment("");
    setBroadcastScheduleAtInput("");
    setBroadcastRuntimeSubmitting(false);
    setBroadcastRunItems([]);
    setBroadcastRunTotal(0);
    setSelectedBroadcastRunId(null);
    setSelectedBroadcastRun(null);
    setBroadcastRunsLoading(false);
    setBroadcastRunDetailLoading(false);
    setBroadcastRunDeliveries([]);
    setBroadcastRunDeliveriesTotal(0);
    setBroadcastRunStatusFilter("all");
    setBroadcastRunTypeFilter("all");
    setBroadcastRunChannelFilter("all");
    setBroadcastName("");
    setBroadcastTitle("");
    setBroadcastBodyHtml("");
    setBroadcastContentType("text");
    setBroadcastImageUrl("");
    setBroadcastButtonDrafts([]);
    setBroadcastAudienceSegment("all");
    setBroadcastAudienceExcludeBlocked(true);
    setBroadcastManualAudienceTargetsInput("");
    setBroadcastLastSeenOlderThanDays("");
    setBroadcastIncludeNeverSeen(false);
    setBroadcastPendingPaymentOlderThanMinutes("");
    setBroadcastPendingPaymentWithinLastDays("");
    setBroadcastFailedPaymentWithinLastDays("");
    setBroadcastSubscriptionExpiredFromDays("");
    setBroadcastSubscriptionExpiredToDays("");
    setBroadcastCooldownDays("");
    setBroadcastCooldownKey("");
    setBroadcastTelegramQuietHoursStart("");
    setBroadcastTelegramQuietHoursEnd("");
    setBroadcastSendInApp(true);
    setBroadcastSendTelegram(false);
    setBroadcastEditorDirty(false);
    setBroadcastFormSourceId(null);
    setBroadcastWorkspaceRefreshing(false);
    setPromoCampaignItems([]);
    setPromoCampaignTotal(0);
    setPromoCampaignStatusFilter("all");
    setSelectedPromoCampaignId(null);
    setPromoCampaignsLoading(false);
    setPromoCampaignSubmitting(false);
    setPromoCampaignEditingId(null);
    setPromoCodeItems([]);
    setPromoCodeTotal(0);
    setPromoCodesLoading(false);
    setPromoCodeSubmitting(false);
    setPromoCodeActionId(null);
    setPromoRedemptionItems([]);
    setPromoRedemptionTotal(0);
    setPromoRedemptionsLoading(false);
    setPromoBatchSubmitting(false);
    setPromoLastGeneratedCodes([]);
    setPromoImportSubmitting(false);
    setPromoImportSkippedCodes([]);
    setPromoExportSubmitting(false);
    setPromoExportText("");
    setPromoRedemptionStatusFilter("all");
    setPromoRedemptionContextFilter("all");
    setPromoRedemptionCodeQueryInput("");
    setPromoRedemptionAccountIdInput("");
    setPromoRedemptionAppliedStatusFilter("all");
    setPromoRedemptionAppliedContextFilter("all");
    setPromoRedemptionAppliedCodeQuery("");
    setPromoRedemptionAppliedAccountId("");
    resetPromoCampaignForm();
    resetPromoCodeForm();
    resetPromoBatchForm();
    resetPromoImportForm();
    setError(null);
    setNotice(null);
    setActiveView("dashboard");
  }

  async function handleRefresh() {
    if (!token) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await loadDashboard(token);
      if (activeView === "plans") {
        await loadSubscriptionPlans(token);
      } else if ((activeView === "accounts" || activeView === "promos") && subscriptionPlans.length === 0) {
        await loadSubscriptionPlans(token);
      }
      if (activeView === "accounts") {
        await loadAccounts(token, {
          offset: 0,
          append: false,
          filters: accountListFilters,
        });
      }
      if (activeView === "accounts" && selectedAccountId) {
        await loadLedgerHistory(selectedAccountId, token, {
          offset: 0,
          append: false,
          entryType: ledgerHistoryFilter,
        });
        await loadAccountEventHistory(selectedAccountId, token, {
          offset: 0,
          append: false,
          eventType: accountEventTypeFilter,
          outcome: accountEventOutcomeFilter,
          source: accountEventSourceFilter,
          requestId: accountEventRequestIdFilter,
        });
      }
      if (activeView === "events") {
        await loadGlobalEventSearch(token, {
          offset: 0,
          append: false,
          filters: globalEventSearchFilters,
        });
      }
      if (activeView === "withdrawals") {
        await loadWithdrawals(token);
      }
      if (activeView === "broadcasts") {
        await loadBroadcasts(token);
        await loadBroadcastRuns(token);
      }
      if (activeView === "promos") {
        await loadPromoCampaigns(token);
      }
      if (activeView === "accounts" && selectedAccountId) {
        await loadAccountDetail(selectedAccountId, token);
      }
      if (activeView === "broadcasts" && selectedBroadcastId !== null) {
        await loadBroadcastDetail(selectedBroadcastId, token);
      }
      if (activeView === "promos" && selectedPromoCampaignId !== null) {
        await loadPromoCodes(selectedPromoCampaignId, token);
        await loadPromoRedemptions(selectedPromoCampaignId, token, {
          statusFilter: promoRedemptionAppliedStatusFilter,
          contextFilter: promoRedemptionAppliedContextFilter,
          codeQuery: promoRedemptionAppliedCodeQuery,
          accountId: promoRedemptionAppliedAccountId,
        });
      }
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Не удалось обновить данные");
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectAccount(accountId: string) {
    if (!token) {
      return;
    }
    setError(null);
    setNotice(null);
    await loadAccountDetail(accountId, token);
  }

  function handleCloseAccountDetail() {
    setSelectedAccountId(null);
    setSelectedAccount(null);
  }

  function handleAccountListTextFilterChange(
    field: "userQuery" | "telegramQuery" | "emailQuery",
    value: string,
  ) {
    setAccountListDraftFilters((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function handleAccountListSelectFilterChange(
    field: "status" | "subscription",
    value: AccountListStatusFilter | AccountListSubscriptionFilter,
  ) {
    setAccountListDraftFilters((current) => {
      const nextFilters = {
        ...current,
        [field]: value,
      };
      setAccountListFilters(normalizeAccountListFilters(nextFilters));
      return nextFilters;
    });
  }

  function handleAccountListSortChange(
    sortBy: AccountListSortBy,
    defaultOrder: AccountListSortOrder,
  ) {
    setAccountListDraftFilters((current) => {
      const nextFilters = {
        ...current,
        sortBy,
        sortOrder: getNextAccountListSortOrder(current, sortBy, defaultOrder),
      };
      setAccountListFilters(normalizeAccountListFilters(nextFilters));
      return nextFilters;
    });
  }

  function handleResetAccountListFilters() {
    setAccountListDraftFilters({ ...EMPTY_ACCOUNT_LIST_FILTERS });
    setAccountListFilters({ ...EMPTY_ACCOUNT_LIST_FILTERS });
  }

  async function handleLoadMoreAccounts() {
    if (!token || !hasMoreAccounts || accountsLoadingMore) {
      return;
    }

    await loadAccounts(token, {
      offset: accountItems.length,
      append: true,
      filters: accountListFilters,
    });
  }

  async function handleExportAccounts() {
    if (!token || accountsExporting) {
      return;
    }

    const filters = normalizeAccountListFilters(accountListDraftFilters);
    setAccountListFilters(filters);
    setError(null);
    setNotice(null);
    setAccountsExporting(true);

    const searchParams = new URLSearchParams({
      sort_by: filters.sortBy,
      sort_order: filters.sortOrder,
    });
    if (filters.userQuery) {
      searchParams.set("user_query", filters.userQuery);
    }
    if (filters.telegramQuery) {
      searchParams.set("telegram_query", filters.telegramQuery);
    }
    if (filters.emailQuery) {
      searchParams.set("email_query", filters.emailQuery);
    }
    if (filters.status !== "all") {
      searchParams.set("status", filters.status);
    }
    if (filters.subscription !== "all") {
      searchParams.set("subscription_state", filters.subscription);
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/admin/accounts/export?${searchParams.toString()}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );
      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download =
        getDownloadFilename(response.headers.get("Content-Disposition")) ||
        "accounts-export.csv";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(downloadUrl);
      setNotice(t("admin.accounts.export.success"));
    } catch (exportError) {
      setError(
        exportError instanceof Error
          ? exportError.message
          : t("admin.accounts.export.failed"),
      );
    } finally {
      setAccountsExporting(false);
    }
  }

  async function handleOpenWithdrawalAccount(accountId: string) {
    if (!token) {
      return;
    }

    setActiveView("accounts");
    setError(null);
    setNotice(null);
    await loadAccountDetail(accountId, token);
  }

  function handleNewBroadcastDraft() {
    if (!confirmDiscardBroadcastEditorChanges()) {
      return;
    }
    setBroadcastSelectionMode("new");
    setSelectedBroadcastId(null);
    setSelectedBroadcast(null);
    resetBroadcastEditorForm();
    setError(null);
    setNotice(null);
  }

  function handleSelectBroadcast(broadcastId: number) {
    if (broadcastId !== selectedBroadcastId && !confirmDiscardBroadcastEditorChanges()) {
      return;
    }
    setBroadcastSelectionMode("existing");
    setSelectedBroadcastId(broadcastId);
    setError(null);
    setNotice(null);
  }

  function handleNewSubscriptionPlan() {
    resetSubscriptionPlanEditor();
    setError(null);
    setNotice(null);
  }

  function handleSelectSubscriptionPlan(plan: AdminSubscriptionPlan) {
    hydrateSubscriptionPlanEditor(plan);
    setError(null);
    setNotice(null);
  }

  function handleSelectPromoCampaign(campaignId: number) {
    setSelectedPromoCampaignId(campaignId);
    setPromoExportText("");
    setPromoImportSkippedCodes([]);
    setError(null);
    setNotice(null);
  }

  function handleEditPromoCampaign(campaign: AdminPromoCampaign) {
    hydratePromoCampaignForm(campaign);
    setSelectedPromoCampaignId(campaign.id);
    setError(null);
    setNotice(null);
  }

  function handleTogglePromoPlanCode(planCode: string) {
    setPromoSelectedPlanCodes((currentItems) =>
      currentItems.includes(planCode)
        ? currentItems.filter((item) => item !== planCode)
        : [...currentItems, planCode],
    );
  }

  async function handleSaveSubscriptionPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      return;
    }

    const normalizedCode = planEditorCode.trim();
    const normalizedName = planEditorName.trim();
    const parsedPriceRub = Number.parseInt(planEditorPriceRub, 10);
    const parsedPriceStars = planEditorPriceStars.trim()
      ? Number.parseInt(planEditorPriceStars, 10)
      : null;
    const parsedDurationDays = Number.parseInt(planEditorDurationDays, 10);
    const parsedDeviceLimit = planEditorDeviceLimit.trim()
      ? Number.parseInt(planEditorDeviceLimit, 10)
      : null;
    const parsedFeatures = parsePlanFeaturesInput(planEditorFeaturesInput);

    if (!normalizedCode && planEditorMode === "create") {
      setError(t("admin.plans.form.validation.codeRequired"));
      return;
    }
    if (!normalizedName) {
      setError(t("admin.plans.form.validation.nameRequired"));
      return;
    }
    if (!Number.isInteger(parsedPriceRub) || parsedPriceRub <= 0) {
      setError(t("admin.plans.form.validation.priceRubInvalid"));
      return;
    }
    if (parsedPriceStars !== null && (!Number.isInteger(parsedPriceStars) || parsedPriceStars <= 0)) {
      setError(t("admin.plans.form.validation.priceStarsInvalid"));
      return;
    }
    if (!Number.isInteger(parsedDurationDays) || parsedDurationDays <= 0) {
      setError(t("admin.plans.form.validation.durationInvalid"));
      return;
    }
    if (parsedDeviceLimit !== null && (!Number.isInteger(parsedDeviceLimit) || parsedDeviceLimit < 0)) {
      setError(t("admin.plans.form.validation.deviceLimitInvalid"));
      return;
    }
    if (parsedFeatures.length === 0) {
      setError(t("admin.plans.form.validation.featuresRequired"));
      return;
    }

    setPlanSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const updatePlanCode = selectedCatalogPlanCode;
      if (planEditorMode === "edit" && !updatePlanCode) {
        setError(t("admin.apiErrors.planNotFound"));
        return;
      }

      const payload = {
        name: normalizedName,
        price_rub: parsedPriceRub,
        price_stars: parsedPriceStars,
        duration_days: parsedDurationDays,
        device_limit: parsedDeviceLimit,
        popular: planEditorPopular,
        features: parsedFeatures,
      };
      const response =
        planEditorMode === "create"
          ? await adminFetch<AdminSubscriptionPlan>("/api/v1/admin/plans", token, {
              method: "POST",
              body: JSON.stringify({
                code: normalizedCode,
                ...payload,
              }),
            })
          : await adminFetch<AdminSubscriptionPlan>(
              `/api/v1/admin/plans/${encodeURIComponent(updatePlanCode || normalizedCode)}`,
              token,
              {
                method: "PUT",
                body: JSON.stringify(payload),
              },
            );

      setSubscriptionPlans((currentItems) => {
        if (planEditorMode === "create") {
          return [...currentItems, response];
        }
        return currentItems.map((item) => (item.code === response.code ? response : item));
      });
      hydrateSubscriptionPlanEditor(response);
      if (subscriptionGrantPlanCode === "" && response.popular) {
        setSubscriptionGrantPlanCode(response.code);
      }
      setNotice(
        planEditorMode === "create"
          ? t("admin.plans.form.notices.created", { name: response.name })
          : t("admin.plans.form.notices.updated", { name: response.name }),
      );
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : t("admin.plans.form.notices.failed"),
      );
    } finally {
      setPlanSubmitting(false);
    }
  }

  async function handleDeleteSubscriptionPlan() {
    if (!token || !selectedCatalogPlan || planDeleting) {
      return;
    }
    if (!window.confirm(t("admin.plans.form.deleteConfirm", { name: selectedCatalogPlan.name }))) {
      return;
    }

    setPlanDeleting(true);
    setError(null);
    setNotice(null);
    try {
      await adminFetch<void>(`/api/v1/admin/plans/${encodeURIComponent(selectedCatalogPlan.code)}`, token, {
        method: "DELETE",
      });
      setSubscriptionPlans((currentItems) =>
        currentItems.filter((item) => item.code !== selectedCatalogPlan.code),
      );
      if (subscriptionGrantPlanCode === selectedCatalogPlan.code) {
        setSubscriptionGrantPlanCode("");
      }
      setPromoSelectedPlanCodes((currentItems) =>
        currentItems.filter((item) => item !== selectedCatalogPlan.code),
      );
      resetSubscriptionPlanEditor();
      setNotice(t("admin.plans.form.notices.deleted", { name: selectedCatalogPlan.name }));
    } catch (deleteError) {
      setError(
        deleteError instanceof Error ? deleteError.message : t("admin.plans.form.notices.failed"),
      );
    } finally {
      setPlanDeleting(false);
    }
  }

  async function handleCreatePromoCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      return;
    }

    const trimmedName = promoCampaignName.trim();
    const trimmedDescription = promoCampaignDescription.trim();
    const normalizedCurrency = promoCurrency.trim().toUpperCase();
    const parsedEffectValue = Number.parseInt(promoEffectValue, 10);
    const parsedTotalLimit = promoTotalRedemptionsLimit.trim()
      ? Number.parseInt(promoTotalRedemptionsLimit, 10)
      : null;
    const parsedPerAccountLimit = promoPerAccountRedemptionsLimit.trim()
      ? Number.parseInt(promoPerAccountRedemptionsLimit, 10)
      : null;

    if (!trimmedName) {
      setError("Название кампании обязательно");
      return;
    }
    if (!Number.isInteger(parsedEffectValue)) {
      setError("Значение эффекта должно быть целым числом");
      return;
    }
    if (
      (promoEffectType === "percent_discount" && (parsedEffectValue < 1 || parsedEffectValue > 100)) ||
      (promoEffectType === "fixed_price" && parsedEffectValue < 0) ||
      (promoEffectType !== "percent_discount" && promoEffectType !== "fixed_price" && parsedEffectValue <= 0)
    ) {
      setError(
        promoEffectType === "percent_discount"
          ? "Для процентной скидки значение должно быть от 1 до 100"
          : promoEffectType === "fixed_price"
            ? "Для фиксированной цены значение должно быть нулем или положительным числом"
            : "Значение эффекта должно быть положительным",
      );
      return;
    }
    if (!normalizedCurrency) {
      setError("Валюта обязательна");
      return;
    }
    if (promoRequiresActiveSubscription && promoRequiresNoActiveSubscription) {
      setError("Нельзя одновременно требовать активную и отсутствующую подписку");
      return;
    }
    if (
      parsedTotalLimit !== null &&
      (!Number.isInteger(parsedTotalLimit) || parsedTotalLimit <= 0)
    ) {
      setError("Общий лимит активаций должен быть положительным целым числом");
      return;
    }
    if (
      parsedPerAccountLimit !== null &&
      (!Number.isInteger(parsedPerAccountLimit) || parsedPerAccountLimit <= 0)
    ) {
      setError("Лимит на аккаунт должен быть положительным целым числом");
      return;
    }
    if (
      parsedTotalLimit !== null &&
      parsedPerAccountLimit !== null &&
      parsedPerAccountLimit > parsedTotalLimit
    ) {
      setError("Лимит на аккаунт не может превышать общий лимит");
      return;
    }

    setPromoCampaignSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const isEditingCampaign = promoCampaignEditingId !== null;
      const campaign = await adminFetch<AdminPromoCampaign>(
        isEditingCampaign
          ? `/api/v1/admin/promos/campaigns/${promoCampaignEditingId}`
          : "/api/v1/admin/promos/campaigns",
        token,
        {
          method: isEditingCampaign ? "PUT" : "POST",
          body: JSON.stringify({
            name: trimmedName,
            description: trimmedDescription || null,
            status: promoCampaignStatus,
            effect_type: promoEffectType,
            effect_value: parsedEffectValue,
            currency: normalizedCurrency,
            plan_codes: promoSelectedPlanCodes.length > 0 ? promoSelectedPlanCodes : null,
            first_purchase_only: promoFirstPurchaseOnly,
            requires_active_subscription: promoRequiresActiveSubscription,
            requires_no_active_subscription: promoRequiresNoActiveSubscription,
            starts_at: promoStartsAtInput ? buildMoscowScheduleIso(promoStartsAtInput) : null,
            ends_at: promoEndsAtInput ? buildMoscowScheduleIso(promoEndsAtInput) : null,
            total_redemptions_limit: parsedTotalLimit,
            per_account_redemptions_limit: parsedPerAccountLimit,
          }),
        },
      );
      const nextStatusFilter =
        promoCampaignStatusFilter !== "all" && promoCampaignStatusFilter !== promoCampaignStatus
          ? "all"
          : promoCampaignStatusFilter;
      if (nextStatusFilter !== promoCampaignStatusFilter) {
        setPromoCampaignStatusFilter("all");
      }
      setSelectedPromoCampaignId(campaign.id);
      resetPromoCampaignForm();
      await Promise.all([
        loadPromoCampaigns(token, { statusFilter: nextStatusFilter }),
        loadPromoCodes(campaign.id, token),
      ]);
      setNotice(isEditingCampaign ? "Кампания промокодов обновлена" : "Кампания промокодов создана");
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : promoCampaignEditingId !== null
            ? "Не удалось обновить кампанию промокодов"
            : "Не удалось создать кампанию промокодов",
      );
    } finally {
      setPromoCampaignSubmitting(false);
    }
  }

  async function handleCreatePromoCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || selectedPromoCampaignId === null) {
      setError("Сначала выбери кампанию промокодов");
      return;
    }

    const trimmedCode = promoCodeValue.trim().toUpperCase();
    const trimmedAssignedAccountId = promoCodeAssignedAccountId.trim();
    const parsedMaxRedemptions = promoCodeMaxRedemptions.trim()
      ? Number.parseInt(promoCodeMaxRedemptions, 10)
      : null;

    if (!trimmedCode) {
      setError("Код обязателен");
      return;
    }
    if (
      parsedMaxRedemptions !== null &&
      (!Number.isInteger(parsedMaxRedemptions) || parsedMaxRedemptions <= 0)
    ) {
      setError("Лимит активаций для кода должен быть положительным целым числом");
      return;
    }

    setPromoCodeSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      await adminFetch<AdminPromoCode>(
        `/api/v1/admin/promos/campaigns/${selectedPromoCampaignId}/codes`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            code: trimmedCode,
            max_redemptions: parsedMaxRedemptions,
            assigned_account_id: trimmedAssignedAccountId || null,
            is_active: promoCodeIsActive,
          }),
        },
      );
      resetPromoCodeForm();
      await Promise.all([loadPromoCampaigns(token), loadPromoCodes(selectedPromoCampaignId, token)]);
      setNotice("Код промокампании создан");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Не удалось создать промокод");
    } finally {
      setPromoCodeSubmitting(false);
    }
  }

  async function handleBatchCreatePromoCodes(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || selectedPromoCampaignId === null) {
      setError("Сначала выбери кампанию промокодов");
      return;
    }

    const parsedQuantity = Number.parseInt(promoBatchQuantity, 10);
    const parsedSuffixLength = Number.parseInt(promoBatchSuffixLength, 10);
    const parsedMaxRedemptions = promoBatchMaxRedemptions.trim()
      ? Number.parseInt(promoBatchMaxRedemptions, 10)
      : null;
    const trimmedPrefix = promoBatchPrefix.trim().toUpperCase();
    const trimmedAssignedAccountId = promoBatchAssignedAccountId.trim();

    if (!Number.isInteger(parsedQuantity) || parsedQuantity <= 0) {
      setError("Количество кодов должно быть положительным целым числом");
      return;
    }
    if (!Number.isInteger(parsedSuffixLength) || parsedSuffixLength < 4 || parsedSuffixLength > 24) {
      setError("Длина suffix должна быть от 4 до 24 символов");
      return;
    }
    if (
      parsedMaxRedemptions !== null &&
      (!Number.isInteger(parsedMaxRedemptions) || parsedMaxRedemptions <= 0)
    ) {
      setError("Лимит активаций для batch-кодов должен быть положительным целым числом");
      return;
    }

    setPromoBatchSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const response = await adminFetch<AdminPromoCodeBatchCreateResponse>(
        `/api/v1/admin/promos/campaigns/${selectedPromoCampaignId}/codes/batch`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            quantity: parsedQuantity,
            prefix: trimmedPrefix || null,
            suffix_length: parsedSuffixLength,
            max_redemptions: parsedMaxRedemptions,
            assigned_account_id: trimmedAssignedAccountId || null,
            is_active: promoBatchIsActive,
          }),
        },
      );
      setPromoLastGeneratedCodes(response.items.map((item) => item.code));
      resetPromoBatchForm();
      await Promise.all([loadPromoCampaigns(token), loadPromoCodes(selectedPromoCampaignId, token)]);
      setNotice(`Сгенерировано ${response.created_count} кодов`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Не удалось сгенерировать batch-коды");
    } finally {
      setPromoBatchSubmitting(false);
    }
  }

  async function handleImportPromoCodes(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || selectedPromoCampaignId === null) {
      setError("Сначала выбери кампанию промокодов");
      return;
    }

    const trimmedCodesText = promoImportCodesText.trim();
    const parsedMaxRedemptions = promoImportMaxRedemptions.trim()
      ? Number.parseInt(promoImportMaxRedemptions, 10)
      : null;
    const trimmedAssignedAccountId = promoImportAssignedAccountId.trim();

    if (!trimmedCodesText) {
      setError("Добавь хотя бы один код для импорта");
      return;
    }
    if (
      parsedMaxRedemptions !== null &&
      (!Number.isInteger(parsedMaxRedemptions) || parsedMaxRedemptions <= 0)
    ) {
      setError("Лимит активаций для импортируемых кодов должен быть положительным целым числом");
      return;
    }

    setPromoImportSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const response = await adminFetch<AdminPromoCodeImportResponse>(
        `/api/v1/admin/promos/campaigns/${selectedPromoCampaignId}/codes/import`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            codes_text: trimmedCodesText,
            max_redemptions: parsedMaxRedemptions,
            assigned_account_id: trimmedAssignedAccountId || null,
            is_active: promoImportIsActive,
            skip_duplicates: promoImportSkipDuplicates,
          }),
        },
      );
      setPromoImportSkippedCodes(response.skipped_codes);
      resetPromoImportForm();
      await Promise.all([loadPromoCampaigns(token), loadPromoCodes(selectedPromoCampaignId, token)]);
      setNotice(
        response.skipped_count > 0
          ? `Импортировано ${response.created_count} кодов, пропущено ${response.skipped_count}`
          : `Импортировано ${response.created_count} кодов`,
      );
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Не удалось импортировать коды");
    } finally {
      setPromoImportSubmitting(false);
    }
  }

  async function handleExportPromoCodes() {
    if (!token || selectedPromoCampaignId === null) {
      setError("Сначала выбери кампанию промокодов");
      return;
    }

    setPromoExportSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const response = await adminFetch<AdminPromoCodeExportResponse>(
        `/api/v1/admin/promos/campaigns/${selectedPromoCampaignId}/codes/export`,
        token,
      );
      const codesText = response.items.map((item) => item.code).join("\n");
      setPromoExportText(codesText);

      let copiedToClipboard = false;
      if (codesText && typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(codesText);
          copiedToClipboard = true;
        } catch {
          copiedToClipboard = false;
        }
      }

      setNotice(
        response.exported_count === 0
          ? "В выбранной кампании пока нет кодов для экспорта"
          : copiedToClipboard
            ? `Экспортировано ${response.exported_count} кодов и скопировано в буфер`
            : `Экспортировано ${response.exported_count} кодов`,
      );
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Не удалось экспортировать коды");
    } finally {
      setPromoExportSubmitting(false);
    }
  }

  function handleApplyPromoRedemptionFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextStatusFilter = promoRedemptionStatusFilter;
    const nextContextFilter = promoRedemptionContextFilter;
    const nextCodeQuery = promoRedemptionCodeQueryInput.trim();
    const nextAccountId = promoRedemptionAccountIdInput.trim();

    setPromoRedemptionAppliedStatusFilter(promoRedemptionStatusFilter);
    setPromoRedemptionAppliedContextFilter(promoRedemptionContextFilter);
    setPromoRedemptionAppliedCodeQuery(nextCodeQuery);
    setPromoRedemptionAppliedAccountId(nextAccountId);
    setError(null);
    setNotice(null);

    if (token && selectedPromoCampaignId !== null) {
      void loadPromoRedemptions(selectedPromoCampaignId, token, {
        statusFilter: nextStatusFilter,
        contextFilter: nextContextFilter,
        codeQuery: nextCodeQuery,
        accountId: nextAccountId,
      });
    }
  }

  function handleResetPromoRedemptionFilters() {
    setPromoRedemptionStatusFilter("all");
    setPromoRedemptionContextFilter("all");
    setPromoRedemptionCodeQueryInput("");
    setPromoRedemptionAccountIdInput("");
    setPromoRedemptionAppliedStatusFilter("all");
    setPromoRedemptionAppliedContextFilter("all");
    setPromoRedemptionAppliedCodeQuery("");
    setPromoRedemptionAppliedAccountId("");
    setError(null);
    setNotice(null);

    if (token && selectedPromoCampaignId !== null) {
      void loadPromoRedemptions(selectedPromoCampaignId, token, {
        statusFilter: "all",
        contextFilter: "all",
        codeQuery: "",
        accountId: "",
      });
    }
  }

  async function handleTogglePromoCodeActivity(promoCode: AdminPromoCode) {
    if (!token || selectedPromoCampaignId === null) {
      return;
    }

    setPromoCodeActionId(promoCode.id);
    setError(null);
    setNotice(null);

    try {
      const updatedCode = await adminFetch<AdminPromoCode>(
        `/api/v1/admin/promos/campaigns/${selectedPromoCampaignId}/codes/${promoCode.id}`,
        token,
        {
          method: "PUT",
          body: JSON.stringify({
            max_redemptions: promoCode.max_redemptions,
            assigned_account_id: promoCode.assigned_account_id,
            is_active: !promoCode.is_active,
          }),
        },
      );
      setPromoCodeItems((currentItems) =>
        currentItems.map((item) => (item.id === updatedCode.id ? updatedCode : item)),
      );
      setNotice(updatedCode.is_active ? `Код ${updatedCode.code} включен` : `Код ${updatedCode.code} выключен`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Не удалось обновить состояние кода");
    } finally {
      setPromoCodeActionId(null);
    }
  }

  function handleBroadcastButtonChange(
    buttonId: string,
    field: "text" | "url",
    value: string,
  ) {
    markBroadcastEditorDirty();
    setBroadcastButtonDrafts((currentItems) =>
      currentItems.map((item) => (item.id === buttonId ? { ...item, [field]: value } : item)),
    );
  }

  function handleAddBroadcastButton() {
    markBroadcastEditorDirty();
    setBroadcastButtonDrafts((currentItems) => {
      if (currentItems.length >= 3) {
        return currentItems;
      }
      return [...currentItems, createBroadcastButtonDraft()];
    });
  }

  function handleRemoveBroadcastButton(buttonId: string) {
    markBroadcastEditorDirty();
    setBroadcastButtonDrafts((currentItems) => currentItems.filter((item) => item.id !== buttonId));
  }

  function handleStartNewBroadcastAudiencePreset() {
    setSelectedBroadcastAudiencePresetId(null);
    setBroadcastAudiencePresetName("");
    setBroadcastAudiencePresetDescription("");
    setBroadcastAudiencePresetError(null);
    setBroadcastAudiencePresetEditor({ ...EMPTY_BROADCAST_AUDIENCE_EDITOR_STATE });
  }

  function handleSelectBroadcastAudiencePreset(preset: AdminBroadcastAudiencePreset) {
    setSelectedBroadcastAudiencePresetId(preset.id);
    setBroadcastAudiencePresetName(preset.name);
    setBroadcastAudiencePresetDescription(preset.description || "");
    setBroadcastAudiencePresetError(null);
    setBroadcastAudiencePresetEditor(
      createBroadcastAudienceEditorState(preset.audience, preset.channels),
    );
  }

  function handleApplyBroadcastAudiencePreset(preset: AdminBroadcastAudiencePreset) {
    if (selectedBroadcast && !broadcastIsDraft) {
      setError("Применять сохранённый сегмент можно только к новому или черновику");
      return;
    }

    markBroadcastEditorDirty();
    applyBroadcastAudienceToEditor(preset.audience, preset.channels);
    setNotice(`Сегмент "${preset.name}" применён к текущему черновику`);
  }

  function handleSelectBroadcastAudiencePresetForCampaign(presetId: string) {
    const nextPresetId = Number.parseInt(presetId, 10);
    if (!Number.isInteger(nextPresetId)) {
      return;
    }

    const preset = broadcastAudiencePresetItems.find((item) => item.id === nextPresetId);
    if (!preset) {
      return;
    }

    handleApplyBroadcastAudiencePreset(preset);
  }

  function buildBroadcastAudiencePayload(): AdminBroadcastAudience {
    return buildBroadcastAudiencePayloadFromEditor({
      segment: broadcastAudienceSegment,
      excludeBlocked: broadcastAudienceExcludeBlocked,
      manualTargetsInput: broadcastManualAudienceTargetsInput,
      lastSeenOlderThanDays: broadcastLastSeenOlderThanDays,
      includeNeverSeen: broadcastIncludeNeverSeen,
      pendingPaymentOlderThanMinutes: broadcastPendingPaymentOlderThanMinutes,
      pendingPaymentWithinLastDays: broadcastPendingPaymentWithinLastDays,
      failedPaymentWithinLastDays: broadcastFailedPaymentWithinLastDays,
      subscriptionExpiredFromDays: broadcastSubscriptionExpiredFromDays,
      subscriptionExpiredToDays: broadcastSubscriptionExpiredToDays,
      cooldownDays: broadcastCooldownDays,
      cooldownKey: broadcastCooldownKey,
      telegramQuietHoursStart: broadcastTelegramQuietHoursStart,
      telegramQuietHoursEnd: broadcastTelegramQuietHoursEnd,
      sendInApp: broadcastSendInApp,
      sendTelegram: broadcastSendTelegram,
    });
  }

  async function handleSaveBroadcast(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      return;
    }
    if (!broadcastIsDraft) {
      setError("Редактирование доступно только для черновика. Для новой версии создай новый черновик.");
      return;
    }

    const trimmedName = broadcastName.trim();
    const trimmedTitle = broadcastTitle.trim();
    const trimmedBody = broadcastBodyHtml.trim();
    const trimmedImageUrl = broadcastImageUrl.trim();
    const channels = broadcastChannels;

    if (!trimmedName || !trimmedTitle || !trimmedBody) {
      setError("Название, заголовок и текст рассылки обязательны");
      return;
    }
    if (channels.length === 0) {
      setError("Выбери хотя бы один канал доставки");
      return;
    }
    if (broadcastContentType === "photo" && !trimmedImageUrl) {
      setError("Для фото-рассылки нужен image URL");
      return;
    }

    let audience: AdminBroadcastAudience;
    try {
      audience = buildBroadcastAudiencePayload();
    } catch (audienceError) {
      setError(audienceError instanceof Error ? audienceError.message : "Некорректные параметры аудитории");
      return;
    }

    const buttons: AdminBroadcastButton[] = [];
    for (const button of broadcastButtonDrafts) {
      const text = button.text.trim();
      const url = button.url.trim();
      if (!text && !url) {
        continue;
      }
      if (!text || !url) {
        setError("У Telegram-кнопки должны быть заполнены и текст, и URL");
        return;
      }
      buttons.push({ text, url });
    }

    setBroadcastSubmitting(true);
    setError(null);

    try {
      const payload = {
        name: trimmedName,
        title: trimmedTitle,
        body_html: trimmedBody,
        content_type: broadcastContentType,
        image_url: broadcastContentType === "photo" ? trimmedImageUrl : null,
        channels,
        buttons,
        audience,
      };
      const isEditing = selectedBroadcastId !== null;
      const broadcast = await adminFetch<AdminBroadcast>(
        isEditing ? `/api/v1/admin/broadcasts/${selectedBroadcastId}` : "/api/v1/admin/broadcasts",
        token,
        {
          method: isEditing ? "PUT" : "POST",
          body: JSON.stringify(payload),
        },
      );
      setBroadcastEditorDirty(false);
      setBroadcastSelectionMode("existing");
      setSelectedBroadcast(broadcast);
      setSelectedBroadcastId(broadcast.id);
      setBroadcastEstimate({
        channels: broadcast.channels,
        audience: broadcast.audience,
        estimated_total_accounts: broadcast.estimated_total_accounts,
        estimated_in_app_recipients: broadcast.estimated_in_app_recipients,
        estimated_telegram_recipients: broadcast.estimated_telegram_recipients,
      });
      setBroadcastEstimateError(null);
      setNotice(isEditing ? "Черновик рассылки обновлен" : "Черновик рассылки создан");
      await loadBroadcasts(token);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Не удалось сохранить черновик рассылки");
    } finally {
      setBroadcastSubmitting(false);
    }
  }

  async function handleCreateBroadcastAudiencePreset() {
    if (!token) {
      return;
    }

    const trimmedName = broadcastAudiencePresetName.trim();
    const trimmedDescription = broadcastAudiencePresetDescription.trim();
    if (!trimmedName) {
      setBroadcastAudiencePresetError("Укажи название сегмента");
      return;
    }
    if (broadcastAudiencePresetChannels.length === 0) {
      setBroadcastAudiencePresetError("Выбери хотя бы один канал доставки");
      return;
    }

    let audience: AdminBroadcastAudience;
    try {
      audience = buildBroadcastAudiencePayloadFromEditor(broadcastAudiencePresetEditor);
    } catch (audienceError) {
      setBroadcastAudiencePresetError(
        audienceError instanceof Error ? audienceError.message : "Некорректные параметры аудитории",
      );
      return;
    }

    setBroadcastAudiencePresetSubmitting(true);
    setBroadcastAudiencePresetError(null);
    setError(null);
    setNotice(null);

    try {
      const preset = await adminFetch<AdminBroadcastAudiencePreset>(
        "/api/v1/admin/broadcasts/audiences",
        token,
        {
          method: "POST",
          body: JSON.stringify({
            name: trimmedName,
            description: trimmedDescription || null,
            channels: broadcastAudiencePresetChannels,
            audience,
          }),
        },
      );
      await loadBroadcastAudiencePresets(token);
      setSelectedBroadcastAudiencePresetId(preset.id);
      setNotice(`Сегмент "${preset.name}" сохранён`);
    } catch (submitError) {
      setBroadcastAudiencePresetError(
        submitError instanceof Error ? submitError.message : "Не удалось сохранить сегмент",
      );
    } finally {
      setBroadcastAudiencePresetSubmitting(false);
    }
  }

  async function handleUpdateBroadcastAudiencePreset() {
    if (!token || selectedBroadcastAudiencePresetId === null) {
      return;
    }

    const trimmedName = broadcastAudiencePresetName.trim();
    const trimmedDescription = broadcastAudiencePresetDescription.trim();
    if (!trimmedName) {
      setBroadcastAudiencePresetError("Укажи название сегмента");
      return;
    }
    if (broadcastAudiencePresetChannels.length === 0) {
      setBroadcastAudiencePresetError("Выбери хотя бы один канал доставки");
      return;
    }

    let audience: AdminBroadcastAudience;
    try {
      audience = buildBroadcastAudiencePayloadFromEditor(broadcastAudiencePresetEditor);
    } catch (audienceError) {
      setBroadcastAudiencePresetError(
        audienceError instanceof Error ? audienceError.message : "Некорректные параметры аудитории",
      );
      return;
    }

    setBroadcastAudiencePresetSubmitting(true);
    setBroadcastAudiencePresetError(null);
    setError(null);
    setNotice(null);

    try {
      const preset = await adminFetch<AdminBroadcastAudiencePreset>(
        `/api/v1/admin/broadcasts/audiences/${selectedBroadcastAudiencePresetId}`,
        token,
        {
          method: "PUT",
          body: JSON.stringify({
            name: trimmedName,
            description: trimmedDescription || null,
            channels: broadcastAudiencePresetChannels,
            audience,
          }),
        },
      );
      await loadBroadcastAudiencePresets(token);
      setSelectedBroadcastAudiencePresetId(preset.id);
      setNotice(`Сегмент "${preset.name}" обновлён`);
    } catch (submitError) {
      setBroadcastAudiencePresetError(
        submitError instanceof Error ? submitError.message : "Не удалось обновить сегмент",
      );
    } finally {
      setBroadcastAudiencePresetSubmitting(false);
    }
  }

  async function handleDeleteBroadcastAudiencePreset() {
    if (!token || selectedBroadcastAudiencePresetId === null || !selectedBroadcastAudiencePreset) {
      return;
    }

    if (!window.confirm(`Удалить сегмент "${selectedBroadcastAudiencePreset.name}"?`)) {
      return;
    }

    setBroadcastAudiencePresetSubmitting(true);
    setBroadcastAudiencePresetError(null);
    setError(null);
    setNotice(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/admin/broadcasts/audiences/${selectedBroadcastAudiencePresetId}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );
      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }

      await loadBroadcastAudiencePresets(token);
      handleStartNewBroadcastAudiencePreset();
      setNotice(`Сегмент "${selectedBroadcastAudiencePreset.name}" удалён`);
    } catch (deleteError) {
      setBroadcastAudiencePresetError(
        deleteError instanceof Error ? deleteError.message : "Не удалось удалить сегмент",
      );
    } finally {
      setBroadcastAudiencePresetSubmitting(false);
    }
  }

  async function refreshBroadcastRuntimeState(activeToken: string, broadcastId?: number | null) {
    await loadBroadcasts(activeToken);
    await loadBroadcastRuns(activeToken);
    if (broadcastId !== null && broadcastId !== undefined) {
      await loadBroadcastDetail(broadcastId, activeToken);
    }
  }

  async function handleRefreshBroadcastWorkspace() {
    if (!token) {
      return;
    }

    setBroadcastWorkspaceRefreshing(true);
    setError(null);
    try {
      await Promise.all([
        refreshBroadcastRuntimeState(token, selectedBroadcastId),
        loadBroadcastAudiencePresets(token),
      ]);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Не удалось обновить workspace рассылок");
    } finally {
      setBroadcastWorkspaceRefreshing(false);
    }
  }

  async function handleDeleteBroadcastDraft() {
    if (!token || selectedBroadcastId === null) {
      return;
    }

    if (!window.confirm("Удалить этот черновик рассылки?")) {
      return;
    }

    setBroadcastRuntimeSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/broadcasts/${selectedBroadcastId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }

      setBroadcastSelectionMode("existing");
      setSelectedBroadcastId(null);
      setSelectedBroadcast(null);
      resetBroadcastEditorForm();
      setSelectedBroadcastRunId(null);
      setSelectedBroadcastRun(null);
      setBroadcastRunDeliveries([]);
      setBroadcastRunDeliveriesTotal(0);
      await loadBroadcasts(token);
      await loadBroadcastRuns(token);
      setNotice("Черновик рассылки удален");
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Не удалось удалить черновик");
    } finally {
      setBroadcastRuntimeSubmitting(false);
    }
  }

  async function submitBroadcastRuntimeAction(
    action: "send-now" | "schedule" | "pause" | "resume" | "cancel",
  ) {
    if (!token || selectedBroadcastId === null) {
      return;
    }
    if (broadcastEditorDirty && (action === "send-now" || action === "schedule")) {
      setError("Сначала сохрани черновик, затем запускай боевое действие.");
      return;
    }

    const idempotencyKey =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `broadcast-runtime-${Date.now()}`;

    const trimmedComment = broadcastRuntimeComment.trim();
    const payload: Record<string, string | null> = {
      comment: trimmedComment || null,
      idempotency_key: idempotencyKey,
    };
    if (action === "schedule") {
      if (!broadcastScheduleAtInput) {
        setError("Для schedule укажи дату и время по Москве");
        return;
      }
      payload.scheduled_at = buildMoscowScheduleIso(broadcastScheduleAtInput);
    }

    setBroadcastRuntimeSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await adminFetch<AdminBroadcast>(
        `/api/v1/admin/broadcasts/${selectedBroadcastId}/${action}`,
        token,
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      );
      setSelectedBroadcast(updated);
      await refreshBroadcastRuntimeState(token, updated.id);
      setNotice(
        action === "send-now"
          ? "Боевой запуск создан"
          : action === "schedule"
            ? "Рассылка поставлена в расписание"
            : action === "pause"
              ? "Рассылка поставлена на паузу"
              : action === "resume"
                ? "Рассылка возобновлена"
                : "Рассылка отменена",
      );
    } catch (runtimeError) {
      setError(runtimeError instanceof Error ? runtimeError.message : "Не удалось выполнить действие с рассылкой");
    } finally {
      setBroadcastRuntimeSubmitting(false);
    }
  }

  async function handleBalanceAdjustment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!token || !selectedAccount) {
      return;
    }

    const parsedAmount = Number.parseInt(balanceAdjustmentAmount, 10);
    const trimmedComment = balanceAdjustmentComment.trim();

    if (!Number.isInteger(parsedAmount) || parsedAmount === 0) {
      setError("Сумма должна быть целым числом и не равняться нулю");
      return;
    }

    if (!trimmedComment) {
      setError("Комментарий обязателен");
      return;
    }

    setBalanceSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const idempotencyKey =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `admin-adjust-${Date.now()}`;

      const response = await adminFetch<AdminBalanceAdjustmentResponse>(
        `/api/v1/admin/accounts/${selectedAccount.id}/balance-adjustments`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            amount: parsedAmount,
            comment: trimmedComment,
            idempotency_key: idempotencyKey,
          }),
        },
      );

      const refreshedAccount = await loadAccountDetail(selectedAccount.id, token);
      if (refreshedAccount) {
        updateAccountListSnapshot(refreshedAccount);
      } else {
        setAccountItems((items) =>
          items.map((item) =>
            item.id === response.account_id
              ? {
                  ...item,
                  balance: response.balance,
                }
              : item,
          ),
        );
      }

      await loadLedgerHistory(selectedAccount.id, token, {
        offset: 0,
        append: false,
        entryType: ledgerHistoryFilter,
      });
      await loadAccountEventHistory(selectedAccount.id, token, {
        offset: 0,
        append: false,
        eventType: accountEventTypeFilter,
        outcome: accountEventOutcomeFilter,
        source: accountEventSourceFilter,
        requestId: accountEventRequestIdFilter,
      });
      await loadDashboard(token);
      setBalanceAdjustmentAmount("");
      setBalanceAdjustmentComment("");
      setNotice(
        `Корректировка проведена: ${
          response.ledger_entry.amount > 0 ? "зачислено" : "списано"
        } ${formatMoney(Math.abs(response.ledger_entry.amount), response.ledger_entry.currency)}.`,
      );
    } catch (adjustmentError) {
      setError(
        adjustmentError instanceof Error
          ? adjustmentError.message
          : "Не удалось провести корректировку баланса",
      );
    } finally {
      setBalanceSubmitting(false);
    }
  }

  async function handleSubscriptionGrant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!token || !selectedAccount) {
      return;
    }

    const trimmedComment = subscriptionGrantComment.trim();
    if (!subscriptionGrantPlanCode) {
      setError("Выбери тариф для выдачи");
      return;
    }

    if (!trimmedComment) {
      setError("Комментарий обязателен");
      return;
    }

    setSubscriptionSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const idempotencyKey =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `admin-grant-${Date.now()}`;

      const response = await adminFetch<AdminSubscriptionGrantResponse>(
        `/api/v1/admin/accounts/${selectedAccount.id}/subscription-grants`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            plan_code: subscriptionGrantPlanCode,
            comment: trimmedComment,
            idempotency_key: idempotencyKey,
          }),
        },
      );

      const refreshedAccount = await loadAccountDetail(selectedAccount.id, token);
      if (refreshedAccount) {
        updateAccountListSnapshot(refreshedAccount);
      } else {
        setAccountItems((items) =>
          items.map((item) =>
            item.id === response.account_id
              ? {
                  ...item,
                  subscription_status: response.subscription_status,
                  subscription_expires_at: response.subscription_expires_at,
                }
              : item,
          ),
        );
      }

      await loadAccountEventHistory(selectedAccount.id, token, {
        offset: 0,
        append: false,
        eventType: accountEventTypeFilter,
        outcome: accountEventOutcomeFilter,
        source: accountEventSourceFilter,
        requestId: accountEventRequestIdFilter,
      });
      await loadDashboard(token);
      setSubscriptionGrantComment("");
      setNotice(
        `Подписка выдана: ${selectedGrantPlan?.name || response.plan_code} до ${formatDate(
          response.subscription_expires_at,
        )}.`,
      );
    } catch (grantError) {
      setError(
        grantError instanceof Error ? grantError.message : "Не удалось выдать подписку",
      );
    } finally {
      setSubscriptionSubmitting(false);
    }
  }

  async function handleAccountStatusChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!token || !selectedAccount) {
      return;
    }

    const trimmedComment = statusChangeComment.trim();
    if (!trimmedComment) {
      setError("Комментарий обязателен");
      return;
    }

    const targetStatus: "active" | "blocked" =
      selectedAccount.status === "blocked" ? "active" : "blocked";

    setStatusSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const idempotencyKey =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `admin-status-${Date.now()}`;

      const response = await adminFetch<AdminAccountStatusChangeResponse>(
        `/api/v1/admin/accounts/${selectedAccount.id}/status`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            status: targetStatus,
            comment: trimmedComment,
            idempotency_key: idempotencyKey,
          }),
        },
      );

      const refreshedAccount = await loadAccountDetail(selectedAccount.id, token);
      if (refreshedAccount) {
        updateAccountListSnapshot(refreshedAccount);
      } else {
        setAccountItems((items) =>
          items.map((item) =>
            item.id === response.account_id
              ? {
                  ...item,
                  status: response.status,
                }
              : item,
          ),
        );
      }

      await loadAccountEventHistory(selectedAccount.id, token, {
        offset: 0,
        append: false,
        eventType: accountEventTypeFilter,
        outcome: accountEventOutcomeFilter,
        source: accountEventSourceFilter,
        requestId: accountEventRequestIdFilter,
      });
      await loadDashboard(token);
      setStatusChangeComment("");
      setNotice(
        response.status === "blocked"
          ? "Полная блокировка включена. Protected API, Telegram WebApp auth и команды бота для этого пользователя теперь режутся."
          : "Полная блокировка снята.",
      );
    } catch (statusError) {
      setError(
        statusError instanceof Error ? statusError.message : "Не удалось изменить статус пользователя",
      );
    } finally {
      setStatusSubmitting(false);
    }
  }

  async function handleLoadMoreLedgerHistory() {
    if (!token || !selectedAccountId || !hasMoreLedgerHistory || ledgerHistoryLoadingMore) {
      return;
    }

    await loadLedgerHistory(selectedAccountId, token, {
      offset: ledgerHistoryItems.length,
      append: true,
      entryType: ledgerHistoryFilter,
    });
  }

  function handleApplyAccountEventFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAccountEventRequestIdFilter(accountEventRequestIdInput.trim());
  }

  function handleResetAccountEventFilters() {
    setAccountEventTypeFilter("all");
    setAccountEventOutcomeFilter("all");
    setAccountEventSourceFilter("all");
    setAccountEventRequestIdInput("");
    setAccountEventRequestIdFilter("");
  }

  async function handleLoadMoreAccountEventHistory() {
    if (
      !token ||
      !selectedAccountId ||
      !hasMoreAccountEventHistory ||
      accountEventHistoryLoadingMore
    ) {
      return;
    }

    await loadAccountEventHistory(selectedAccountId, token, {
      offset: accountEventHistoryItems.length,
      append: true,
      eventType: accountEventTypeFilter,
      outcome: accountEventOutcomeFilter,
      source: accountEventSourceFilter,
      requestId: accountEventRequestIdFilter,
    });
  }

  function handleApplyGlobalEventSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setGlobalEventSearchFilters(normalizeGlobalEventSearchFilters(globalEventSearchDraft));
  }

  function handleResetGlobalEventSearch() {
    setGlobalEventSearchDraft({ ...EMPTY_GLOBAL_EVENT_SEARCH_FILTERS });
    setGlobalEventSearchFilters({ ...EMPTY_GLOBAL_EVENT_SEARCH_FILTERS });
  }

  async function handleLoadMoreGlobalEvents() {
    if (!token || !hasMoreGlobalEvents || globalEventLoadingMore) {
      return;
    }

    await loadGlobalEventSearch(token, {
      offset: globalEventItems.length,
      append: true,
      filters: globalEventSearchFilters,
    });
  }

  async function handleOpenGlobalEventAccount(eventItem: AdminGlobalAccountEventLog) {
    if (!token || !eventItem.account_id) {
      return;
    }

    setError(null);
    setNotice(null);
    setAccountEventTypeFilter("all");
    setAccountEventOutcomeFilter("all");
    setAccountEventSourceFilter("all");
    setAccountEventRequestIdInput(eventItem.request_id || "");
    setAccountEventRequestIdFilter(eventItem.request_id || "");
    setActiveView("accounts");
    await loadAccountDetail(eventItem.account_id, token);
  }

  async function handleWithdrawalStatusChange(targetStatus: "in_progress" | "paid" | "rejected") {
    if (!token || !selectedWithdrawal) {
      return;
    }

    const currentWithdrawal = selectedWithdrawal;
    const trimmedComment = withdrawalComment.trim();
    if (!trimmedComment) {
      setError("Комментарий обязателен");
      return;
    }

    setWithdrawalSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const idempotencyKey =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `admin-withdrawal-${Date.now()}`;

      const response = await adminFetch<AdminWithdrawalStatusChangeResponse>(
        `/api/v1/admin/withdrawals/${currentWithdrawal.id}/status`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            status: targetStatus,
            comment: trimmedComment,
            idempotency_key: idempotencyKey,
          }),
        },
      );

      await Promise.all([loadWithdrawals(token), loadDashboard(token)]);
      setWithdrawalComment("");

      if (targetStatus === "in_progress") {
        setNotice(`Заявка на вывод #${response.withdrawal_id} переведена в работу.`);
      } else if (targetStatus === "paid") {
        setNotice(`Заявка на вывод #${response.withdrawal_id} отмечена как выплаченная.`);
      } else {
        setNotice(
          `Заявка на вывод #${response.withdrawal_id} отклонена. ${formatMoney(currentWithdrawal.amount)} возвращены на баланс пользователя.`,
        );
      }
    } catch (withdrawalError) {
      setError(
        withdrawalError instanceof Error
          ? withdrawalError.message
          : "Не удалось изменить статус заявки на вывод",
      );
    } finally {
      setWithdrawalSubmitting(false);
    }
  }

  if (!token) {
    return (
      <main className="admin-shell admin-shell--auth">
          <form className="auth-form auth-form--standalone" onSubmit={handleLogin}>
            <label>
              <span>{t("admin.auth.loginLabel")}</span>
              <input
                autoComplete="username"
                value={login}
                onChange={(event) => setLogin(event.target.value)}
                placeholder={t("admin.auth.loginPlaceholder")}
                required
              />
            </label>
            <label>
              <span>{t("admin.auth.passwordLabel")}</span>
              <input
                autoComplete="current-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={t("admin.auth.passwordPlaceholder")}
                required
              />
            </label>
            {error ? <div className="form-error">{error}</div> : null}
            <button type="submit" disabled={submitting}>
              {submitting ? t("admin.auth.submitting") : t("admin.auth.submit")}
            </button>
          </form>
        </main>
    );
  }

  return (
    <main className="admin-shell">
      <section className="dashboard-hero">
        <div className="hero-copy">
          <span className="eyebrow">{t("admin.dashboard.heroEyebrow")}</span>
          <h1>{t("admin.dashboard.heroTitle")}</h1>
          <p>{t("admin.dashboard.heroDescription")}</p>
        </div>
        <div className="hero-side">
          <div className="hero-blade" aria-hidden="true">
            <span className="hero-blade__beam" />
            <span className="hero-blade__hilt" />
          </div>
          <div className="hero-actions">
            <button className="ghost-button" type="button" onClick={handleRefresh} disabled={loading}>
              {loading ? t("admin.actions.refreshing") : t("admin.actions.refresh")}
            </button>
            <button className="ghost-button" type="button" onClick={handleLogout}>
              {t("admin.actions.logout")}
            </button>
          </div>
        </div>
      </section>

      <nav className="module-nav" aria-label={t("admin.navigation.modulesAriaLabel")}>
        <button
          type="button"
          className={activeView === "dashboard" ? "module-nav__button module-nav__button--active" : "module-nav__button"}
          onClick={() => setActiveView("dashboard")}
        >
          {t("admin.navigation.dashboard")}
        </button>
        <button
          type="button"
          className={activeView === "accounts" ? "module-nav__button module-nav__button--active" : "module-nav__button"}
          onClick={() => setActiveView("accounts")}
        >
          {t("admin.navigation.accounts")}
        </button>
        <button
          type="button"
          className={activeView === "events" ? "module-nav__button module-nav__button--active" : "module-nav__button"}
          onClick={() => setActiveView("events")}
        >
          {t("admin.navigation.events")}
        </button>
        <button
          type="button"
          className={
            activeView === "broadcasts"
              ? "module-nav__button module-nav__button--active"
              : "module-nav__button"
          }
          onClick={() => setActiveView("broadcasts")}
        >
          {t("admin.navigation.broadcasts")}
        </button>
        <button
          type="button"
          className={
            activeView === "plans"
              ? "module-nav__button module-nav__button--active"
              : "module-nav__button"
          }
          onClick={() => setActiveView("plans")}
        >
          {t("admin.navigation.plans")}
        </button>
        <button
          type="button"
          className={
            activeView === "promos"
              ? "module-nav__button module-nav__button--active"
              : "module-nav__button"
          }
          onClick={() => setActiveView("promos")}
        >
          {t("admin.navigation.promos")}
        </button>
        <button
          type="button"
          className={
            activeView === "withdrawals"
              ? "module-nav__button module-nav__button--active"
              : "module-nav__button"
          }
          onClick={() => setActiveView("withdrawals")}
        >
          {t("admin.navigation.withdrawals")}
        </button>
      </nav>

      {error ? <div className="form-error form-error--banner">{error}</div> : null}
      {notice ? <div className="form-success form-success--banner">{notice}</div> : null}

      {activeView === "dashboard" ? (
        <>
          <section className="dashboard-grid">
            <article className="profile-card">
              <span className="eyebrow">{t("admin.dashboard.profileEyebrow")}</span>
              <h2>{profile?.full_name || profile?.username || t("admin.dashboard.profileFallbackName")}</h2>
              <dl className="profile-list">
                <div>
                  <dt>{t("admin.dashboard.profileLogin")}</dt>
                  <dd>{profile?.username}</dd>
                </div>
                <div>
                  <dt>{t("admin.dashboard.profileEmail")}</dt>
                  <dd>{profile?.email || t("admin.dashboard.profileEmailMissing")}</dd>
                </div>
                <div>
                  <dt>{t("admin.dashboard.profileRole")}</dt>
                  <dd>
                    {profile?.is_superuser
                      ? t("admin.dashboard.profileRoleSuperuser")
                      : t("admin.dashboard.profileRoleOperator")}
                  </dd>
                </div>
                <div>
                  <dt>{t("admin.dashboard.profileLastLogin")}</dt>
                  <dd>{formatDate(profile?.last_login_at || null)}</dd>
                </div>
              </dl>
            </article>

            <section className="metrics-grid">
              {cards.map((card) => (
                <DashboardCard key={card.label} {...card} />
              ))}
            </section>
          </section>

          <section className="dashboard-panels">
            <article className="dashboard-panel">
              <div className="dashboard-panel__header">
                <div>
                  <span className="eyebrow">{t("admin.dashboard.financeEyebrow")}</span>
                  <h2>{t("admin.dashboard.financeTitle")}</h2>
                </div>
                <p>{t("admin.dashboard.financeDescription")}</p>
              </div>
              <div className="metrics-grid metrics-grid--dense">
                {financeCards.map((card) => (
                  <DashboardCard key={card.label} {...card} />
                ))}
              </div>
            </article>

            <article className="dashboard-panel">
              <div className="dashboard-panel__header">
                <div>
                  <span className="eyebrow">{t("admin.dashboard.activityEyebrow")}</span>
                  <h2>{t("admin.dashboard.activityTitle")}</h2>
                </div>
                <p>{t("admin.dashboard.activityDescription")}</p>
              </div>
              <div className="metrics-grid metrics-grid--dense">
                {activityCards.map((card) => (
                  <DashboardCard key={card.label} {...card} />
                ))}
              </div>
            </article>
          </section>
        </>
      ) : activeView === "accounts" ? (
        <section className="accounts-layout">
          <section className="accounts-panel">
            <div className="dashboard-panel__header accounts-panel__header">
              <div>
                <span className="eyebrow">{t("admin.accounts.directoryEyebrow")}</span>
                <h2>{t("admin.accounts.directoryTitle")}</h2>
              </div>
              <div className="accounts-panel__actions">
                <p>{t("admin.accounts.directoryDescription")}</p>
                <div className="accounts-panel__actions-row">
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={handleExportAccounts}
                    disabled={accountsExporting}
                  >
                    {accountsExporting
                      ? t("admin.accounts.export.loading")
                      : t("admin.accounts.export.action")}
                  </button>
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={handleResetAccountListFilters}
                    disabled={!accountListFiltersActive}
                  >
                    {t("admin.accounts.table.resetFilters")}
                  </button>
                </div>
              </div>
            </div>

            <div className="accounts-table__meta">
              <span>{t("admin.accounts.list.summary", { count: accountItems.length, total: accountTotal })}</span>
              <span>{t("admin.accounts.table.filterHint")}</span>
            </div>

            <div className="accounts-table__wrap">
              <table className="accounts-table">
                <thead>
                  <tr>
                    <th scope="col">
                      <div className="accounts-table__column-head">
                        <span>{t("admin.accounts.table.columns.user")}</span>
                        <button
                          className="table-sort-button"
                          type="button"
                          onClick={() => handleAccountListSortChange("user", "asc")}
                          aria-label={t("admin.accounts.table.sortButtons.user")}
                        >
                          {renderAccountSortIndicator(accountListDraftFilters, "user")}
                        </button>
                      </div>
                      <input
                        value={accountListDraftFilters.userQuery}
                        onChange={(event) =>
                          handleAccountListTextFilterChange("userQuery", event.target.value)
                        }
                        placeholder={t("admin.accounts.table.filters.user")}
                      />
                    </th>
                    <th scope="col">
                      <div className="accounts-table__column-head">
                        <span>{t("admin.accounts.table.columns.telegram")}</span>
                        <button
                          className="table-sort-button"
                          type="button"
                          onClick={() => handleAccountListSortChange("telegram_id", "asc")}
                          aria-label={t("admin.accounts.table.sortButtons.telegram")}
                        >
                          {renderAccountSortIndicator(accountListDraftFilters, "telegram_id")}
                        </button>
                      </div>
                      <input
                        value={accountListDraftFilters.telegramQuery}
                        onChange={(event) =>
                          handleAccountListTextFilterChange("telegramQuery", event.target.value)
                        }
                        placeholder={t("admin.accounts.table.filters.telegram")}
                        inputMode="numeric"
                      />
                    </th>
                    <th scope="col">
                      <div className="accounts-table__column-head">
                        <span>{t("admin.accounts.table.columns.email")}</span>
                        <button
                          className="table-sort-button"
                          type="button"
                          onClick={() => handleAccountListSortChange("email", "asc")}
                          aria-label={t("admin.accounts.table.sortButtons.email")}
                        >
                          {renderAccountSortIndicator(accountListDraftFilters, "email")}
                        </button>
                      </div>
                      <input
                        value={accountListDraftFilters.emailQuery}
                        onChange={(event) =>
                          handleAccountListTextFilterChange("emailQuery", event.target.value)
                        }
                        placeholder={t("admin.accounts.table.filters.email")}
                      />
                    </th>
                    <th scope="col">
                      <div className="accounts-table__column-head">
                        <span>{t("admin.accounts.table.columns.balance")}</span>
                        <button
                          className="table-sort-button"
                          type="button"
                          onClick={() => handleAccountListSortChange("balance", "desc")}
                          aria-label={t("admin.accounts.table.sortButtons.balance")}
                        >
                          {renderAccountSortIndicator(accountListDraftFilters, "balance")}
                        </button>
                      </div>
                    </th>
                    <th scope="col">
                      <div className="accounts-table__column-head">
                        <span>{t("admin.accounts.table.columns.status")}</span>
                      </div>
                      <select
                        value={accountListDraftFilters.status}
                        onChange={(event) =>
                          handleAccountListSelectFilterChange(
                            "status",
                            event.target.value as AccountListStatusFilter,
                          )
                        }
                      >
                        <option value="all">{t("admin.accounts.table.statusOptions.all")}</option>
                        <option value="active">{t("admin.common.active")}</option>
                        <option value="blocked">{t("admin.common.blocked")}</option>
                      </select>
                    </th>
                    <th scope="col">
                      <div className="accounts-table__column-head">
                        <span>{t("admin.accounts.table.columns.subscription")}</span>
                        <button
                          className="table-sort-button"
                          type="button"
                          onClick={() => handleAccountListSortChange("subscription_expires_at", "desc")}
                          aria-label={t("admin.accounts.table.sortButtons.subscription")}
                        >
                          {renderAccountSortIndicator(accountListDraftFilters, "subscription_expires_at")}
                        </button>
                      </div>
                      <select
                        value={accountListDraftFilters.subscription}
                        onChange={(event) =>
                          handleAccountListSelectFilterChange(
                            "subscription",
                            event.target.value as AccountListSubscriptionFilter,
                          )
                        }
                      >
                        <option value="all">{t("admin.accounts.table.subscriptionOptions.all")}</option>
                        <option value="active">{t("admin.accounts.table.subscriptionOptions.active")}</option>
                        <option value="inactive">{t("admin.accounts.table.subscriptionOptions.inactive")}</option>
                        <option value="none">{t("admin.accounts.table.subscriptionOptions.none")}</option>
                      </select>
                    </th>
                    <th scope="col">
                      <div className="accounts-table__column-head">
                        <span>{t("admin.accounts.table.columns.referrals")}</span>
                        <button
                          className="table-sort-button"
                          type="button"
                          onClick={() => handleAccountListSortChange("referrals_count", "desc")}
                          aria-label={t("admin.accounts.table.sortButtons.referrals")}
                        >
                          {renderAccountSortIndicator(accountListDraftFilters, "referrals_count")}
                        </button>
                      </div>
                    </th>
                    <th scope="col">
                      <div className="accounts-table__column-head">
                        <span>{t("admin.accounts.table.columns.lastSeen")}</span>
                        <button
                          className="table-sort-button"
                          type="button"
                          onClick={() => handleAccountListSortChange("last_seen_at", "desc")}
                          aria-label={t("admin.accounts.table.sortButtons.lastSeen")}
                        >
                          {renderAccountSortIndicator(accountListDraftFilters, "last_seen_at")}
                        </button>
                      </div>
                    </th>
                    <th scope="col">
                      <div className="accounts-table__column-head">
                        <span>{t("admin.accounts.table.columns.created")}</span>
                        <button
                          className="table-sort-button"
                          type="button"
                          onClick={() => handleAccountListSortChange("created_at", "desc")}
                          aria-label={t("admin.accounts.table.sortButtons.created")}
                        >
                          {renderAccountSortIndicator(accountListDraftFilters, "created_at")}
                        </button>
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {accountsLoading && accountItems.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="accounts-table__empty">
                        {t("admin.accounts.list.loading")}
                      </td>
                    </tr>
                  ) : accountItems.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="accounts-table__empty">
                        {t("admin.accounts.list.empty")}
                      </td>
                    </tr>
                  ) : (
                    accountItems.map((item) => (
                      <tr
                        key={item.id}
                        className={
                          selectedAccountId === item.id
                            ? "accounts-table__row accounts-table__row--active"
                            : "accounts-table__row"
                        }
                        onClick={() => void handleSelectAccount(item.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            void handleSelectAccount(item.id);
                          }
                        }}
                        tabIndex={0}
                      >
                        <td>
                          <div className="accounts-table__identity">
                            <strong>{formatAccountIdentity(item)}</strong>
                            <small>{formatCompactId(item.id)}</small>
                          </div>
                        </td>
                        <td>{item.telegram_id ?? t("admin.accounts.telegramMissing")}</td>
                        <td>{item.email || t("admin.accounts.emailMissing")}</td>
                        <td>{formatMoney(item.balance)}</td>
                        <td>
                          <span className={`status-pill status-pill--${item.status}`}>
                            {humanizeAccountStatus(item.status)}
                          </span>
                        </td>
                        <td>
                          <div className="accounts-table__subscription">
                            <strong>{humanizeAccountSubscriptionStatus(item.subscription_status)}</strong>
                            <small>
                              {item.subscription_expires_at
                                ? formatDate(item.subscription_expires_at)
                                : t("admin.accounts.table.subscriptionDateMissing")}
                            </small>
                          </div>
                        </td>
                        <td>{item.referrals_count}</td>
                        <td>{formatDate(item.last_seen_at)}</td>
                        <td>{formatDate(item.created_at)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {hasMoreAccounts ? (
              <div className="accounts-table__footer">
                <button
                  className="ghost-button"
                  type="button"
                  onClick={() => void handleLoadMoreAccounts()}
                  disabled={accountsLoading || accountsLoadingMore}
                >
                  {accountsLoadingMore
                    ? t("admin.accounts.list.loadingMore")
                    : t("admin.accounts.list.loadMore")}
                </button>
              </div>
            ) : null}
          </section>

          {detailLoading || selectedAccount ? (
            <div
              className="accounts-detail-modal"
              role="dialog"
              aria-modal="true"
              aria-label={t("admin.accounts.detailEyebrow")}
              onClick={handleCloseAccountDetail}
            >
              <div className="accounts-detail-modal__panel" onClick={(event) => event.stopPropagation()}>
                <div className="accounts-detail-modal__toolbar">
                  <button className="ghost-button" type="button" onClick={handleCloseAccountDetail}>
                    {t("admin.accounts.closeDetail")}
                  </button>
                </div>
                {detailLoading ? <div className="detail-skeleton">{t("admin.accounts.detailLoading")}</div> : null}
                {!detailLoading && selectedAccount ? (
              <>
                <section className="detail-header">
                  <div>
                    <span className="eyebrow">{t("admin.accounts.detailEyebrow")}</span>
                    <h2>{selectedAccount.display_name || selectedAccount.username || selectedAccount.email || selectedAccount.id}</h2>
                    <p>
                      {selectedAccount.email || t("admin.accounts.emailMissing")} ·{" "}
                      {selectedAccount.telegram_id
                        ? `${t("admin.accounts.telegramLabel")} ${selectedAccount.telegram_id}`
                        : t("admin.accounts.telegramNotLinked")}
                    </p>
                  </div>
                  <span className={`status-pill status-pill--${selectedAccount.status}`}>
                    {humanizeAccountStatus(selectedAccount.status)}
                  </span>
                </section>

                <section className="detail-facts-grid">
                  <DetailFact label={t("admin.accounts.detailFacts.balance")} value={formatMoney(selectedAccount.balance)} />
                  <DetailFact
                    label={t("admin.accounts.detailFacts.referralEarnings")}
                    value={formatMoney(selectedAccount.referral_earnings)}
                  />
                  <DetailFact
                    label={t("admin.accounts.detailFacts.subscription")}
                    value={selectedAccount.subscription_status || t("admin.accounts.detailFacts.subscriptionMissing")}
                  />
                  <DetailFact label={t("admin.accounts.detailFacts.created")} value={formatDate(selectedAccount.created_at)} />
                </section>

                <section className="detail-section detail-section--action">
                  <span className="eyebrow">{t("admin.accounts.balanceAdjustment.eyebrow")}</span>
                  <div className="detail-section__intro">
                    <h3>{t("admin.accounts.balanceAdjustment.title")}</h3>
                    <p>{t("admin.accounts.balanceAdjustment.description")}</p>
                  </div>
                  <form className="adjustment-form" onSubmit={handleBalanceAdjustment}>
                    <label className="form-field">
                      <span>{t("admin.accounts.balanceAdjustment.amountLabel")}</span>
                      <input
                        type="number"
                        step="1"
                        value={balanceAdjustmentAmount}
                        onChange={(event) => setBalanceAdjustmentAmount(event.target.value)}
                        placeholder={t("admin.accounts.balanceAdjustment.amountPlaceholder")}
                        required
                      />
                    </label>
                    <label className="form-field form-field--wide">
                      <span>{t("admin.accounts.balanceAdjustment.commentLabel")}</span>
                      <textarea
                        value={balanceAdjustmentComment}
                        onChange={(event) => setBalanceAdjustmentComment(event.target.value)}
                        placeholder={t("admin.accounts.balanceAdjustment.commentPlaceholder")}
                        rows={3}
                        required
                      />
                    </label>
                    <div className="adjustment-form__footer">
                      <span className="form-hint">{t("admin.accounts.balanceAdjustment.hint")}</span>
                      <button className="action-button" type="submit" disabled={balanceSubmitting}>
                        {balanceSubmitting
                          ? t("admin.accounts.balanceAdjustment.submitting")
                          : t("admin.accounts.balanceAdjustment.submit")}
                      </button>
                    </div>
                  </form>
                </section>

                <section className="detail-section detail-section--action">
                  <span className="eyebrow">{t("admin.accounts.subscriptionGrant.eyebrow")}</span>
                  <div className="detail-section__intro">
                    <h3>{t("admin.accounts.subscriptionGrant.title")}</h3>
                    <p>{t("admin.accounts.subscriptionGrant.description")}</p>
                  </div>
                  <form className="adjustment-form" onSubmit={handleSubscriptionGrant}>
                    <label className="form-field">
                      <span>{t("admin.accounts.subscriptionGrant.planLabel")}</span>
                      <select
                        value={subscriptionGrantPlanCode}
                        onChange={(event) => setSubscriptionGrantPlanCode(event.target.value)}
                        disabled={plansLoading || subscriptionPlans.length === 0}
                        required
                      >
                        {subscriptionPlans.length === 0 ? (
                          <option value="">
                            {plansLoading
                              ? t("admin.accounts.subscriptionGrant.plansLoading")
                              : t("admin.accounts.subscriptionGrant.plansUnavailable")}
                          </option>
                        ) : null}
                        {subscriptionPlans.map((plan) => (
                          <option key={plan.code} value={plan.code}>
                            {plan.name} · {plan.duration_days} дн. · {formatMoney(plan.price_rub)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="form-field form-field--wide">
                      <span>{t("admin.accounts.subscriptionGrant.commentLabel")}</span>
                      <textarea
                        value={subscriptionGrantComment}
                        onChange={(event) => setSubscriptionGrantComment(event.target.value)}
                        placeholder={t("admin.accounts.subscriptionGrant.commentPlaceholder")}
                        rows={3}
                        required
                      />
                    </label>
                    <div className="adjustment-form__footer">
                      <span className="form-hint">
                        {selectedGrantPlan
                          ? t("admin.accounts.subscriptionGrant.selectedPlanHint", {
                              name: selectedGrantPlan.name,
                              days: selectedGrantPlan.duration_days,
                            })
                          : t("admin.accounts.subscriptionGrant.plansUnavailableHint")}
                      </span>
                      <button
                        className="action-button"
                        type="submit"
                        disabled={
                          plansLoading || subscriptionPlans.length === 0 || subscriptionSubmitting
                        }
                      >
                        {subscriptionSubmitting
                          ? t("admin.accounts.subscriptionGrant.submitting")
                          : t("admin.accounts.subscriptionGrant.submit")}
                      </button>
                    </div>
                  </form>
                </section>

                <section className="detail-sections-grid">
                  <article className="detail-section">
                    <span className="eyebrow">{t("admin.accounts.identity.eyebrow")}</span>
                    <div className="detail-kv">
                      <div><span>{t("admin.accounts.identity.username")}</span><strong>{selectedAccount.username || "-"}</strong></div>
                      <div><span>{t("admin.accounts.identity.name")}</span><strong>{[selectedAccount.first_name, selectedAccount.last_name].filter(Boolean).join(" ") || "-"}</strong></div>
                      <div><span>{t("admin.accounts.identity.locale")}</span><strong>{selectedAccount.locale || "-"}</strong></div>
                      <div><span>{t("admin.accounts.identity.referralCode")}</span><strong>{selectedAccount.referral_code || "-"}</strong></div>
                      <div><span>{t("admin.accounts.identity.referrals")}</span><strong>{selectedAccount.referrals_count}</strong></div>
                      <div><span>{t("admin.accounts.identity.lastSeen")}</span><strong>{formatDate(selectedAccount.last_seen_at)}</strong></div>
                    </div>
                  </article>

                  <article className="detail-section">
                    <span className="eyebrow">{t("admin.accounts.subscription.eyebrow")}</span>
                    <div className="detail-kv">
                      <div>
                        <span>{t("admin.accounts.subscription.status")}</span>
                        <strong>{selectedAccount.subscription_status || t("admin.accounts.subscription.none")}</strong>
                      </div>
                      <div>
                        <span>{t("admin.accounts.subscription.expires")}</span>
                        <strong>{formatDate(selectedAccount.subscription_expires_at)}</strong>
                      </div>
                      <div>
                        <span>{t("admin.accounts.subscription.trial")}</span>
                        <strong>
                          {selectedAccount.subscription_is_trial
                            ? t("admin.accounts.subscription.yes")
                            : t("admin.accounts.subscription.no")}
                        </strong>
                      </div>
                      <div>
                        <span>{t("admin.accounts.subscription.trialUsed")}</span>
                        <strong>{formatDate(selectedAccount.trial_used_at)}</strong>
                      </div>
                      <div>
                        <span>{t("admin.accounts.subscription.sync")}</span>
                        <strong>{formatDate(selectedAccount.subscription_last_synced_at)}</strong>
                      </div>
                      <div>
                        <span>{t("admin.accounts.subscription.externalId")}</span>
                        <strong>{selectedAccount.remnawave_user_uuid || "-"}</strong>
                      </div>
                    </div>
                    {selectedAccount.subscription_url ? (
                      <a className="detail-link" href={selectedAccount.subscription_url} target="_blank" rel="noreferrer">
                        {t("admin.accounts.subscription.openLink")}
                      </a>
                    ) : null}
                  </article>
                </section>

                <section className="detail-facts-grid detail-facts-grid--compact">
                  <DetailFact
                    label={t("admin.accounts.metrics.ledgerEntries")}
                    value={String(selectedAccount.ledger_entries_count)}
                  />
                  <DetailFact
                    label={t("admin.accounts.metrics.payments")}
                    value={String(selectedAccount.payments_count)}
                  />
                  <DetailFact
                    label={t("admin.accounts.metrics.pendingPayments")}
                    value={String(selectedAccount.pending_payments_count)}
                  />
                  <DetailFact
                    label={t("admin.accounts.metrics.withdrawals")}
                    value={String(selectedAccount.withdrawals_count)}
                  />
                </section>

                <section className="detail-section">
                  <div className="detail-section__header detail-section__header--stacked">
                    <div>
                      <span className="eyebrow">{t("admin.accounts.referralChain.eyebrow")}</span>
                      <h3>Кто привел пользователя и кого привел он</h3>
                    </div>
                    <span className="form-hint">
                      Эффективная ставка текущего аккаунта:{" "}
                      {formatRewardRate(selectedAccount.referral_chain.effective_reward_rate)}
                    </span>
                  </div>

                  <section className="detail-facts-grid detail-facts-grid--compact">
                    <DetailFact
                      label="Direct referrals"
                      value={String(selectedAccount.referral_chain.direct_referrals_count)}
                    />
                    <DetailFact
                      label="Rewarded"
                      value={String(selectedAccount.referral_chain.rewarded_direct_referrals_count)}
                    />
                    <DetailFact
                      label="Pending"
                      value={String(selectedAccount.referral_chain.pending_direct_referrals_count)}
                    />
                    <DetailFact
                      label="Referral earnings"
                      value={formatMoney(selectedAccount.referral_earnings)}
                    />
                  </section>

                  <section className="detail-sections-grid">
                    <article className="detail-section">
                      <span className="eyebrow">Апстрим</span>
                      <div className="activity-list">
                        {selectedAccount.referral_chain.referrer ? (
                          <article className="activity-item">
                            <div>
                              <strong>{formatAccountIdentity(selectedAccount.referral_chain.referrer)}</strong>
                              <span>
                                {selectedAccount.referral_chain.referrer.email ||
                                  selectedAccount.referral_chain.referrer.username ||
                                  "Без email и username"}
                              </span>
                              <span>
                                Подключил {formatDate(selectedAccount.referral_chain.referrer.attributed_at)} ·{" "}
                                {selectedAccount.referral_chain.referrer.telegram_id
                                  ? `Telegram ${selectedAccount.referral_chain.referrer.telegram_id}`
                                  : "Telegram не привязан"}
                              </span>
                            </div>
                            <div className="activity-item__meta">
                              {selectedAccount.referral_chain.referrer.status ? (
                                <span
                                  className={`status-pill status-pill--${selectedAccount.referral_chain.referrer.status}`}
                                >
                                  {humanizeAccountStatus(selectedAccount.referral_chain.referrer.status)}
                                </span>
                              ) : null}
                              <span>
                                Код: {selectedAccount.referral_chain.referrer.referral_code || "не задан"}
                              </span>
                            </div>
                          </article>
                        ) : (
                          <div className="activity-empty">Пользователь пришел без реферера.</div>
                        )}
                      </div>
                    </article>

                    <article className="detail-section">
                      <span className="eyebrow">Даунстрим</span>
                      <div className="activity-list">
                        {selectedAccount.referral_chain.direct_referrals.length === 0 ? (
                          <div className="activity-empty">Прямых рефералов пока нет.</div>
                        ) : (
                          selectedAccount.referral_chain.direct_referrals.map((referral) => (
                            <article key={referral.attribution_id} className="activity-item">
                              <div>
                                <strong>{formatAccountIdentity(referral)}</strong>
                                <span>
                                  {referral.email || referral.username || "Без email и username"}
                                </span>
                                <span>
                                  Подключился {formatDate(referral.attributed_at)} ·{" "}
                                  {referral.telegram_id
                                    ? `Telegram ${referral.telegram_id}`
                                    : "Telegram не привязан"}
                                </span>
                                <span>
                                  {referral.subscription_status
                                    ? `Подписка ${referral.subscription_status} до ${formatDate(referral.subscription_expires_at)}`
                                    : "Подписки пока нет"}
                                </span>
                              </div>
                              <div className="activity-item__meta">
                                <span
                                  className={`status-pill status-pill--${
                                    referral.reward_status === "rewarded" ? "paid" : "new"
                                  }`}
                                >
                                  {humanizeReferralRewardStatus(referral.reward_status)}
                                </span>
                                <strong>
                                  {referral.reward_amount > 0
                                    ? `+${formatMoney(referral.reward_amount)}`
                                    : t("admin.accounts.referrals.noReward")}
                                </strong>
                                <span>
                                  {referral.reward_created_at
                                    ? t("admin.accounts.referrals.rewardedAt", {
                                        date: formatDate(referral.reward_created_at),
                                      })
                                    : t("admin.accounts.referrals.waitingFirstPayment")}
                                </span>
                                {referral.purchase_amount !== null && referral.reward_rate !== null ? (
                                  <span>
                                    {t("admin.accounts.referrals.purchaseRate", {
                                      amount: formatMoney(referral.purchase_amount),
                                      rate: formatRewardRate(referral.reward_rate),
                                    })}
                                  </span>
                                ) : null}
                              </div>
                            </article>
                          ))
                        )}
                      </div>
                    </article>
                  </section>
                </section>

                <section className="detail-section">
                  <span className="eyebrow">{t("admin.accounts.authIdentities.eyebrow")}</span>
                  <div className="activity-list">
                    {selectedAccount.auth_accounts.length === 0 ? (
                      <div className="activity-empty">{t("admin.accounts.authIdentities.empty")}</div>
                    ) : (
                      selectedAccount.auth_accounts.map((identity) => (
                        <article key={`${identity.provider}:${identity.provider_uid}`} className="activity-item">
                          <div>
                            <strong>{identity.provider}</strong>
                            <span>{identity.email || identity.display_name || identity.provider_uid}</span>
                          </div>
                          <span>{formatDate(identity.linked_at)}</span>
                        </article>
                      ))
                    )}
                  </div>
                </section>

                <section className="activity-grid">
                  <article className="detail-section">
                    <div className="detail-section__header detail-section__header--stacked">
                      <div>
                        <span className="eyebrow">{t("admin.accounts.timeline.eyebrow")}</span>
                        <h3>{t("admin.accounts.timeline.title")}</h3>
                      </div>
                      <span className="form-hint">{t("admin.accounts.timeline.description")}</span>
                    </div>
                    <form className="event-filter-grid" onSubmit={handleApplyAccountEventFilters}>
                      <label className="form-field">
                        <span>Event type</span>
                        <select
                          value={accountEventTypeFilter}
                          onChange={(event) =>
                            setAccountEventTypeFilter(event.target.value as AccountEventTypeFilterOption)
                          }
                          disabled={accountEventHistoryLoading}
                        >
                          {ACCOUNT_EVENT_TYPE_FILTER_OPTIONS.map((eventType) => (
                            <option key={eventType} value={eventType}>
                              {eventType === "all"
                                ? t("admin.accounts.timeline.allEvents")
                                : humanizeAccountEventType(eventType)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="form-field">
                        <span>Outcome</span>
                        <select
                          value={accountEventOutcomeFilter}
                          onChange={(event) =>
                            setAccountEventOutcomeFilter(
                              event.target.value as AccountEventOutcomeFilterOption,
                            )
                          }
                          disabled={accountEventHistoryLoading}
                        >
                          {ACCOUNT_EVENT_OUTCOME_FILTER_OPTIONS.map((outcome) => (
                            <option key={outcome} value={outcome}>
                              {outcome === "all" ? "Все outcomes" : humanizeAccountEventOutcome(outcome)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="form-field">
                        <span>Source</span>
                        <select
                          value={accountEventSourceFilter}
                          onChange={(event) =>
                            setAccountEventSourceFilter(event.target.value as AccountEventSourceFilterOption)
                          }
                          disabled={accountEventHistoryLoading}
                        >
                          {ACCOUNT_EVENT_SOURCE_FILTER_OPTIONS.map((source) => (
                            <option key={source} value={source}>
                              {source === "all" ? "Все источники" : humanizeAccountEventSource(source)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="form-field">
                        <span>Request ID</span>
                        <input
                          value={accountEventRequestIdInput}
                          onChange={(event) => setAccountEventRequestIdInput(event.target.value)}
                          placeholder="Например: req_123456"
                        />
                      </label>
                      <div className="event-filter-actions">
                        <button className="ghost-button" type="submit" disabled={accountEventHistoryLoading}>
                          Применить request_id
                        </button>
                        <button
                          className="ghost-button"
                          type="button"
                          onClick={handleResetAccountEventFilters}
                          disabled={!accountEventFiltersActive && !accountEventRequestIdInput}
                        >
                          Сбросить
                        </button>
                      </div>
                    </form>
                    <div className="activity-list">
                      {accountEventHistoryLoading ? (
                        <div className="activity-empty">Загружаем timeline событий...</div>
                      ) : accountEventHistoryItems.length === 0 ? (
                        <div className="activity-empty">
                          {accountEventFiltersActive
                            ? "По текущим фильтрам событий нет."
                            : "Событий пока нет."}
                        </div>
                      ) : (
                        accountEventHistoryItems.map((eventItem) => {
                          const payloadSummary = summarizeAccountEventPayload(eventItem.payload);

                          return (
                            <article key={eventItem.id} className="activity-item">
                              <div className="activity-item__body">
                                <strong>{humanizeAccountEventType(eventItem.event_type)}</strong>
                                <span>{payloadSummary || "Без дополнительного payload"}</span>
                                <span>
                                  {describeAccountEventActor(eventItem)} · source:{" "}
                                  {humanizeAccountEventSource(eventItem.source)}
                                </span>
                                {eventItem.request_id ? (
                                  <span>request_id: {eventItem.request_id}</span>
                                ) : null}
                                {eventItem.payload ? (
                                  <details className="payload-preview">
                                    <summary>Payload JSON</summary>
                                    <pre>{JSON.stringify(eventItem.payload, null, 2)}</pre>
                                  </details>
                                ) : null}
                              </div>
                              <div className="activity-item__meta activity-item__meta--stacked">
                                <span
                                  className={`status-pill ${getAccountEventOutcomePillClass(eventItem.outcome)}`}
                                >
                                  {humanizeAccountEventOutcome(eventItem.outcome)}
                                </span>
                                <span>{formatDate(eventItem.created_at)}</span>
                                <span>#{eventItem.id}</span>
                              </div>
                            </article>
                          );
                        })
                      )}
                    </div>
                    <div className="section-footer">
                      <span className="form-hint">
                        Показано {accountEventHistoryItems.length} из {accountEventHistoryTotal} событий.
                      </span>
                      {hasMoreAccountEventHistory ? (
                        <button
                          className="ghost-button"
                          type="button"
                          onClick={() => void handleLoadMoreAccountEventHistory()}
                          disabled={accountEventHistoryLoading || accountEventHistoryLoadingMore}
                        >
                          {accountEventHistoryLoadingMore ? "Загружаем..." : "Загрузить еще"}
                        </button>
                      ) : null}
                    </div>
                  </article>

                  <article className="detail-section">
                    <div className="detail-section__header detail-section__header--stacked">
                      <div>
                        <span className="eyebrow">История ledger</span>
                        <h3>Все движения по балансу</h3>
                      </div>
                      <div className="inline-filter">
                        <label className="inline-filter__field">
                          <span>Фильтр</span>
                          <select
                            value={ledgerHistoryFilter}
                            onChange={(event) =>
                              setLedgerHistoryFilter(event.target.value as LedgerEntryFilterOption)
                            }
                            disabled={ledgerHistoryLoading}
                          >
                            {LEDGER_ENTRY_FILTER_OPTIONS.map((entryType) => (
                              <option key={entryType} value={entryType}>
                                {humanizeLedgerEntryFilter(entryType)}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                    </div>
                    <div className="activity-list">
                      {ledgerHistoryLoading ? (
                        <div className="activity-empty">Загружаем ledger history...</div>
                      ) : ledgerHistoryItems.length === 0 ? (
                        <div className="activity-empty">Записей пока нет.</div>
                      ) : (
                        ledgerHistoryItems.map((entry) => (
                          <article key={entry.id} className="activity-item activity-item--dense">
                            <div>
                              <strong>{humanizeLedgerType(entry.entry_type)}</strong>
                              <span>
                                {entry.comment ||
                                  describeLedgerEntryContext(entry) ||
                                  `${entry.reference_type || "entry"} ${entry.reference_id || ""}`.trim()}
                              </span>
                            </div>
                            <div className="activity-item__meta">
                              <strong>{formatMoney(entry.amount, entry.currency)}</strong>
                              <span>{formatDate(entry.created_at)}</span>
                              <span>После: {formatMoney(entry.balance_after, entry.currency)}</span>
                            </div>
                          </article>
                        ))
                      )}
                    </div>
                    <div className="section-footer">
                      <span className="form-hint">
                        Показано {ledgerHistoryItems.length} из {ledgerHistoryTotal} записей.
                      </span>
                      {hasMoreLedgerHistory ? (
                        <button
                          className="ghost-button"
                          type="button"
                          onClick={() => void handleLoadMoreLedgerHistory()}
                          disabled={ledgerHistoryLoading || ledgerHistoryLoadingMore}
                        >
                          {ledgerHistoryLoadingMore ? "Загружаем..." : "Загрузить еще"}
                        </button>
                      ) : null}
                    </div>
                  </article>
                </section>

                <section className="activity-grid">
                  <article className="detail-section">
                    <span className="eyebrow">Последние платежи</span>
                    <div className="activity-list">
                      {selectedAccount.recent_payments.length === 0 ? (
                        <div className="activity-empty">Платежей пока нет.</div>
                      ) : (
                        selectedAccount.recent_payments.map((payment) => (
                          <article key={payment.id} className="activity-item activity-item--dense">
                            <div>
                              <strong>{humanizePaymentFlow(payment.flow_type)}</strong>
                              <span>{payment.description || payment.plan_code || payment.provider}</span>
                            </div>
                            <div className="activity-item__meta">
                              <strong>{formatMoney(payment.amount, payment.currency)}</strong>
                              <span>{humanizePaymentStatus(payment.status)}</span>
                            </div>
                          </article>
                        ))
                      )}
                    </div>
                  </article>

                  <article className="detail-section">
                    <span className="eyebrow">Последние выводы</span>
                    <div className="activity-list">
                      {selectedAccount.recent_withdrawals.length === 0 ? (
                        <div className="activity-empty">Выводов пока нет.</div>
                      ) : (
                        selectedAccount.recent_withdrawals.map((withdrawal) => (
                          <article key={withdrawal.id} className="activity-item activity-item--dense">
                            <div>
                              <strong>{formatMoney(withdrawal.amount)}</strong>
                              <span>{withdrawal.destination_type}: {withdrawal.destination_value}</span>
                            </div>
                            <div className="activity-item__meta">
                              <strong>{humanizeWithdrawalStatus(withdrawal.status)}</strong>
                              <span>{formatDate(withdrawal.created_at)}</span>
                            </div>
                          </article>
                        ))
                      )}
                    </div>
                  </article>
                </section>

                <section className="detail-section detail-section--action detail-section--danger">
                  <span className="eyebrow">{t("admin.accounts.dangerZone.eyebrow")}</span>
                  <div className="detail-section__intro">
                    <h3>{t("admin.accounts.dangerZone.title")}</h3>
                    <p>{t("admin.accounts.dangerZone.description")}</p>
                  </div>
                  <form className="adjustment-form" onSubmit={handleAccountStatusChange}>
                    <div className="form-field">
                      <span>{t("admin.accounts.dangerZone.statusLabel")}</span>
                      <div className="status-action-summary status-action-summary--danger">
                        <strong>{humanizeAccountStatus(selectedAccount.status)}</strong>
                        <small>
                          {selectedAccount.status === "blocked"
                            ? t("admin.accounts.dangerZone.blockedState")
                            : t("admin.accounts.dangerZone.activeState")}
                        </small>
                      </div>
                    </div>
                    <label className="form-field form-field--wide">
                      <span>{t("admin.accounts.dangerZone.commentLabel")}</span>
                      <textarea
                        value={statusChangeComment}
                        onChange={(event) => setStatusChangeComment(event.target.value)}
                        placeholder={t("admin.accounts.dangerZone.commentPlaceholder")}
                        rows={3}
                        required
                      />
                    </label>
                    <div className="adjustment-form__footer">
                      <span className="form-hint">
                        {t("admin.accounts.dangerZone.nextActionLabel")}:{" "}
                        {selectedAccount.status === "blocked"
                          ? t("admin.accounts.dangerZone.nextActionUnblock")
                          : t("admin.accounts.dangerZone.nextActionBlock")}
                      </span>
                      <button
                        className={
                          selectedAccount.status === "blocked"
                            ? "action-button"
                            : "action-button action-button--danger"
                        }
                        type="submit"
                        disabled={statusSubmitting}
                      >
                        {statusSubmitting
                          ? t("admin.accounts.dangerZone.submitting")
                          : selectedAccount.status === "blocked"
                            ? t("admin.accounts.dangerZone.submitUnblock")
                            : t("admin.accounts.dangerZone.submitBlock")}
                      </button>
                    </div>
                  </form>
                </section>
              </>
                ) : null}
              </div>
            </div>
          ) : null}
        </section>
      ) : activeView === "events" ? (
        <section className="search-shell">
          <aside className="search-column">
            <form className="search-panel" onSubmit={handleApplyGlobalEventSearch}>
              <span className="eyebrow">Support search</span>
              <h2>Глобальный поиск по account events</h2>
              <p className="queue-panel__copy">
                Ищи по `request_id`, `telegram_id`, `account_id`, `actor_account_id`, `actor_admin_id`
                и бизнес-событиям без привязки к одной карточке пользователя.
              </p>
              <div className="event-filter-grid">
                <label className="form-field">
                  <span>Event type</span>
                  <select
                    value={globalEventSearchDraft.eventType}
                    onChange={(event) =>
                      setGlobalEventSearchDraft((current) => ({
                        ...current,
                        eventType: event.target.value as AccountEventTypeFilterOption,
                      }))
                    }
                    disabled={globalEventLoading}
                  >
                    {ACCOUNT_EVENT_TYPE_FILTER_OPTIONS.map((eventType) => (
                      <option key={eventType} value={eventType}>
                        {eventType === "all" ? "Все события" : humanizeAccountEventType(eventType)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-field">
                  <span>Outcome</span>
                  <select
                    value={globalEventSearchDraft.outcome}
                    onChange={(event) =>
                      setGlobalEventSearchDraft((current) => ({
                        ...current,
                        outcome: event.target.value as AccountEventOutcomeFilterOption,
                      }))
                    }
                    disabled={globalEventLoading}
                  >
                    {ACCOUNT_EVENT_OUTCOME_FILTER_OPTIONS.map((outcome) => (
                      <option key={outcome} value={outcome}>
                        {outcome === "all" ? "Все outcomes" : humanizeAccountEventOutcome(outcome)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-field">
                  <span>Source</span>
                  <select
                    value={globalEventSearchDraft.source}
                    onChange={(event) =>
                      setGlobalEventSearchDraft((current) => ({
                        ...current,
                        source: event.target.value as AccountEventSourceFilterOption,
                      }))
                    }
                    disabled={globalEventLoading}
                  >
                    {ACCOUNT_EVENT_SOURCE_FILTER_OPTIONS.map((source) => (
                      <option key={source} value={source}>
                        {source === "all" ? "Все источники" : humanizeAccountEventSource(source)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-field">
                  <span>Telegram ID</span>
                  <input
                    value={globalEventSearchDraft.telegramId}
                    onChange={(event) =>
                      setGlobalEventSearchDraft((current) => ({
                        ...current,
                        telegramId: event.target.value,
                      }))
                    }
                    placeholder="Например: 777000111"
                  />
                </label>
                <label className="form-field">
                  <span>Request ID</span>
                  <input
                    value={globalEventSearchDraft.requestId}
                    onChange={(event) =>
                      setGlobalEventSearchDraft((current) => ({
                        ...current,
                        requestId: event.target.value,
                      }))
                    }
                    placeholder="Например: req_123456"
                  />
                </label>
                <label className="form-field">
                  <span>Account ID</span>
                  <input
                    value={globalEventSearchDraft.accountId}
                    onChange={(event) =>
                      setGlobalEventSearchDraft((current) => ({
                        ...current,
                        accountId: event.target.value,
                      }))
                    }
                    placeholder="UUID target account"
                  />
                </label>
                <label className="form-field">
                  <span>Actor account ID</span>
                  <input
                    value={globalEventSearchDraft.actorAccountId}
                    onChange={(event) =>
                      setGlobalEventSearchDraft((current) => ({
                        ...current,
                        actorAccountId: event.target.value,
                      }))
                    }
                    placeholder="UUID actor account"
                  />
                </label>
                <label className="form-field">
                  <span>Actor admin ID</span>
                  <input
                    value={globalEventSearchDraft.actorAdminId}
                    onChange={(event) =>
                      setGlobalEventSearchDraft((current) => ({
                        ...current,
                        actorAdminId: event.target.value,
                      }))
                    }
                    placeholder="UUID admin actor"
                  />
                </label>
              </div>
              <div className="event-filter-actions">
                <button className="action-button" type="submit" disabled={globalEventLoading}>
                  {globalEventLoading ? "Ищем..." : "Применить фильтры"}
                </button>
                <button
                  className="ghost-button"
                  type="button"
                  onClick={handleResetGlobalEventSearch}
                  disabled={!globalEventFiltersActive && !globalEventLoading}
                >
                  Сбросить
                </button>
              </div>
            </form>

            <div className="results-list">
              {globalEventLoading && globalEventItems.length === 0 ? (
                <div className="empty-state">Загружаем события...</div>
              ) : globalEventItems.length === 0 ? (
                <div className="empty-state">
                  {globalEventFiltersActive ? "По текущим фильтрам событий нет." : "Событий пока нет."}
                </div>
              ) : (
                globalEventItems.map((eventItem) => (
                  <button
                    key={eventItem.id}
                    type="button"
                    className={
                      selectedGlobalEventId === eventItem.id
                        ? "result-card result-card--active"
                        : "result-card"
                    }
                    onClick={() => setSelectedGlobalEventId(eventItem.id)}
                  >
                    <div className="result-card__top">
                      <strong>{humanizeAccountEventType(eventItem.event_type)}</strong>
                      <span className={`status-pill ${getAccountEventOutcomePillClass(eventItem.outcome)}`}>
                        {humanizeAccountEventOutcome(eventItem.outcome)}
                      </span>
                    </div>
                    <span>{describeGlobalEventTargetAccount(eventItem)}</span>
                    <span>{summarizeAccountEventPayload(eventItem.payload) || describeGlobalEventActor(eventItem)}</span>
                    <span>
                      {humanizeAccountEventSource(eventItem.source)} · {formatDate(eventItem.created_at)}
                    </span>
                  </button>
                ))
              )}
            </div>

            <section className="detail-section">
              <div className="section-footer">
                <span className="form-hint">
                  Показано {globalEventItems.length} из {globalEventTotal} событий.
                </span>
                {hasMoreGlobalEvents ? (
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => void handleLoadMoreGlobalEvents()}
                    disabled={globalEventLoading || globalEventLoadingMore}
                  >
                    {globalEventLoadingMore ? "Загружаем..." : "Загрузить еще"}
                  </button>
                ) : null}
              </div>
            </section>
          </aside>

          <div className="detail-column">
            {globalEventLoading && globalEventItems.length === 0 ? (
              <div className="detail-skeleton">Загружаем детализацию события...</div>
            ) : null}
            {!globalEventLoading && !selectedGlobalEvent ? (
              <div className="detail-skeleton">Выбери событие из списка слева.</div>
            ) : null}
            {!globalEventLoading && selectedGlobalEvent ? (
              <>
                <section className="detail-header">
                  <div>
                    <span className="eyebrow">Account event</span>
                    <h2>{humanizeAccountEventType(selectedGlobalEvent.event_type)}</h2>
                    <p>
                      {describeGlobalEventTargetAccount(selectedGlobalEvent)} ·{" "}
                      {humanizeAccountEventSource(selectedGlobalEvent.source)}
                    </p>
                  </div>
                  <span className={`status-pill ${getAccountEventOutcomePillClass(selectedGlobalEvent.outcome)}`}>
                    {humanizeAccountEventOutcome(selectedGlobalEvent.outcome)}
                  </span>
                </section>

                <section className="detail-facts-grid">
                  <DetailFact label="Request ID" value={selectedGlobalEvent.request_id || "-"} />
                  <DetailFact label="Создано" value={formatDate(selectedGlobalEvent.created_at)} />
                  <DetailFact label="Source" value={humanizeAccountEventSource(selectedGlobalEvent.source)} />
                  <DetailFact label="Event ID" value={`#${selectedGlobalEvent.id}`} />
                </section>

                <section className="detail-sections-grid">
                  <article className="detail-section">
                    <span className="eyebrow">Target account</span>
                    <div className="detail-kv">
                      <div>
                        <span>Аккаунт</span>
                        <strong>{describeGlobalEventTargetAccount(selectedGlobalEvent)}</strong>
                      </div>
                      <div>
                        <span>Email</span>
                        <strong>{selectedGlobalEvent.account?.email || "-"}</strong>
                      </div>
                      <div>
                        <span>Username</span>
                        <strong>{selectedGlobalEvent.account?.username || "-"}</strong>
                      </div>
                      <div>
                        <span>Telegram</span>
                        <strong>
                          {selectedGlobalEvent.account?.telegram_id
                            ? String(selectedGlobalEvent.account.telegram_id)
                            : "-"}
                        </strong>
                      </div>
                      <div>
                        <span>Status</span>
                        <strong>
                          {selectedGlobalEvent.account?.status
                            ? humanizeAccountStatus(selectedGlobalEvent.account.status)
                            : "-"}
                        </strong>
                      </div>
                      <div>
                        <span>UUID</span>
                        <strong>{selectedGlobalEvent.account_id || "-"}</strong>
                      </div>
                    </div>
                    {selectedGlobalEvent.account_id ? (
                      <button
                        className="ghost-button detail-inline-button"
                        type="button"
                        onClick={() => void handleOpenGlobalEventAccount(selectedGlobalEvent)}
                      >
                        Открыть аккаунт и timeline
                      </button>
                    ) : null}
                  </article>

                  <article className="detail-section">
                    <span className="eyebrow">Actor</span>
                    <div className="detail-kv">
                      <div>
                        <span>Инициатор</span>
                        <strong>{describeGlobalEventActor(selectedGlobalEvent)}</strong>
                      </div>
                      <div>
                        <span>Actor account</span>
                        <strong>
                          {selectedGlobalEvent.actor_account
                            ? formatAccountIdentity(selectedGlobalEvent.actor_account)
                            : "-"}
                        </strong>
                      </div>
                      <div>
                        <span>Actor admin</span>
                        <strong>{formatAdminIdentity(selectedGlobalEvent.actor_admin)}</strong>
                      </div>
                      <div>
                        <span>Actor account UUID</span>
                        <strong>{selectedGlobalEvent.actor_account_id || "-"}</strong>
                      </div>
                      <div>
                        <span>Actor admin UUID</span>
                        <strong>{selectedGlobalEvent.actor_admin_id || "-"}</strong>
                      </div>
                      <div>
                        <span>Telegram actor</span>
                        <strong>
                          {selectedGlobalEvent.actor_account?.telegram_id
                            ? String(selectedGlobalEvent.actor_account.telegram_id)
                            : "-"}
                        </strong>
                      </div>
                    </div>
                  </article>
                </section>

                <section className="detail-section">
                  <span className="eyebrow">Payload</span>
                  {selectedGlobalEvent.payload ? (
                    <>
                      <div className="note-card">
                        <strong>Summary</strong>
                        <p>{summarizeAccountEventPayload(selectedGlobalEvent.payload) || "Без краткого summary"}</p>
                      </div>
                      <details className="payload-preview" open>
                        <summary>Payload JSON</summary>
                        <pre>{JSON.stringify(selectedGlobalEvent.payload, null, 2)}</pre>
                      </details>
                    </>
                  ) : (
                    <div className="activity-empty">Payload не записан.</div>
                  )}
                </section>
              </>
            ) : null}
          </div>
        </section>
      ) : activeView === "plans" ? (
        <section className="search-shell search-shell--broadcasts">
          <div className="detail-column detail-column--broadcasts">
            <section className="search-panel search-panel--broadcasts">
              <div className="panel-toolbar">
                <div>
                  <span className="eyebrow">{t("admin.plans.overview.eyebrow")}</span>
                  <h2>{t("admin.plans.overview.title")}</h2>
                  <p className="queue-panel__copy">{t("admin.plans.overview.description")}</p>
                </div>
                <div className="panel-toolbar__actions">
                  <button className="ghost-button" type="button" onClick={handleNewSubscriptionPlan}>
                    {t("admin.plans.overview.newPlan")}
                  </button>
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => {
                      if (token) {
                        void loadSubscriptionPlans(token);
                      }
                    }}
                    disabled={!token || plansLoading}
                  >
                    {plansLoading ? t("admin.actions.refreshing") : t("admin.actions.refresh")}
                  </button>
                </div>
              </div>

              <div className="queue-summary queue-summary--broadcasts">
                <article className="queue-summary__item">
                  <span>{t("admin.plans.overview.summary.total")}</span>
                  <strong>{plansOverview.total}</strong>
                </article>
                <article className="queue-summary__item">
                  <span>{t("admin.plans.overview.summary.popular")}</span>
                  <strong>{plansOverview.popular}</strong>
                </article>
                <article className="queue-summary__item">
                  <span>{t("admin.plans.overview.summary.starsEnabled")}</span>
                  <strong>{plansOverview.starsEnabled}</strong>
                </article>
                <article className="queue-summary__item">
                  <span>{t("admin.plans.overview.summary.longestDuration")}</span>
                  <strong>
                    {plansOverview.longestDuration > 0
                      ? formatPlanDuration(plansOverview.longestDuration)
                      : t("admin.plans.overview.summary.longestDurationEmpty")}
                  </strong>
                </article>
              </div>
            </section>

            <section className="detail-section detail-section--editor">
              <div className="detail-section__header detail-section__header--stacked">
                <div>
                  <span className="eyebrow">{t("admin.plans.table.eyebrow")}</span>
                  <h3>{t("admin.plans.table.title")}</h3>
                </div>
                <span className="form-hint">
                  {selectedCatalogPlan
                    ? t("admin.plans.table.selectedHint", { name: selectedCatalogPlan.name })
                    : t("admin.plans.table.description")}
                </span>
              </div>
              <div className="accounts-table__wrap plans-table__wrap">
                <table className="accounts-table plans-table">
                  <thead>
                    <tr>
                      <th>{t("admin.plans.table.columns.code")}</th>
                      <th>{t("admin.plans.table.columns.plan")}</th>
                      <th>{t("admin.plans.table.columns.duration")}</th>
                      <th>{t("admin.plans.table.columns.priceRub")}</th>
                      <th>{t("admin.plans.table.columns.priceStars")}</th>
                      <th>{t("admin.plans.table.columns.devices")}</th>
                      <th>{t("admin.plans.table.columns.features")}</th>
                      <th>{t("admin.plans.table.columns.status")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plansLoading ? (
                      <tr>
                        <td className="accounts-table__empty" colSpan={8}>
                          {t("admin.plans.table.loading")}
                        </td>
                      </tr>
                    ) : subscriptionPlans.length === 0 ? (
                      <tr>
                        <td className="accounts-table__empty" colSpan={8}>
                          {t("admin.plans.table.empty")}
                        </td>
                      </tr>
                    ) : (
                      subscriptionPlans.map((plan) => (
                        <tr
                          key={plan.code}
                          className={
                            selectedCatalogPlanCode === plan.code
                              ? "accounts-table__row accounts-table__row--active"
                              : "accounts-table__row"
                          }
                          onClick={() => handleSelectSubscriptionPlan(plan)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              handleSelectSubscriptionPlan(plan);
                            }
                          }}
                          role="button"
                          tabIndex={0}
                        >
                          <td>
                            <div className="plans-table__title-cell">
                              <strong>{plan.code}</strong>
                            </div>
                          </td>
                          <td>
                            <div className="plans-table__title-cell">
                              <strong>{plan.name}</strong>
                              <small>{t("admin.plans.table.featuresValue", { count: plan.features.length })}</small>
                            </div>
                          </td>
                          <td>{formatPlanDuration(plan.duration_days)}</td>
                          <td>{formatMoney(plan.price_rub)}</td>
                          <td>{formatPlanStarsPrice(plan.price_stars)}</td>
                          <td>{formatPlanDeviceLimit(plan.device_limit)}</td>
                          <td>
                            <div className="plans-table__title-cell">
                              <strong>{t("admin.plans.table.featuresValue", { count: plan.features.length })}</strong>
                              <small>{summarizePlanFeatures(plan.features)}</small>
                            </div>
                          </td>
                          <td>
                            <span
                              className={
                                plan.popular
                                  ? "status-pill status-pill--active"
                                  : "status-pill status-pill--pending"
                              }
                            >
                              {plan.popular ? t("admin.plans.table.popular") : t("admin.plans.table.regular")}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="detail-section detail-section--action detail-section--editor">
              <div className="detail-section__header">
                <div>
                  <span className="eyebrow">
                    {planEditorMode === "create"
                      ? t("admin.plans.form.createEyebrow")
                      : t("admin.plans.form.editEyebrow")}
                  </span>
                  <h3>
                    {planEditorMode === "create"
                      ? t("admin.plans.form.createTitle")
                      : t("admin.plans.form.editTitle")}
                  </h3>
                </div>
                <span className="form-hint">
                  {planEditorMode === "create"
                    ? t("admin.plans.form.createDescription")
                    : t("admin.plans.form.editDescription")}
                </span>
              </div>

              <form className="broadcast-editor-form" onSubmit={handleSaveSubscriptionPlan}>
                <div className="broadcast-form-section broadcast-form-section--compact">
                  <div className="broadcast-form-section__header">
                    <div>
                      <span className="eyebrow">{t("admin.plans.form.basicsEyebrow")}</span>
                      <h4>{t("admin.plans.form.basicsTitle")}</h4>
                    </div>
                    <span className="form-hint">{t("admin.plans.form.basicsHint")}</span>
                  </div>
                  <div className="broadcast-form-grid">
                    <label className="form-field">
                      <span>{t("admin.plans.form.fields.code")}</span>
                      <input
                        value={planEditorCode}
                        onChange={(event) => setPlanEditorCode(event.target.value)}
                        placeholder={t("admin.plans.form.fields.codePlaceholder")}
                        disabled={planSubmitting || planEditorMode === "edit"}
                        required
                      />
                    </label>
                    <label className="form-field">
                      <span>{t("admin.plans.form.fields.name")}</span>
                      <input
                        value={planEditorName}
                        onChange={(event) => setPlanEditorName(event.target.value)}
                        placeholder={t("admin.plans.form.fields.namePlaceholder")}
                        disabled={planSubmitting}
                        required
                      />
                    </label>
                    <label className="form-field">
                      <span>{t("admin.plans.form.fields.duration")}</span>
                      <input
                        type="number"
                        step="1"
                        min="1"
                        value={planEditorDurationDays}
                        onChange={(event) => setPlanEditorDurationDays(event.target.value)}
                        placeholder={t("admin.plans.form.fields.durationPlaceholder")}
                        disabled={planSubmitting}
                        required
                      />
                    </label>
                    <label className="checkbox-card checkbox-card--inline">
                      <input
                        type="checkbox"
                        checked={planEditorPopular}
                        onChange={(event) => setPlanEditorPopular(event.target.checked)}
                        disabled={planSubmitting}
                      />
                      <span>{t("admin.plans.form.fields.popular")}</span>
                    </label>
                  </div>
                </div>

                <div className="broadcast-form-section broadcast-form-section--compact">
                  <div className="broadcast-form-section__header">
                    <div>
                      <span className="eyebrow">{t("admin.plans.form.pricingEyebrow")}</span>
                      <h4>{t("admin.plans.form.pricingTitle")}</h4>
                    </div>
                    <span className="form-hint">{t("admin.plans.form.pricingHint")}</span>
                  </div>
                  <div className="broadcast-form-grid">
                    <label className="form-field">
                      <span>{t("admin.plans.form.fields.priceRub")}</span>
                      <input
                        type="number"
                        step="1"
                        min="1"
                        value={planEditorPriceRub}
                        onChange={(event) => setPlanEditorPriceRub(event.target.value)}
                        placeholder={t("admin.plans.form.fields.priceRubPlaceholder")}
                        disabled={planSubmitting}
                        required
                      />
                    </label>
                    <label className="form-field">
                      <span>{t("admin.plans.form.fields.priceStars")}</span>
                      <input
                        type="number"
                        step="1"
                        min="1"
                        value={planEditorPriceStars}
                        onChange={(event) => setPlanEditorPriceStars(event.target.value)}
                        placeholder={t("admin.plans.form.fields.priceStarsPlaceholder")}
                        disabled={planSubmitting}
                      />
                    </label>
                    <label className="form-field">
                      <span>{t("admin.plans.form.fields.deviceLimit")}</span>
                      <input
                        type="number"
                        step="1"
                        min="1"
                        value={planEditorDeviceLimit}
                        onChange={(event) => setPlanEditorDeviceLimit(event.target.value)}
                        placeholder={t("admin.plans.form.fields.deviceLimitPlaceholder")}
                        disabled={planSubmitting}
                      />
                    </label>
                    <div className="status-action-summary">
                      <strong>
                        {t("admin.plans.form.preview.duration", {
                          days: Number.parseInt(planEditorDurationDays || "0", 10) || 0,
                        })}
                      </strong>
                      <small>
                        {t("admin.plans.form.preview.rub", {
                          amount: formatMoney(Number.parseInt(planEditorPriceRub || "0", 10) || 0),
                        })}
                      </small>
                      <small>
                        {planEditorPriceStars.trim()
                          ? t("admin.plans.form.preview.stars", {
                              amount: Number.parseInt(planEditorPriceStars, 10) || 0,
                            })
                          : t("admin.plans.form.preview.starsEmpty")}
                      </small>
                      <small>
                        {t("admin.plans.form.preview.devices", {
                          value: planEditorDeviceLimit.trim()
                            ? String(Number.parseInt(planEditorDeviceLimit, 10) || 0)
                            : t("admin.plans.table.deviceLimitEmpty"),
                        })}
                      </small>
                    </div>
                  </div>
                </div>

                <div className="broadcast-form-section broadcast-form-section--compact">
                  <div className="broadcast-form-section__header">
                    <div>
                      <span className="eyebrow">{t("admin.plans.form.featuresEyebrow")}</span>
                      <h4>{t("admin.plans.form.featuresTitle")}</h4>
                    </div>
                    <span className="form-hint">{t("admin.plans.form.featuresHint")}</span>
                  </div>
                  <label className="form-field form-field--wide">
                    <span>{t("admin.plans.form.fields.features")}</span>
                    <textarea
                      rows={8}
                      value={planEditorFeaturesInput}
                      onChange={(event) => setPlanEditorFeaturesInput(event.target.value)}
                      placeholder={t("admin.plans.form.fields.featuresPlaceholder")}
                      disabled={planSubmitting}
                      required
                    />
                  </label>
                </div>

                <div className="adjustment-form__footer">
                  <span className="form-hint">{t("admin.plans.form.saveHint")}</span>
                  <div className="action-cluster">
                    {planEditorMode === "edit" ? (
                      <button
                        className="ghost-button"
                        type="button"
                        onClick={() => void handleDeleteSubscriptionPlan()}
                        disabled={planSubmitting || planDeleting}
                      >
                        {planDeleting
                          ? t("admin.plans.form.buttons.deleting")
                          : t("admin.plans.form.buttons.delete")}
                      </button>
                    ) : null}
                    <button className="action-button" type="submit" disabled={planSubmitting}>
                      {planSubmitting
                        ? planEditorMode === "create"
                          ? t("admin.plans.form.buttons.creating")
                          : t("admin.plans.form.buttons.saving")
                        : planEditorMode === "create"
                          ? t("admin.plans.form.buttons.create")
                          : t("admin.plans.form.buttons.save")}
                    </button>
                  </div>
                </div>
              </form>
            </section>
          </div>
        </section>
      ) : activeView === "promos" ? (
        <section className="search-shell search-shell--broadcasts">
          <div className="detail-column detail-column--broadcasts">
            <section className="search-panel search-panel--broadcasts">
              <div className="panel-toolbar">
                <div>
                  <span className="eyebrow">{t("admin.promos.workspace.overview.eyebrow")}</span>
                  <h2>{t("admin.promos.workspace.overview.title")}</h2>
                  <p className="queue-panel__copy">{t("admin.promos.workspace.overview.description")}</p>
                </div>
                <div className="panel-toolbar__actions">
                  <button className="ghost-button" type="button" onClick={resetPromoCampaignForm}>
                    {promoCampaignEditingId === null
                      ? t("admin.promos.workspace.overview.newCampaign")
                      : t("admin.promos.workspace.overview.clearForm")}
                  </button>
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => {
                      if (token) {
                        void loadPromoCampaigns(token);
                      }
                    }}
                    disabled={!token || promoCampaignsLoading}
                  >
                    {promoCampaignsLoading ? t("admin.actions.refreshing") : t("admin.actions.refresh")}
                  </button>
                </div>
              </div>

              <div className="queue-summary queue-summary--broadcasts">
                <article className="queue-summary__item">
                  <span>{t("admin.promos.workspace.overview.cards.totalCampaigns")}</span>
                  <strong>{promoCampaignTotal}</strong>
                </article>
                <article className="queue-summary__item">
                  <span>{t("admin.promos.workspace.overview.cards.activeCampaigns")}</span>
                  <strong>{promoOverview.active}</strong>
                </article>
                <article className="queue-summary__item">
                  <span>{t("admin.promos.workspace.overview.cards.totalCodes")}</span>
                  <strong>{promoOverview.totalCodes}</strong>
                </article>
                <article className="queue-summary__item">
                  <span>{t("admin.promos.workspace.overview.cards.activations")}</span>
                  <strong>{promoOverview.totalRedemptions}</strong>
                </article>
              </div>

              <div className="promo-overview-toolbar">
                <label className="inline-filter__field">
                  <span>{t("admin.promos.workspace.overview.filterLabel")}</span>
                  <select
                    value={promoCampaignStatusFilter}
                    onChange={(event) => setPromoCampaignStatusFilter(event.target.value as PromoCampaignFilter)}
                    disabled={promoCampaignsLoading}
                  >
                    <option value="all">{t("admin.promos.workspace.overview.filterAll")}</option>
                    {PROMO_CAMPAIGN_STATUS_OPTIONS.map((status) => (
                      <option key={status} value={status}>
                        {humanizePromoCampaignStatus(status)}
                      </option>
                    ))}
                  </select>
                </label>
                <span className="form-hint">
                  {t("admin.promos.workspace.overview.summary", {
                    shown: promoCampaignItems.length,
                    total: promoCampaignTotal,
                    draft: promoOverview.draft,
                  })}
                </span>
              </div>
            </section>

            <section className="detail-section detail-section--editor">
              <div className="detail-section__header detail-section__header--stacked">
                <div>
                  <span className="eyebrow">{t("admin.promos.workspace.campaignTable.eyebrow")}</span>
                  <h3>{t("admin.promos.workspace.campaignTable.title")}</h3>
                </div>
                <span className="form-hint">{t("admin.promos.workspace.campaignTable.description")}</span>
              </div>
              <div className="accounts-table__wrap promo-table__wrap">
                <table className="accounts-table promo-table promo-table--campaigns">
                  <thead>
                    <tr>
                      <th>{t("admin.promos.workspace.campaignTable.columns.campaign")}</th>
                      <th>{t("admin.promos.workspace.campaignTable.columns.status")}</th>
                      <th>{t("admin.promos.workspace.campaignTable.columns.effect")}</th>
                      <th>{t("admin.promos.workspace.campaignTable.columns.plans")}</th>
                      <th>{t("admin.promos.workspace.campaignTable.columns.window")}</th>
                      <th>{t("admin.promos.workspace.campaignTable.columns.codes")}</th>
                      <th>{t("admin.promos.workspace.campaignTable.columns.updatedAt")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {promoCampaignsLoading ? (
                      <tr>
                        <td className="accounts-table__empty" colSpan={7}>
                          {t("admin.promos.workspace.campaignTable.loading")}
                        </td>
                      </tr>
                    ) : promoCampaignItems.length === 0 ? (
                      <tr>
                        <td className="accounts-table__empty" colSpan={7}>
                          {t("admin.promos.workspace.campaignTable.empty")}
                        </td>
                      </tr>
                    ) : (
                      promoCampaignItems.map((campaign) => (
                        <tr
                          key={campaign.id}
                          className={
                            selectedPromoCampaignId === campaign.id
                              ? "accounts-table__row accounts-table__row--active"
                              : "accounts-table__row"
                          }
                          onClick={() => handleSelectPromoCampaign(campaign.id)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              handleSelectPromoCampaign(campaign.id);
                            }
                          }}
                          role="button"
                          tabIndex={0}
                        >
                          <td>
                            <div className="promo-table__title-cell">
                              <strong>{campaign.name}</strong>
                              <small>{campaign.description || t("admin.promos.workspace.common.noDescription")}</small>
                            </div>
                          </td>
                          <td>
                            <span className={promoCampaignStatusPillClass(campaign.status)}>
                              {humanizePromoCampaignStatus(campaign.status)}
                            </span>
                          </td>
                          <td>
                            <div className="promo-table__title-cell">
                              <strong>{describePromoEffect(campaign.effect_type, campaign.effect_value, campaign.currency)}</strong>
                              <small>{humanizePromoEffectType(campaign.effect_type)}</small>
                            </div>
                          </td>
                          <td>{describePromoPlanScope(campaign.plan_codes)}</td>
                          <td>{describePromoCampaignWindow(campaign)}</td>
                          <td>
                            <div className="promo-table__title-cell">
                              <strong>{campaign.codes_count}</strong>
                              <small>
                                {t("admin.promos.workspace.campaignTable.activationsValue", {
                                  count: campaign.redemptions_count,
                                })}
                              </small>
                            </div>
                          </td>
                          <td>{formatDateMoscow(campaign.updated_at)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="detail-section detail-section--action detail-section--editor">
              <div className="detail-section__header">
                <div>
                  <span className="eyebrow">
                    {promoCampaignEditorMode === "create"
                      ? t("admin.promos.workspace.campaignForm.createEyebrow")
                      : t("admin.promos.workspace.campaignForm.editEyebrow")}
                  </span>
                  <h3>
                    {promoCampaignEditorMode === "create"
                      ? t("admin.promos.workspace.campaignForm.createTitle")
                      : t("admin.promos.workspace.campaignForm.editTitle")}
                  </h3>
                </div>
                <span className="form-hint">
                  {promoCampaignEditorMode === "create"
                    ? t("admin.promos.workspace.campaignForm.createDescription")
                    : t("admin.promos.workspace.campaignForm.editDescription")}
                </span>
              </div>

              <form className="broadcast-editor-form" onSubmit={handleCreatePromoCampaign}>
                <div className="broadcast-form-section broadcast-form-section--compact">
                  <div className="broadcast-form-section__header">
                    <div>
                      <span className="eyebrow">{t("admin.promos.workspace.campaignForm.basicsEyebrow")}</span>
                      <h4>{t("admin.promos.workspace.campaignForm.basicsTitle")}</h4>
                    </div>
                    <span className="form-hint">{t("admin.promos.workspace.campaignForm.basicsHint")}</span>
                  </div>
                  <div className="broadcast-form-grid">
                    <label className="form-field">
                      <span>{t("admin.promos.workspace.campaignForm.fields.name")}</span>
                      <input
                        value={promoCampaignName}
                        onChange={(event) => setPromoCampaignName(event.target.value)}
                        placeholder={t("admin.promos.workspace.campaignForm.fields.namePlaceholder")}
                        required
                        disabled={promoCampaignSubmitting}
                      />
                    </label>
                    <label className="form-field">
                      <span>{t("admin.promos.workspace.campaignForm.fields.status")}</span>
                      <select
                        value={promoCampaignStatus}
                        onChange={(event) => setPromoCampaignStatus(event.target.value as PromoCampaignStatus)}
                        disabled={promoCampaignSubmitting}
                      >
                        {PROMO_CAMPAIGN_STATUS_OPTIONS.map((status) => (
                          <option key={status} value={status}>
                            {humanizePromoCampaignStatus(status)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="form-field">
                      <span>{t("admin.promos.workspace.campaignForm.fields.effectType")}</span>
                      <select
                        value={promoEffectType}
                        onChange={(event) => setPromoEffectType(event.target.value as PromoEffectType)}
                        disabled={promoCampaignSubmitting}
                      >
                        {PROMO_EFFECT_TYPE_OPTIONS.map((effectType) => (
                          <option key={effectType} value={effectType}>
                            {humanizePromoEffectType(effectType)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="form-field">
                      <span>{t("admin.promos.workspace.campaignForm.fields.effectValue")}</span>
                      <input
                        type="number"
                        step="1"
                        value={promoEffectValue}
                        onChange={(event) => setPromoEffectValue(event.target.value)}
                        placeholder={
                          promoEffectType === "percent_discount"
                            ? t("admin.promos.workspace.campaignForm.fields.effectValuePercentPlaceholder")
                            : promoEffectType === "extra_days" || promoEffectType === "free_days"
                              ? t("admin.promos.workspace.campaignForm.fields.effectValueDaysPlaceholder")
                              : t("admin.promos.workspace.campaignForm.fields.effectValueAmountPlaceholder")
                        }
                        required
                        disabled={promoCampaignSubmitting}
                      />
                    </label>
                    <label className="form-field">
                      <span>{t("admin.promos.workspace.campaignForm.fields.currency")}</span>
                      <input
                        value={promoCurrency}
                        onChange={(event) => setPromoCurrency(event.target.value.toUpperCase())}
                        placeholder={t("admin.promos.workspace.campaignForm.fields.currencyPlaceholder")}
                        maxLength={8}
                        required
                        disabled={promoCampaignSubmitting}
                      />
                    </label>
                    <label className="form-field">
                      <span>{t("admin.promos.workspace.campaignForm.fields.startsAt")}</span>
                      <input
                        type="datetime-local"
                        value={promoStartsAtInput}
                        onChange={(event) => setPromoStartsAtInput(event.target.value)}
                        disabled={promoCampaignSubmitting}
                      />
                    </label>
                    <label className="form-field">
                      <span>{t("admin.promos.workspace.campaignForm.fields.endsAt")}</span>
                      <input
                        type="datetime-local"
                        value={promoEndsAtInput}
                        onChange={(event) => setPromoEndsAtInput(event.target.value)}
                        disabled={promoCampaignSubmitting}
                      />
                    </label>
                    <label className="form-field">
                      <span>{t("admin.promos.workspace.campaignForm.fields.totalLimit")}</span>
                      <input
                        type="number"
                        step="1"
                        min="1"
                        value={promoTotalRedemptionsLimit}
                        onChange={(event) => setPromoTotalRedemptionsLimit(event.target.value)}
                        placeholder={t("admin.promos.workspace.campaignForm.fields.limitPlaceholder")}
                        disabled={promoCampaignSubmitting}
                      />
                    </label>
                    <label className="form-field">
                      <span>{t("admin.promos.workspace.campaignForm.fields.perAccountLimit")}</span>
                      <input
                        type="number"
                        step="1"
                        min="1"
                        value={promoPerAccountRedemptionsLimit}
                        onChange={(event) => setPromoPerAccountRedemptionsLimit(event.target.value)}
                        placeholder={t("admin.promos.workspace.campaignForm.fields.limitPlaceholder")}
                        disabled={promoCampaignSubmitting}
                      />
                    </label>
                    <label className="form-field form-field--wide">
                      <span>{t("admin.promos.workspace.campaignForm.fields.description")}</span>
                      <textarea
                        value={promoCampaignDescription}
                        onChange={(event) => setPromoCampaignDescription(event.target.value)}
                        placeholder={t("admin.promos.workspace.campaignForm.fields.descriptionPlaceholder")}
                        rows={4}
                        disabled={promoCampaignSubmitting}
                      />
                    </label>
                  </div>
                </div>

                <div className="broadcast-form-section broadcast-form-section--compact">
                  <div className="broadcast-form-section__header">
                    <div>
                      <span className="eyebrow">{t("admin.promos.workspace.campaignForm.rulesEyebrow")}</span>
                      <h4>{t("admin.promos.workspace.campaignForm.rulesTitle")}</h4>
                    </div>
                    <span className="form-hint">{t("admin.promos.workspace.campaignForm.rulesHint")}</span>
                  </div>
                  <div className="broadcast-form-grid">
                    <div className="broadcast-channel-grid">
                      <label className="checkbox-card">
                        <input
                          type="checkbox"
                          checked={promoFirstPurchaseOnly}
                          onChange={(event) => setPromoFirstPurchaseOnly(event.target.checked)}
                          disabled={promoCampaignSubmitting}
                        />
                        <span>{t("admin.promos.workspace.campaignForm.fields.firstPurchaseOnly")}</span>
                      </label>
                      <label className="checkbox-card">
                        <input
                          type="checkbox"
                          checked={promoRequiresActiveSubscription}
                          onChange={(event) => setPromoRequiresActiveSubscription(event.target.checked)}
                          disabled={promoCampaignSubmitting}
                        />
                        <span>{t("admin.promos.workspace.campaignForm.fields.requiresActiveSubscription")}</span>
                      </label>
                      <label className="checkbox-card">
                        <input
                          type="checkbox"
                          checked={promoRequiresNoActiveSubscription}
                          onChange={(event) => setPromoRequiresNoActiveSubscription(event.target.checked)}
                          disabled={promoCampaignSubmitting}
                        />
                        <span>{t("admin.promos.workspace.campaignForm.fields.requiresNoActiveSubscription")}</span>
                      </label>
                    </div>
                    <div className="form-field form-field--wide">
                      <span>{t("admin.promos.workspace.campaignForm.fields.planCodes")}</span>
                      {subscriptionPlans.length === 0 ? (
                        <div className="status-action-summary">
                          <strong>
                            {plansLoading
                              ? t("admin.promos.workspace.campaignForm.fields.plansLoading")
                              : t("admin.promos.workspace.campaignForm.fields.plansEmpty")}
                          </strong>
                          <small>{t("admin.promos.workspace.campaignForm.fields.plansHint")}</small>
                        </div>
                      ) : (
                        <div className="broadcast-channel-grid">
                          {subscriptionPlans.map((plan) => (
                            <label key={plan.code} className="checkbox-card">
                              <input
                                type="checkbox"
                                checked={promoSelectedPlanCodes.includes(plan.code)}
                                onChange={() => handleTogglePromoPlanCode(plan.code)}
                                disabled={promoCampaignSubmitting}
                              />
                              <span>
                                {t("admin.promos.workspace.campaignForm.fields.planOption", {
                                  name: plan.name,
                                  days: plan.duration_days,
                                })}
                              </span>
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                <div className="adjustment-form__footer">
                  <span className="form-hint">
                    {t("admin.promos.workspace.campaignForm.effectPreview", {
                      effect: describePromoEffect(
                        promoEffectType,
                        Number.parseInt(promoEffectValue || "0", 10) || 0,
                        promoCurrency || "RUB",
                      ),
                    })}
                  </span>
                  <button className="action-button" type="submit" disabled={promoCampaignSubmitting}>
                    {promoCampaignSubmitting
                      ? promoCampaignEditorMode === "create"
                        ? t("admin.promos.workspace.campaignForm.buttons.creating")
                        : t("admin.promos.workspace.campaignForm.buttons.saving")
                      : promoCampaignEditorMode === "create"
                        ? t("admin.promos.workspace.campaignForm.buttons.create")
                        : t("admin.promos.workspace.campaignForm.buttons.save")}
                  </button>
                </div>
              </form>
            </section>

            {!selectedPromoCampaign ? (
              <section className="detail-section">
                <div className="detail-section__intro">
                  <span className="eyebrow">{t("admin.promos.workspace.selectedCampaign.emptyEyebrow")}</span>
                  <h3>{t("admin.promos.workspace.selectedCampaign.emptyTitle")}</h3>
                  <p>{t("admin.promos.workspace.selectedCampaign.emptyDescription")}</p>
                </div>
              </section>
            ) : (
              <>
                <section className="detail-header">
                  <div>
                    <span className="eyebrow">{t("admin.promos.workspace.selectedCampaign.eyebrow")}</span>
                    <h2>{selectedPromoCampaign.name}</h2>
                    <p>{selectedPromoCampaign.description || t("admin.promos.workspace.common.noDescription")}</p>
                  </div>
                  <div className="broadcast-toolbar__meta">
                    <span className={promoCampaignStatusPillClass(selectedPromoCampaign.status)}>
                      {humanizePromoCampaignStatus(selectedPromoCampaign.status)}
                    </span>
                    <div className="broadcast-header-actions">
                      <button
                        className="ghost-button"
                        type="button"
                        onClick={() => handleEditPromoCampaign(selectedPromoCampaign)}
                      >
                        {t("admin.promos.workspace.selectedCampaign.edit")}
                      </button>
                    </div>
                  </div>
                </section>

                <section className="detail-facts-grid detail-facts-grid--compact">
                  <DetailFact
                    label={t("admin.promos.workspace.selectedCampaign.facts.effect")}
                    value={describePromoEffect(
                      selectedPromoCampaign.effect_type,
                      selectedPromoCampaign.effect_value,
                      selectedPromoCampaign.currency,
                    )}
                  />
                  <DetailFact
                    label={t("admin.promos.workspace.selectedCampaign.facts.codes")}
                    value={String(selectedPromoCampaign.codes_count)}
                  />
                  <DetailFact
                    label={t("admin.promos.workspace.selectedCampaign.facts.activations")}
                    value={String(selectedPromoCampaign.redemptions_count)}
                  />
                  <DetailFact
                    label={t("admin.promos.workspace.selectedCampaign.facts.history")}
                    value={String(promoRedemptionTotal)}
                  />
                  <DetailFact
                    label={t("admin.promos.workspace.selectedCampaign.facts.window")}
                    value={
                      selectedPromoCampaign.starts_at || selectedPromoCampaign.ends_at
                        ? t("admin.promos.workspace.common.limitedWindow")
                        : t("admin.promos.workspace.common.openWindow")
                    }
                  />
                </section>

                <section className="detail-sections-grid">
                  <article className="detail-section">
                    <span className="eyebrow">{t("admin.promos.workspace.campaignDetail.rulesEyebrow")}</span>
                    <div className="detail-kv">
                      <div>
                        <span>{t("admin.promos.workspace.campaignDetail.effectType")}</span>
                        <strong>{humanizePromoEffectType(selectedPromoCampaign.effect_type)}</strong>
                      </div>
                      <div>
                        <span>{t("admin.promos.workspace.campaignDetail.window")}</span>
                        <strong>{describePromoCampaignWindow(selectedPromoCampaign)}</strong>
                      </div>
                      <div>
                        <span>{t("admin.promos.workspace.campaignDetail.firstPurchase")}</span>
                        <strong>
                          {selectedPromoCampaign.first_purchase_only
                            ? t("admin.promos.workspace.common.yes")
                            : t("admin.promos.workspace.common.no")}
                        </strong>
                      </div>
                      <div>
                        <span>{t("admin.promos.workspace.campaignDetail.subscriptionRequirementLabel")}</span>
                        <strong>{describePromoSubscriptionRequirement(selectedPromoCampaign)}</strong>
                      </div>
                      <div>
                        <span>{t("admin.promos.workspace.campaignDetail.totalLimit")}</span>
                        <strong>{describePromoLimit(selectedPromoCampaign.total_redemptions_limit)}</strong>
                      </div>
                      <div>
                        <span>{t("admin.promos.workspace.campaignDetail.perAccountLimit")}</span>
                        <strong>{describePromoLimit(selectedPromoCampaign.per_account_redemptions_limit)}</strong>
                      </div>
                    </div>
                  </article>

                  <article className="detail-section">
                    <span className="eyebrow">{t("admin.promos.workspace.campaignDetail.serviceEyebrow")}</span>
                    <div className="detail-kv">
                      <div>
                        <span>{t("admin.promos.workspace.campaignDetail.plans")}</span>
                        <strong>{describePromoPlanScope(selectedPromoCampaign.plan_codes)}</strong>
                      </div>
                      <div>
                        <span>{t("admin.promos.workspace.campaignDetail.createdAt")}</span>
                        <strong>{formatDateMoscow(selectedPromoCampaign.created_at)}</strong>
                      </div>
                      <div>
                        <span>{t("admin.promos.workspace.campaignDetail.updatedAt")}</span>
                        <strong>{formatDateMoscow(selectedPromoCampaign.updated_at)}</strong>
                      </div>
                      <div>
                        <span>{t("admin.promos.workspace.campaignDetail.createdBy")}</span>
                        <strong>{selectedPromoCampaign.created_by_admin_id || t("admin.common.notSpecified")}</strong>
                      </div>
                    </div>
                  </article>
                </section>

                <section className="promo-tools-grid">
                  <article className="detail-section detail-section--action promo-tool-card">
                    <div className="detail-section__intro">
                      <span className="eyebrow">{t("admin.promos.workspace.singleCode.eyebrow")}</span>
                      <h3>{t("admin.promos.workspace.singleCode.title")}</h3>
                      <p>{t("admin.promos.workspace.singleCode.description")}</p>
                    </div>
                    <form className="adjustment-form adjustment-form--runtime" onSubmit={handleCreatePromoCode}>
                      <label className="form-field">
                        <span>{t("admin.promos.workspace.singleCode.fields.code")}</span>
                        <input
                          value={promoCodeValue}
                          onChange={(event) => setPromoCodeValue(event.target.value.toUpperCase())}
                          placeholder={t("admin.promos.workspace.singleCode.fields.codePlaceholder")}
                          required
                          disabled={promoCodeSubmitting}
                        />
                      </label>
                      <label className="form-field">
                        <span>{t("admin.promos.workspace.singleCode.fields.limit")}</span>
                        <input
                          type="number"
                          step="1"
                          min="1"
                          value={promoCodeMaxRedemptions}
                          onChange={(event) => setPromoCodeMaxRedemptions(event.target.value)}
                          placeholder={t("admin.promos.workspace.campaignForm.fields.limitPlaceholder")}
                          disabled={promoCodeSubmitting}
                        />
                      </label>
                      <label className="form-field form-field--wide">
                        <span>{t("admin.promos.workspace.singleCode.fields.accountId")}</span>
                        <input
                          value={promoCodeAssignedAccountId}
                          onChange={(event) => setPromoCodeAssignedAccountId(event.target.value)}
                          placeholder={t("admin.promos.workspace.singleCode.fields.accountIdPlaceholder")}
                          disabled={promoCodeSubmitting}
                        />
                      </label>
                      <label className="checkbox-card checkbox-card--inline">
                        <input
                          type="checkbox"
                          checked={promoCodeIsActive}
                          onChange={(event) => setPromoCodeIsActive(event.target.checked)}
                          disabled={promoCodeSubmitting}
                        />
                        <span>{t("admin.promos.workspace.singleCode.fields.isActive")}</span>
                      </label>
                      <div className="adjustment-form__footer">
                        <span className="form-hint">
                          {t("admin.promos.workspace.singleCode.effectSummary", {
                            effect: describePromoEffect(
                              selectedPromoCampaign.effect_type,
                              selectedPromoCampaign.effect_value,
                              selectedPromoCampaign.currency,
                            ),
                          })}
                        </span>
                        <button className="action-button" type="submit" disabled={promoCodeSubmitting}>
                          {promoCodeSubmitting
                            ? t("admin.promos.workspace.singleCode.buttons.creating")
                            : t("admin.promos.workspace.singleCode.buttons.create")}
                        </button>
                      </div>
                    </form>
                  </article>

                  <article className="detail-section detail-section--action promo-tool-card">
                    <div className="detail-section__intro">
                      <span className="eyebrow">{t("admin.promos.workspace.batch.eyebrow")}</span>
                      <h3>{t("admin.promos.workspace.batch.title")}</h3>
                      <p>{t("admin.promos.workspace.batch.description")}</p>
                    </div>
                    <form className="adjustment-form adjustment-form--runtime" onSubmit={handleBatchCreatePromoCodes}>
                      <label className="form-field">
                        <span>{t("admin.promos.workspace.batch.fields.quantity")}</span>
                        <input
                          type="number"
                          step="1"
                          min="1"
                          max="500"
                          value={promoBatchQuantity}
                          onChange={(event) => setPromoBatchQuantity(event.target.value)}
                          disabled={promoBatchSubmitting}
                          required
                        />
                      </label>
                      <label className="form-field">
                        <span>{t("admin.promos.workspace.batch.fields.prefix")}</span>
                        <input
                          value={promoBatchPrefix}
                          onChange={(event) => setPromoBatchPrefix(event.target.value.toUpperCase())}
                          placeholder={t("admin.promos.workspace.batch.fields.prefixPlaceholder")}
                          disabled={promoBatchSubmitting}
                        />
                      </label>
                      <label className="form-field">
                        <span>{t("admin.promos.workspace.batch.fields.suffixLength")}</span>
                        <input
                          type="number"
                          step="1"
                          min="4"
                          max="24"
                          value={promoBatchSuffixLength}
                          onChange={(event) => setPromoBatchSuffixLength(event.target.value)}
                          disabled={promoBatchSubmitting}
                          required
                        />
                      </label>
                      <label className="form-field">
                        <span>{t("admin.promos.workspace.batch.fields.limit")}</span>
                        <input
                          type="number"
                          step="1"
                          min="1"
                          value={promoBatchMaxRedemptions}
                          onChange={(event) => setPromoBatchMaxRedemptions(event.target.value)}
                          placeholder={t("admin.promos.workspace.campaignForm.fields.limitPlaceholder")}
                          disabled={promoBatchSubmitting}
                        />
                      </label>
                      <label className="form-field form-field--wide">
                        <span>{t("admin.promos.workspace.batch.fields.accountId")}</span>
                        <input
                          value={promoBatchAssignedAccountId}
                          onChange={(event) => setPromoBatchAssignedAccountId(event.target.value)}
                          placeholder={t("admin.promos.workspace.batch.fields.accountIdPlaceholder")}
                          disabled={promoBatchSubmitting}
                        />
                      </label>
                      <label className="checkbox-card checkbox-card--inline">
                        <input
                          type="checkbox"
                          checked={promoBatchIsActive}
                          onChange={(event) => setPromoBatchIsActive(event.target.checked)}
                          disabled={promoBatchSubmitting}
                        />
                        <span>{t("admin.promos.workspace.batch.fields.isActive")}</span>
                      </label>
                      <div className="adjustment-form__footer">
                        <span className="form-hint">
                          {t("admin.promos.workspace.batch.example", {
                            example: `${promoBatchPrefix.trim() ? `${promoBatchPrefix.trim().toUpperCase()}-` : ""}${"X".repeat(Math.max(Number.parseInt(promoBatchSuffixLength || "8", 10) || 8, 4))}`,
                          })}
                        </span>
                        <button className="action-button" type="submit" disabled={promoBatchSubmitting}>
                          {promoBatchSubmitting
                            ? t("admin.promos.workspace.batch.buttons.creating")
                            : t("admin.promos.workspace.batch.buttons.create")}
                        </button>
                      </div>
                    </form>
                    {promoLastGeneratedCodes.length > 0 ? (
                      <article className="note-card">
                        <strong>{t("admin.promos.workspace.batch.lastBatchTitle")}</strong>
                        <p>{promoLastGeneratedCodes.join("\n")}</p>
                      </article>
                    ) : null}
                  </article>

                  <article className="detail-section detail-section--action promo-tool-card promo-tool-card--wide">
                    <div className="detail-section__intro">
                      <span className="eyebrow">{t("admin.promos.workspace.importExport.eyebrow")}</span>
                      <h3>{t("admin.promos.workspace.importExport.title")}</h3>
                      <p>{t("admin.promos.workspace.importExport.description")}</p>
                    </div>
                    <form className="adjustment-form adjustment-form--runtime" onSubmit={handleImportPromoCodes}>
                      <label className="form-field form-field--wide">
                        <span>{t("admin.promos.workspace.importExport.fields.codes")}</span>
                        <textarea
                          rows={8}
                          value={promoImportCodesText}
                          onChange={(event) => setPromoImportCodesText(event.target.value.toUpperCase())}
                          placeholder={t("admin.promos.workspace.importExport.fields.codesPlaceholder")}
                          disabled={promoImportSubmitting}
                          required
                        />
                      </label>
                      <label className="form-field">
                        <span>{t("admin.promos.workspace.importExport.fields.limit")}</span>
                        <input
                          type="number"
                          step="1"
                          min="1"
                          value={promoImportMaxRedemptions}
                          onChange={(event) => setPromoImportMaxRedemptions(event.target.value)}
                          placeholder={t("admin.promos.workspace.campaignForm.fields.limitPlaceholder")}
                          disabled={promoImportSubmitting}
                        />
                      </label>
                      <label className="form-field form-field--wide">
                        <span>{t("admin.promos.workspace.importExport.fields.accountId")}</span>
                        <input
                          value={promoImportAssignedAccountId}
                          onChange={(event) => setPromoImportAssignedAccountId(event.target.value)}
                          placeholder={t("admin.promos.workspace.importExport.fields.accountIdPlaceholder")}
                          disabled={promoImportSubmitting}
                        />
                      </label>
                      <label className="checkbox-card checkbox-card--inline">
                        <input
                          type="checkbox"
                          checked={promoImportIsActive}
                          onChange={(event) => setPromoImportIsActive(event.target.checked)}
                          disabled={promoImportSubmitting}
                        />
                        <span>{t("admin.promos.workspace.importExport.fields.isActive")}</span>
                      </label>
                      <label className="checkbox-card checkbox-card--inline">
                        <input
                          type="checkbox"
                          checked={promoImportSkipDuplicates}
                          onChange={(event) => setPromoImportSkipDuplicates(event.target.checked)}
                          disabled={promoImportSubmitting}
                        />
                        <span>{t("admin.promos.workspace.importExport.fields.skipDuplicates")}</span>
                      </label>
                      <div className="adjustment-form__footer">
                        <span className="form-hint">{t("admin.promos.workspace.importExport.importHint")}</span>
                        <button className="action-button" type="submit" disabled={promoImportSubmitting}>
                          {promoImportSubmitting
                            ? t("admin.promos.workspace.importExport.buttons.importing")
                            : t("admin.promos.workspace.importExport.buttons.import")}
                        </button>
                      </div>
                    </form>
                    {promoImportSkippedCodes.length > 0 ? (
                      <article className="note-card note-card--secondary">
                        <strong>{t("admin.promos.workspace.importExport.skippedTitle")}</strong>
                        <p>{promoImportSkippedCodes.join(", ")}</p>
                      </article>
                    ) : null}
                    <div className="promo-export-panel">
                      <div className="detail-section__header detail-section__header--stacked">
                        <div>
                          <span className="eyebrow">{t("admin.promos.workspace.importExport.exportEyebrow")}</span>
                          <h3>{t("admin.promos.workspace.importExport.exportTitle")}</h3>
                        </div>
                        <button
                          className="ghost-button"
                          type="button"
                          onClick={() => void handleExportPromoCodes()}
                          disabled={promoExportSubmitting}
                        >
                          {promoExportSubmitting
                            ? t("admin.promos.workspace.importExport.buttons.exporting")
                            : t("admin.promos.workspace.importExport.buttons.export")}
                        </button>
                      </div>
                      <label className="form-field form-field--wide">
                        <span>{t("admin.promos.workspace.importExport.exportField")}</span>
                        <textarea
                          readOnly
                          rows={Math.min(Math.max(promoExportText.split("\n").length, 6), 16)}
                          value={promoExportText}
                          placeholder={t("admin.promos.workspace.importExport.exportPlaceholder")}
                        />
                      </label>
                    </div>
                  </article>
                </section>

                <section className="detail-section">
                  <div className="detail-section__header detail-section__header--stacked">
                    <div>
                      <span className="eyebrow">{t("admin.promos.workspace.codeTable.eyebrow")}</span>
                      <h3>{t("admin.promos.workspace.codeTable.title")}</h3>
                    </div>
                    <span className="form-hint">
                      {t("admin.promos.workspace.codeTable.summary", { total: promoCodeTotal })}
                    </span>
                  </div>
                  <div className="accounts-table__wrap promo-table__wrap">
                    <table className="accounts-table promo-table promo-table--codes">
                      <thead>
                        <tr>
                          <th>{t("admin.promos.workspace.codeTable.columns.code")}</th>
                          <th>{t("admin.promos.workspace.codeTable.columns.status")}</th>
                          <th>{t("admin.promos.workspace.codeTable.columns.account")}</th>
                          <th>{t("admin.promos.workspace.codeTable.columns.limit")}</th>
                          <th>{t("admin.promos.workspace.codeTable.columns.createdAt")}</th>
                          <th>{t("admin.promos.workspace.codeTable.columns.actions")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {promoCodesLoading ? (
                          <tr>
                            <td className="accounts-table__empty" colSpan={6}>
                              {t("admin.promos.workspace.codeTable.loading")}
                            </td>
                          </tr>
                        ) : promoCodeItems.length === 0 ? (
                          <tr>
                            <td className="accounts-table__empty" colSpan={6}>
                              {t("admin.promos.workspace.codeTable.empty")}
                            </td>
                          </tr>
                        ) : (
                          promoCodeItems.map((promoCode) => (
                            <tr key={promoCode.id}>
                              <td>
                                <div className="promo-table__title-cell">
                                  <strong>{promoCode.code}</strong>
                                  <small>
                                    {t("admin.promos.workspace.codeTable.redemptionsValue", {
                                      count: promoCode.redemptions_count,
                                    })}
                                  </small>
                                </div>
                              </td>
                              <td>
                                <span
                                  className={
                                    promoCode.is_active
                                      ? "status-pill status-pill--active"
                                      : "status-pill status-pill--cancelled"
                                  }
                                >
                                  {describePromoCodeStatus(promoCode.is_active)}
                                </span>
                              </td>
                              <td title={promoCode.assigned_account_id || undefined}>
                                {describePromoCodeAssignment(promoCode.assigned_account_id)}
                              </td>
                              <td>{describePromoCodeLimit(promoCode.max_redemptions)}</td>
                              <td>{formatDateMoscow(promoCode.created_at)}</td>
                              <td>
                                <button
                                  className="ghost-button"
                                  type="button"
                                  onClick={() => void handleTogglePromoCodeActivity(promoCode)}
                                  disabled={promoCodeActionId === promoCode.id}
                                >
                                  {promoCodeActionId === promoCode.id
                                    ? t("admin.promos.workspace.codeTable.buttons.saving")
                                    : promoCode.is_active
                                      ? t("admin.promos.workspace.codeTable.buttons.disable")
                                      : t("admin.promos.workspace.codeTable.buttons.enable")}
                                </button>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="detail-section">
                  <div className="detail-section__header detail-section__header--stacked">
                    <div>
                      <span className="eyebrow">{t("admin.promos.workspace.redemptions.eyebrow")}</span>
                      <h3>{t("admin.promos.workspace.redemptions.title")}</h3>
                    </div>
                    <span className="form-hint">
                      {t("admin.promos.workspace.redemptions.summary", {
                        shown: promoRedemptionItems.length,
                        total: promoRedemptionTotal,
                      })}
                    </span>
                  </div>
                  <form className="promo-filters-grid" onSubmit={handleApplyPromoRedemptionFilters}>
                    <label className="form-field">
                      <span>{t("admin.promos.workspace.redemptions.filters.status")}</span>
                      <select
                        value={promoRedemptionStatusFilter}
                        onChange={(event) =>
                          setPromoRedemptionStatusFilter(event.target.value as PromoRedemptionStatusFilter)
                        }
                        disabled={promoRedemptionsLoading}
                      >
                        <option value="all">{t("admin.promos.workspace.redemptions.filters.allStatuses")}</option>
                        {PROMO_REDEMPTION_STATUS_OPTIONS.map((status) => (
                          <option key={status} value={status}>
                            {humanizePromoRedemptionStatus(status)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="form-field">
                      <span>{t("admin.promos.workspace.redemptions.filters.context")}</span>
                      <select
                        value={promoRedemptionContextFilter}
                        onChange={(event) =>
                          setPromoRedemptionContextFilter(event.target.value as PromoRedemptionContextFilter)
                        }
                        disabled={promoRedemptionsLoading}
                      >
                        <option value="all">{t("admin.promos.workspace.redemptions.filters.allContexts")}</option>
                        {PROMO_REDEMPTION_CONTEXT_OPTIONS.map((context) => (
                          <option key={context} value={context}>
                            {humanizePromoRedemptionContext(context)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="form-field">
                      <span>{t("admin.promos.workspace.redemptions.filters.code")}</span>
                      <input
                        value={promoRedemptionCodeQueryInput}
                        onChange={(event) => setPromoRedemptionCodeQueryInput(event.target.value.toUpperCase())}
                        placeholder={t("admin.promos.workspace.redemptions.filters.codePlaceholder")}
                        disabled={promoRedemptionsLoading}
                      />
                    </label>
                    <label className="form-field">
                      <span>{t("admin.promos.workspace.redemptions.filters.account")}</span>
                      <input
                        value={promoRedemptionAccountIdInput}
                        onChange={(event) => setPromoRedemptionAccountIdInput(event.target.value)}
                        placeholder={t("admin.promos.workspace.redemptions.filters.accountPlaceholder")}
                        disabled={promoRedemptionsLoading}
                      />
                    </label>
                    <div className="promo-filters-grid__footer">
                      <span className="form-hint">
                        {promoRedemptionFiltersActive
                          ? t("admin.promos.workspace.redemptions.filters.activeHint")
                          : t("admin.promos.workspace.redemptions.filters.defaultHint")}
                      </span>
                      <div className="action-cluster">
                        <button
                          className="ghost-button"
                          type="button"
                          onClick={handleResetPromoRedemptionFilters}
                          disabled={promoRedemptionsLoading}
                        >
                          {t("admin.promos.workspace.redemptions.filters.reset")}
                        </button>
                        <button className="action-button" type="submit" disabled={promoRedemptionsLoading}>
                          {promoRedemptionsLoading
                            ? t("admin.promos.workspace.redemptions.filters.applying")
                            : t("admin.promos.workspace.redemptions.filters.apply")}
                        </button>
                      </div>
                    </div>
                  </form>
                  <div className="accounts-table__wrap promo-table__wrap">
                    <table className="accounts-table promo-table promo-table--redemptions">
                      <thead>
                        <tr>
                          <th>{t("admin.promos.workspace.redemptions.columns.code")}</th>
                          <th>{t("admin.promos.workspace.redemptions.columns.status")}</th>
                          <th>{t("admin.promos.workspace.redemptions.columns.context")}</th>
                          <th>{t("admin.promos.workspace.redemptions.columns.account")}</th>
                          <th>{t("admin.promos.workspace.redemptions.columns.result")}</th>
                          <th>{t("admin.promos.workspace.redemptions.columns.createdAt")}</th>
                          <th>{t("admin.promos.workspace.redemptions.columns.details")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {promoRedemptionsLoading ? (
                          <tr>
                            <td className="accounts-table__empty" colSpan={7}>
                              {t("admin.promos.workspace.redemptions.loading")}
                            </td>
                          </tr>
                        ) : promoRedemptionItems.length === 0 ? (
                          <tr>
                            <td className="accounts-table__empty" colSpan={7}>
                              {t("admin.promos.workspace.redemptions.empty")}
                            </td>
                          </tr>
                        ) : (
                          promoRedemptionItems.map((redemption) => (
                            <tr key={redemption.id}>
                              <td>
                                <div className="promo-table__title-cell">
                                  <strong>{redemption.promo_code}</strong>
                                  <small>{describePromoEffect(redemption.effect_type, redemption.effect_value, redemption.currency)}</small>
                                </div>
                              </td>
                              <td>
                                <span className={promoRedemptionStatusPillClass(redemption.status)}>
                                  {humanizePromoRedemptionStatus(redemption.status)}
                                </span>
                              </td>
                              <td>{humanizePromoRedemptionContext(redemption.redemption_context)}</td>
                              <td title={redemption.account_id}>
                                <div className="promo-table__title-cell">
                                  <strong>{formatCompactId(redemption.account_id)}</strong>
                                  <small>
                                    {redemption.plan_code
                                      ? t("admin.promos.workspace.redemptions.planValue", {
                                          planCode: redemption.plan_code,
                                        })
                                      : t("admin.promos.workspace.redemptions.planEmpty")}
                                  </small>
                                </div>
                              </td>
                              <td>{describePromoRedemptionOutcome(redemption)}</td>
                              <td>
                                <div className="promo-table__title-cell">
                                  <strong>{formatDateMoscow(redemption.created_at)}</strong>
                                  <small>
                                    {redemption.applied_at
                                      ? t("admin.promos.workspace.redemptions.appliedValue", {
                                          date: formatDateMoscow(redemption.applied_at),
                                        })
                                      : t("admin.promos.workspace.redemptions.appliedEmpty")}
                                  </small>
                                </div>
                              </td>
                              <td>{describePromoRedemptionReference(redemption)}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>
              </>
            )}
          </div>
        </section>
      ) : activeView === "broadcasts" ? (
        <section className="search-shell search-shell--broadcasts">
          <div className="detail-column detail-column--broadcasts">
            <section className="search-panel search-panel--broadcasts">
              <div className="panel-toolbar">
                <div>
                  <span className="eyebrow">{t("admin.broadcasts.overview.eyebrow")}</span>
                  <h2>{t("admin.broadcasts.overview.title")}</h2>
                  <p className="queue-panel__copy">{t("admin.broadcasts.overview.description")}</p>
                </div>
                <div className="panel-toolbar__actions">
                  <button className="ghost-button" type="button" onClick={handleNewBroadcastDraft}>
                    {t("admin.broadcasts.overview.newDraft")}
                  </button>
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => void handleRefreshBroadcastWorkspace()}
                    disabled={broadcastWorkspaceRefreshing}
                  >
                    {broadcastWorkspaceRefreshing ? t("admin.actions.refreshing") : t("admin.actions.refresh")}
                  </button>
                </div>
              </div>

              <div className="broadcasts-overview-grid">
                <article className="broadcasts-overview-card">
                  <div className="broadcasts-overview-card__header">
                    <div>
                      <span className="eyebrow">{t("admin.broadcasts.overview.generalEyebrow")}</span>
                      <h3>{t("admin.broadcasts.overview.generalTitle")}</h3>
                    </div>
                    <span className="form-hint">{t("admin.broadcasts.overview.generalDescription")}</span>
                  </div>
                  <div className="queue-summary queue-summary--broadcasts">
                    <article className="queue-summary__item">
                      <span>{t("admin.broadcasts.overview.stats.campaignsTotal")}</span>
                      <strong>{broadcastTotal}</strong>
                    </article>
                    <article className="queue-summary__item">
                      <span>{t("admin.broadcasts.overview.stats.drafts")}</span>
                      <strong>{broadcastDraftCount}</strong>
                    </article>
                    <article className="queue-summary__item">
                      <span>{t("admin.broadcasts.overview.stats.active")}</span>
                      <strong>{broadcastActiveCount}</strong>
                    </article>
                    <article className="queue-summary__item">
                      <span>{t("admin.broadcasts.overview.stats.runsTotal")}</span>
                      <strong>{broadcastRunTotal}</strong>
                    </article>
                  </div>
                </article>

                <article className="broadcasts-overview-card broadcasts-overview-card--selected">
                  <div className="broadcasts-overview-card__header">
                    <div>
                      <span className="eyebrow">{t("admin.broadcasts.overview.selectionEyebrow")}</span>
                      <h3>
                        {selectedBroadcast
                          ? selectedBroadcast.title || selectedBroadcast.name
                          : t("admin.broadcasts.overview.selectionDraftTitle")}
                      </h3>
                    </div>
                    <span className="form-hint">{t("admin.broadcasts.overview.selectionDescription")}</span>
                  </div>
                  <div className="queue-summary queue-summary--broadcasts">
                    <article className="queue-summary__item">
                      <span>{t("admin.broadcasts.overview.stats.status")}</span>
                      <strong>
                        {selectedBroadcast
                          ? humanizeBroadcastStatus(selectedBroadcast.status)
                          : t("admin.broadcasts.overview.stats.selectedNone")}
                      </strong>
                    </article>
                    <article className="queue-summary__item">
                      <span>{t("admin.broadcasts.overview.stats.channels")}</span>
                      <strong>
                        {broadcastChannels.length > 0
                          ? humanizeBroadcastChannels(broadcastChannels)
                          : t("admin.broadcasts.overview.stats.channelsEmpty")}
                      </strong>
                    </article>
                    <article className="queue-summary__item">
                      <span>{t("admin.broadcasts.overview.stats.audience")}</span>
                      <strong>{broadcastAudiencePreviewSummary}</strong>
                    </article>
                    <article className="queue-summary__item">
                      <span>{t("admin.broadcasts.overview.stats.audienceTotal")}</span>
                      <strong>
                        {broadcastEstimateSnapshot
                          ? String(broadcastEstimateSnapshot.estimated_total_accounts)
                          : "—"}
                      </strong>
                    </article>
                    <article className="queue-summary__item">
                      <span>{t("admin.broadcasts.overview.stats.inApp")}</span>
                      <strong>
                        {broadcastEstimateSnapshot
                          ? String(broadcastEstimateSnapshot.estimated_in_app_recipients)
                          : "—"}
                      </strong>
                    </article>
                    <article className="queue-summary__item">
                      <span>{t("admin.broadcasts.overview.stats.telegram")}</span>
                      <strong>
                        {broadcastEstimateSnapshot
                          ? String(broadcastEstimateSnapshot.estimated_telegram_recipients)
                          : "—"}
                      </strong>
                    </article>
                    <article className="queue-summary__item">
                      <span>{t("admin.broadcasts.overview.stats.updated")}</span>
                      <strong>
                        {selectedBroadcast
                          ? formatDateMoscow(selectedBroadcast.updated_at)
                          : t("admin.broadcasts.overview.stats.updatedEmpty")}
                      </strong>
                    </article>
                    <article className="queue-summary__item">
                      <span>{t("admin.broadcasts.overview.stats.estimateStatus")}</span>
                      <strong>
                        {broadcastEstimateLoading
                          ? t("admin.broadcasts.overview.stats.estimateRefreshing")
                          : broadcastEstimateError
                            ? t("admin.broadcasts.overview.stats.estimateError")
                            : t("admin.broadcasts.overview.stats.estimateReady")}
                      </strong>
                    </article>
                  </div>
                  <div className="broadcasts-overview-card__footer">
                    <span className="form-hint">
                      {broadcastEstimateError || t("admin.broadcasts.overview.selectionHint")}
                    </span>
                  </div>
                </article>
              </div>
            </section>

            <section className="detail-section detail-section--action">
              <div className="detail-section__header detail-section__header--stacked">
                <div>
                  <span className="eyebrow">{t("admin.broadcasts.campaignTable.eyebrow")}</span>
                  <h3>{t("admin.broadcasts.campaignTable.title")}</h3>
                </div>
                <span className="form-hint">{t("admin.broadcasts.campaignTable.description")}</span>
              </div>

              <div className="accounts-table__wrap broadcasts-table__wrap">
                <table className="accounts-table broadcasts-table">
                  <thead>
                    <tr>
                      <th scope="col">{t("admin.broadcasts.campaignTable.columns.campaign")}</th>
                      <th scope="col">{t("admin.broadcasts.campaignTable.columns.status")}</th>
                      <th scope="col">{t("admin.broadcasts.campaignTable.columns.channels")}</th>
                      <th scope="col">{t("admin.broadcasts.campaignTable.columns.audience")}</th>
                      <th scope="col">{t("admin.broadcasts.campaignTable.columns.recipients")}</th>
                      <th scope="col">{t("admin.broadcasts.campaignTable.columns.lastRun")}</th>
                      <th scope="col">{t("admin.broadcasts.campaignTable.columns.updated")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {broadcastsLoading ? (
                      <tr>
                        <td colSpan={7} className="accounts-table__empty">
                          {t("admin.broadcasts.campaignTable.loading")}
                        </td>
                      </tr>
                    ) : broadcastItems.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="accounts-table__empty">
                          {t("admin.broadcasts.campaignTable.empty")}
                        </td>
                      </tr>
                    ) : (
                      broadcastItems.map((item) => (
                        <tr
                          key={item.id}
                          className={
                            selectedBroadcastId === item.id
                              ? "accounts-table__row accounts-table__row--active"
                              : "accounts-table__row"
                          }
                          onClick={() => handleSelectBroadcast(item.id)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              void handleSelectBroadcast(item.id);
                            }
                          }}
                          tabIndex={0}
                        >
                          <td>
                            <div className="broadcasts-table__cell broadcasts-table__cell--campaign">
                              <strong>{item.name}</strong>
                              <small>{item.title || t("admin.broadcasts.campaignTable.untitled")}</small>
                            </div>
                          </td>
                          <td>
                            <span className={`status-pill status-pill--${item.status}`}>
                              {humanizeBroadcastStatus(item.status)}
                            </span>
                          </td>
                          <td>{humanizeBroadcastChannels(item.channels)}</td>
                          <td>
                            <div className="broadcasts-table__cell">
                              <strong>{formatBroadcastAudienceSummary(item.audience)}</strong>
                              <small>
                                {t("admin.broadcasts.campaignTable.estimatedRecipients", {
                                  count: item.estimated_total_accounts,
                                })}
                              </small>
                            </div>
                          </td>
                          <td>{item.estimated_total_accounts}</td>
                          <td>
                            <div className="broadcasts-table__cell">
                              <strong>
                                {item.latest_run
                                  ? `${humanizeBroadcastRunStatus(item.latest_run.status)} · ${humanizeBroadcastRunType(
                                      item.latest_run.run_type,
                                    )}`
                                  : t("admin.broadcasts.campaignTable.runNever")}
                              </strong>
                              <small>
                                {item.latest_run
                                  ? t("admin.broadcasts.campaignTable.delivered", {
                                      delivered: item.latest_run.delivered_deliveries,
                                      total: item.latest_run.total_deliveries,
                                    })
                                  : t("admin.broadcasts.campaignTable.draftOnly")}
                              </small>
                            </div>
                          </td>
                          <td>{formatDateMoscow(item.updated_at)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="detail-section detail-section--action">
              <div className="detail-section__header detail-section__header--stacked">
                <div>
                  <span className="eyebrow">{t("admin.broadcasts.audienceLibrary.eyebrow")}</span>
                  <h3>{t("admin.broadcasts.audienceLibrary.title")}</h3>
                </div>
                <span className="form-hint">{t("admin.broadcasts.audienceLibrary.description")}</span>
              </div>

              <div className="broadcast-audience-library">
                <article className="broadcast-audience-preset-panel broadcast-audience-preset-panel--editor">
                  <div className="broadcast-audience-preset-panel__header">
                    <div>
                      <span className="eyebrow">{t("admin.broadcasts.audienceLibrary.editorEyebrow")}</span>
                      <h5>{t("admin.broadcasts.audienceLibrary.editorTitle")}</h5>
                    </div>
                    <span className="form-hint">
                      {`${broadcastAudiencePresetEditorSummary} · ${
                        broadcastAudiencePresetChannels.length > 0
                          ? humanizeBroadcastChannels(broadcastAudiencePresetChannels)
                          : t("admin.broadcasts.overview.stats.channelsEmpty")
                      }`}
                    </span>
                  </div>

                  <div className="broadcast-form-grid">
                    <label className="form-field">
                      <span>{t("admin.broadcasts.audienceLibrary.fields.name")}</span>
                      <input
                        value={broadcastAudiencePresetName}
                        onChange={(event) => setBroadcastAudiencePresetName(event.target.value)}
                        placeholder={t("admin.broadcasts.audienceLibrary.placeholders.name")}
                        disabled={broadcastAudiencePresetSubmitting}
                      />
                    </label>
                    <label className="form-field">
                      <span>{t("admin.broadcasts.audienceLibrary.fields.description")}</span>
                      <input
                        value={broadcastAudiencePresetDescription}
                        onChange={(event) => setBroadcastAudiencePresetDescription(event.target.value)}
                        placeholder={t("admin.broadcasts.audienceLibrary.placeholders.description")}
                        disabled={broadcastAudiencePresetSubmitting}
                      />
                    </label>

                    <div className="broadcast-channel-grid">
                      <label className="checkbox-card">
                        <input
                          type="checkbox"
                          checked={broadcastAudiencePresetEditor.sendInApp}
                          onChange={(event) =>
                            setBroadcastAudiencePresetEditor((current) => ({
                              ...current,
                              sendInApp: event.target.checked,
                            }))
                          }
                          disabled={broadcastAudiencePresetSubmitting}
                        />
                        <span>{t("admin.broadcasts.channels.inApp")}</span>
                      </label>
                      <label className="checkbox-card">
                        <input
                          type="checkbox"
                          checked={broadcastAudiencePresetEditor.sendTelegram}
                          onChange={(event) =>
                            setBroadcastAudiencePresetEditor((current) => ({
                              ...current,
                              sendTelegram: event.target.checked,
                            }))
                          }
                          disabled={broadcastAudiencePresetSubmitting}
                        />
                        <span>{t("admin.broadcasts.channels.telegram")}</span>
                      </label>
                    </div>

                    <label className="form-field">
                      <span>{t("admin.broadcasts.audienceLibrary.fields.segment")}</span>
                      <select
                        value={broadcastAudiencePresetEditor.segment}
                        onChange={(event) =>
                          setBroadcastAudiencePresetEditor((current) => ({
                            ...current,
                            segment: event.target.value as BroadcastAudienceSegment,
                          }))
                        }
                        disabled={broadcastAudiencePresetSubmitting}
                      >
                        {BROADCAST_AUDIENCE_SEGMENTS.map((segment) => (
                          <option key={segment} value={segment}>
                            {humanizeBroadcastAudienceSegment(segment)}
                          </option>
                        ))}
                      </select>
                    </label>

                    {broadcastAudiencePresetEditor.segment === "manual_list" ? (
                      <label className="form-field form-field--wide">
                        <span>{t("admin.broadcasts.audienceLibrary.fields.manualList")}</span>
                        <textarea
                          value={broadcastAudiencePresetEditor.manualTargetsInput}
                          onChange={(event) =>
                            setBroadcastAudiencePresetEditor((current) => ({
                              ...current,
                              manualTargetsInput: event.target.value,
                            }))
                          }
                          placeholder={t("admin.broadcasts.audienceLibrary.placeholders.manualList")}
                          rows={8}
                          disabled={broadcastAudiencePresetSubmitting}
                        />
                      </label>
                    ) : null}

                    {broadcastAudiencePresetEditor.segment === "inactive_accounts" ||
                    broadcastAudiencePresetEditor.segment === "inactive_paid_users" ? (
                      <>
                        <label className="form-field">
                          <span>{t("admin.broadcasts.audienceLibrary.fields.inactiveDays")}</span>
                          <input
                            type="number"
                            min={1}
                            value={broadcastAudiencePresetEditor.lastSeenOlderThanDays}
                            onChange={(event) =>
                              setBroadcastAudiencePresetEditor((current) => ({
                                ...current,
                                lastSeenOlderThanDays: event.target.value,
                              }))
                            }
                            placeholder="7"
                            disabled={broadcastAudiencePresetSubmitting}
                          />
                        </label>
                        <label className="checkbox-card checkbox-card--inline">
                          <input
                            type="checkbox"
                            checked={broadcastAudiencePresetEditor.includeNeverSeen}
                            onChange={(event) =>
                              setBroadcastAudiencePresetEditor((current) => ({
                                ...current,
                                includeNeverSeen: event.target.checked,
                              }))
                            }
                            disabled={broadcastAudiencePresetSubmitting}
                          />
                          <span>{t("admin.broadcasts.audienceLibrary.fields.includeNeverSeen")}</span>
                        </label>
                      </>
                    ) : null}

                    {broadcastAudiencePresetEditor.segment === "abandoned_checkout" ? (
                      <>
                        <label className="form-field">
                          <span>{t("admin.broadcasts.audienceLibrary.fields.pendingOlderThanMinutes")}</span>
                          <input
                            type="number"
                            min={1}
                            value={broadcastAudiencePresetEditor.pendingPaymentOlderThanMinutes}
                            onChange={(event) =>
                              setBroadcastAudiencePresetEditor((current) => ({
                                ...current,
                                pendingPaymentOlderThanMinutes: event.target.value,
                              }))
                            }
                            placeholder="30"
                            disabled={broadcastAudiencePresetSubmitting}
                          />
                        </label>
                        <label className="form-field">
                          <span>{t("admin.broadcasts.audienceLibrary.fields.pendingWithinDays")}</span>
                          <input
                            type="number"
                            min={1}
                            value={broadcastAudiencePresetEditor.pendingPaymentWithinLastDays}
                            onChange={(event) =>
                              setBroadcastAudiencePresetEditor((current) => ({
                                ...current,
                                pendingPaymentWithinLastDays: event.target.value,
                              }))
                            }
                            placeholder="7"
                            disabled={broadcastAudiencePresetSubmitting}
                          />
                        </label>
                      </>
                    ) : null}

                    {broadcastAudiencePresetEditor.segment === "failed_payment" ? (
                      <label className="form-field">
                        <span>{t("admin.broadcasts.audienceLibrary.fields.failedWithinDays")}</span>
                        <input
                          type="number"
                          min={1}
                          value={broadcastAudiencePresetEditor.failedPaymentWithinLastDays}
                          onChange={(event) =>
                            setBroadcastAudiencePresetEditor((current) => ({
                              ...current,
                              failedPaymentWithinLastDays: event.target.value,
                            }))
                          }
                          placeholder="7"
                          disabled={broadcastAudiencePresetSubmitting}
                        />
                      </label>
                    ) : null}

                    {broadcastAudiencePresetEditor.segment === "expired" ? (
                      <>
                        <label className="form-field">
                          <span>{t("admin.broadcasts.audienceLibrary.fields.expiredFromDays")}</span>
                          <input
                            type="number"
                            min={0}
                            value={broadcastAudiencePresetEditor.subscriptionExpiredFromDays}
                            onChange={(event) =>
                              setBroadcastAudiencePresetEditor((current) => ({
                                ...current,
                                subscriptionExpiredFromDays: event.target.value,
                              }))
                            }
                            placeholder="30"
                            disabled={broadcastAudiencePresetSubmitting}
                          />
                        </label>
                        <label className="form-field">
                          <span>{t("admin.broadcasts.audienceLibrary.fields.expiredToDays")}</span>
                          <input
                            type="number"
                            min={0}
                            value={broadcastAudiencePresetEditor.subscriptionExpiredToDays}
                            onChange={(event) =>
                              setBroadcastAudiencePresetEditor((current) => ({
                                ...current,
                                subscriptionExpiredToDays: event.target.value,
                              }))
                            }
                            placeholder="90"
                            disabled={broadcastAudiencePresetSubmitting}
                          />
                        </label>
                      </>
                    ) : null}

                    <label className="form-field">
                      <span>{t("admin.broadcasts.audienceLibrary.fields.cooldownDays")}</span>
                      <input
                        type="number"
                        min={1}
                        value={broadcastAudiencePresetEditor.cooldownDays}
                        onChange={(event) =>
                          setBroadcastAudiencePresetEditor((current) => ({
                            ...current,
                            cooldownDays: event.target.value,
                          }))
                        }
                        placeholder="7"
                        disabled={broadcastAudiencePresetSubmitting}
                      />
                    </label>
                    <label className="form-field">
                      <span>{t("admin.broadcasts.audienceLibrary.fields.cooldownKey")}</span>
                      <input
                        value={broadcastAudiencePresetEditor.cooldownKey}
                        onChange={(event) =>
                          setBroadcastAudiencePresetEditor((current) => ({
                            ...current,
                            cooldownKey: event.target.value,
                          }))
                        }
                        placeholder={t("admin.broadcasts.audienceLibrary.placeholders.cooldownKey")}
                        disabled={broadcastAudiencePresetSubmitting}
                      />
                    </label>

                    {broadcastAudiencePresetEditor.sendTelegram ? (
                      <>
                        <label className="form-field">
                          <span>{t("admin.broadcasts.audienceLibrary.fields.telegramQuietStart")}</span>
                          <input
                            type="time"
                            value={broadcastAudiencePresetEditor.telegramQuietHoursStart}
                            onChange={(event) =>
                              setBroadcastAudiencePresetEditor((current) => ({
                                ...current,
                                telegramQuietHoursStart: event.target.value,
                              }))
                            }
                            disabled={broadcastAudiencePresetSubmitting}
                          />
                        </label>
                        <label className="form-field">
                          <span>{t("admin.broadcasts.audienceLibrary.fields.telegramQuietEnd")}</span>
                          <input
                            type="time"
                            value={broadcastAudiencePresetEditor.telegramQuietHoursEnd}
                            onChange={(event) =>
                              setBroadcastAudiencePresetEditor((current) => ({
                                ...current,
                                telegramQuietHoursEnd: event.target.value,
                              }))
                            }
                            disabled={broadcastAudiencePresetSubmitting}
                          />
                        </label>
                      </>
                    ) : null}

                    <label className="checkbox-card checkbox-card--inline">
                      <input
                        type="checkbox"
                        checked={broadcastAudiencePresetEditor.excludeBlocked}
                        onChange={(event) =>
                          setBroadcastAudiencePresetEditor((current) => ({
                            ...current,
                            excludeBlocked: event.target.checked,
                          }))
                        }
                        disabled={broadcastAudiencePresetSubmitting}
                      />
                      <span>{t("admin.broadcasts.audienceLibrary.fields.excludeBlocked")}</span>
                    </label>
                  </div>

                  {broadcastAudiencePresetError ? (
                    <div className="form-hint form-hint--error">{broadcastAudiencePresetError}</div>
                  ) : null}

                  <div className="broadcast-audience-preset-toolbar">
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={handleStartNewBroadcastAudiencePreset}
                      disabled={broadcastAudiencePresetSubmitting}
                    >
                      {t("admin.broadcasts.audienceLibrary.actions.new")}
                    </button>
                    <button
                      className="action-button"
                      type="button"
                      onClick={() => void handleCreateBroadcastAudiencePreset()}
                      disabled={broadcastAudiencePresetSubmitting}
                    >
                      {broadcastAudiencePresetSubmitting && selectedBroadcastAudiencePresetId === null
                        ? t("admin.broadcasts.audienceLibrary.actions.saving")
                        : t("admin.broadcasts.audienceLibrary.actions.save")}
                    </button>
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={() => void handleUpdateBroadcastAudiencePreset()}
                      disabled={broadcastAudiencePresetSubmitting || selectedBroadcastAudiencePresetId === null}
                    >
                      {t("admin.broadcasts.audienceLibrary.actions.update")}
                    </button>
                    <button
                      className="ghost-button ghost-button--danger"
                      type="button"
                      onClick={() => void handleDeleteBroadcastAudiencePreset()}
                      disabled={broadcastAudiencePresetSubmitting || selectedBroadcastAudiencePresetId === null}
                    >
                      {t("admin.broadcasts.audienceLibrary.actions.delete")}
                    </button>
                  </div>
                </article>

                <article className="broadcast-audience-preset-panel broadcast-audience-preset-panel--list">
                  <div className="broadcast-audience-preset-panel__header">
                    <div>
                      <span className="eyebrow">{t("admin.broadcasts.audienceLibrary.listEyebrow")}</span>
                      <h5>{t("admin.broadcasts.audienceLibrary.listTitle")}</h5>
                    </div>
                    <span className="form-hint">
                      {t("admin.broadcasts.audienceLibrary.listCount", {
                        count: broadcastAudiencePresetTotal,
                      })}
                    </span>
                  </div>

                  {broadcastAudiencePresetLoading ? (
                    <div className="activity-empty">{t("admin.broadcasts.audienceLibrary.loading")}</div>
                  ) : broadcastAudiencePresetItems.length === 0 ? (
                    <div className="activity-empty">{t("admin.broadcasts.audienceLibrary.empty")}</div>
                  ) : (
                    <div className="broadcast-audience-preset-list">
                      {broadcastAudiencePresetItems.map((item) => (
                        <article
                          key={item.id}
                          className={`broadcast-audience-preset-card ${
                            item.id === selectedBroadcastAudiencePresetId ? "broadcast-audience-preset-card--active" : ""
                          }`}
                        >
                          <div className="broadcast-audience-preset-card__top">
                            <div>
                              <strong>{item.name}</strong>
                              {item.description ? (
                                <div className="broadcast-audience-preset-card__description">{item.description}</div>
                              ) : null}
                            </div>
                            {matchedBroadcastAudiencePreset?.id === item.id ? (
                              <span className="status-pill status-pill--active">
                                {t("admin.broadcasts.audienceLibrary.inCampaign")}
                              </span>
                            ) : (
                              <span className="form-hint">{formatDateMoscow(item.updated_at)}</span>
                            )}
                          </div>
                          <div className="broadcast-audience-preset-card__summary">
                            <strong>{humanizeBroadcastChannels(item.channels)}</strong>
                            <span>{formatBroadcastAudienceSummary(item.audience)}</span>
                          </div>
                          <div className="broadcast-audience-preset-actions">
                            <button
                              className="ghost-button"
                              type="button"
                              onClick={() => handleSelectBroadcastAudiencePreset(item)}
                              disabled={broadcastAudiencePresetSubmitting}
                            >
                              {item.id === selectedBroadcastAudiencePresetId
                                ? t("admin.broadcasts.audienceLibrary.actions.selected")
                                : t("admin.broadcasts.audienceLibrary.actions.open")}
                            </button>
                            <button
                              className="ghost-button"
                              type="button"
                              onClick={() => handleApplyBroadcastAudiencePreset(item)}
                              disabled={broadcastAudiencePresetSubmitting || (selectedBroadcast !== null && !broadcastIsDraft)}
                            >
                              {t("admin.broadcasts.audienceLibrary.actions.useInCampaign")}
                            </button>
                          </div>
                        </article>
                      ))}
                    </div>
                  )}
                </article>
              </div>
            </section>

            <section className="detail-header detail-header--broadcasts">
              <div className="broadcast-toolbar">
                <div>
                  <span className="eyebrow">
                    {showBroadcastEditor
                      ? t("admin.broadcasts.editorHeader.eyebrow")
                      : t("admin.broadcasts.editorHeader.previewEyebrow")}
                  </span>
                  <h2>{selectedBroadcast ? selectedBroadcast.title : t("admin.broadcasts.editorHeader.newTitle")}</h2>
                  <p>
                    {showBroadcastEditor
                      ? t("admin.broadcasts.editorHeader.description")
                      : t("admin.broadcasts.editorHeader.previewDescription")}
                  </p>
                </div>
              </div>
              <div className="broadcast-toolbar__meta">
                <div className="broadcast-badge-cluster">
                  {showBroadcastEditor ? (
                    <span
                      className={`status-pill ${broadcastEditorDirty ? "status-pill--warning" : "status-pill--active"}`}
                    >
                      {broadcastEditorDirty
                        ? t("admin.broadcasts.editorHeader.dirty")
                        : t("admin.broadcasts.editorHeader.synced")}
                    </span>
                  ) : null}
                  <span
                    className={`status-pill ${
                      selectedBroadcast ? `status-pill--${selectedBroadcast.status}` : "status-pill--draft"
                    }`}
                  >
                    {selectedBroadcast
                      ? humanizeBroadcastStatus(selectedBroadcast.status)
                      : t("admin.broadcasts.editorHeader.newStatus")}
                  </span>
                </div>
              </div>
            </section>

            <section className="broadcast-workbench">
              {showBroadcastEditor ? (
                <section className="detail-section detail-section--action detail-section--editor">
                  <div className="detail-section__header">
                    <div>
                      <span className="eyebrow">Редактор</span>
                      <h3>{broadcastEditorMode === "edit" ? "Контент кампании" : "Создание новой кампании"}</h3>
                    </div>
                  </div>

                  <form className="broadcast-editor-form" onSubmit={handleSaveBroadcast}>
                    <div className="broadcast-form-section broadcast-form-section--compact">
                      <div className="broadcast-form-section__header">
                        <div>
                          <span className="eyebrow">{t("admin.broadcasts.segmentPicker.eyebrow")}</span>
                          <h4>{t("admin.broadcasts.segmentPicker.title")}</h4>
                        </div>
                        <span className="form-hint">{t("admin.broadcasts.segmentPicker.description")}</span>
                      </div>
                      <div className="broadcast-form-grid">
                        <label className="form-field form-field--wide">
                          <span>{t("admin.broadcasts.segmentPicker.label")}</span>
                          <select
                            value={matchedBroadcastAudiencePreset?.id ?? ""}
                            onChange={(event) =>
                              handleSelectBroadcastAudiencePresetForCampaign(event.target.value)
                            }
                            disabled={
                              !broadcastIsDraft ||
                              broadcastSubmitting ||
                              broadcastAudiencePresetItems.length === 0
                            }
                          >
                            <option value="">{t("admin.broadcasts.segmentPicker.placeholder")}</option>
                            {broadcastAudiencePresetItems.map((item) => (
                              <option key={item.id} value={item.id}>
                                {item.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <div className="status-action-summary status-action-summary--neutral broadcast-campaign-segment">
                          <strong>
                            {matchedBroadcastAudiencePreset
                              ? matchedBroadcastAudiencePreset.name
                              : t("admin.broadcasts.segmentPicker.custom")}
                          </strong>
                          <span>
                            {matchedBroadcastAudiencePreset
                              ? matchedBroadcastAudiencePreset.description ||
                                t("admin.broadcasts.segmentPicker.savedSummary")
                              : t("admin.broadcasts.segmentPicker.customSummary")}
                          </span>
                          <span>{broadcastAudiencePreviewSummary}</span>
                          <span>
                            {broadcastChannels.length > 0
                              ? humanizeBroadcastChannels(broadcastChannels)
                              : t("admin.broadcasts.overview.stats.channelsEmpty")}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="broadcast-form-section">
                      <div className="broadcast-form-section__header">
                        <div>
                          <span className="eyebrow">Блок 1</span>
                          <h4>Основа кампании</h4>
                        </div>
                        <span className="form-hint">Название для команды и пользовательский заголовок сообщения.</span>
                      </div>
                      <div className="broadcast-form-grid">
                        <label className="form-field">
                          <span>Внутреннее название</span>
                          <input
                            value={broadcastName}
                            onChange={(event) => {
                              markBroadcastEditorDirty();
                              setBroadcastName(event.target.value);
                            }}
                            placeholder="Например: Spring promo 2026"
                            required
                            disabled={!broadcastIsDraft || broadcastSubmitting}
                          />
                        </label>
                        <label className="form-field form-field--wide">
                          <span>Заголовок</span>
                          <input
                            value={broadcastTitle}
                            onChange={(event) => {
                              markBroadcastEditorDirty();
                              setBroadcastTitle(event.target.value);
                            }}
                            placeholder="Что увидит пользователь в Telegram и in-app"
                            required
                            disabled={!broadcastIsDraft || broadcastSubmitting}
                          />
                        </label>
                        <label className="form-field">
                          <span>Тип контента</span>
                          <select
                            value={broadcastContentType}
                            onChange={(event) => {
                              markBroadcastEditorDirty();
                              setBroadcastContentType(event.target.value as BroadcastContentType);
                            }}
                            disabled={!broadcastIsDraft || broadcastSubmitting}
                          >
                            <option value="text">Только текст</option>
                            <option value="photo">Текст + фото</option>
                          </select>
                        </label>
                      </div>
                    </div>

                    <div className="broadcast-form-section">
                      <div className="broadcast-form-section__header">
                        <div>
                          <span className="eyebrow">Блок 3</span>
                          <h4>Контент и визуал</h4>
                        </div>
                        <span className="form-hint">Telegram HTML и медиа для обеих клиентских поверхностей.</span>
                      </div>
                      <div className="broadcast-form-grid">
                        {broadcastContentType === "photo" ? (
                          <label className="form-field form-field--wide">
                            <span>Image URL</span>
                            <input
                              value={broadcastImageUrl}
                              onChange={(event) => {
                                markBroadcastEditorDirty();
                                setBroadcastImageUrl(event.target.value);
                              }}
                              placeholder="https://..."
                              required
                              disabled={!broadcastIsDraft || broadcastSubmitting}
                            />
                          </label>
                        ) : null}
                        <label className="form-field form-field--wide">
                          <span>HTML-текст</span>
                          <textarea
                            value={broadcastBodyHtml}
                            onChange={(event) => {
                              markBroadcastEditorDirty();
                              setBroadcastBodyHtml(event.target.value);
                            }}
                            placeholder={"<b>Жирный текст</b>, <a href=\"https://...\">ссылка</a>, переносы строк и Telegram HTML"}
                            rows={10}
                            required
                            disabled={!broadcastIsDraft || broadcastSubmitting}
                          />
                        </label>
                      </div>
                    </div>

                    <div className="broadcast-form-section broadcast-buttons-section">
                      <div className="broadcast-form-section__header">
                        <div>
                          <span className="eyebrow">Блок 4</span>
                          <h4>CTA-кнопки</h4>
                        </div>
                        <button
                          className="ghost-button"
                          type="button"
                          onClick={handleAddBroadcastButton}
                          disabled={!broadcastIsDraft || broadcastSubmitting || broadcastButtonDrafts.length >= 3}
                        >
                          Добавить кнопку
                        </button>
                      </div>
                      {broadcastButtonDrafts.length === 0 ? (
                        <div className="activity-empty">Кнопки опциональны. Поддерживаются до 3 URL-кнопок.</div>
                      ) : (
                        <div className="broadcast-buttons-list">
                          {broadcastButtonDrafts.map((button, index) => (
                            <div key={button.id} className="broadcast-button-editor">
                              <label className="form-field">
                                <span>Текст #{index + 1}</span>
                                <input
                                  value={button.text}
                                  onChange={(event) =>
                                    handleBroadcastButtonChange(button.id, "text", event.target.value)
                                  }
                                  placeholder="Например: Открыть"
                                  disabled={!broadcastIsDraft || broadcastSubmitting}
                                />
                              </label>
                              <label className="form-field form-field--wide">
                                <span>URL</span>
                                <input
                                  value={button.url}
                                  onChange={(event) =>
                                    handleBroadcastButtonChange(button.id, "url", event.target.value)
                                  }
                                  placeholder="https://..."
                                  disabled={!broadcastIsDraft || broadcastSubmitting}
                                />
                              </label>
                              <button
                                className="ghost-button"
                                type="button"
                                onClick={() => handleRemoveBroadcastButton(button.id)}
                                disabled={!broadcastIsDraft || broadcastSubmitting}
                              >
                                Удалить
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="adjustment-form__footer">
                      <span className="form-hint">
                        Черновик сохраняется отдельно. Live estimate считает только текущие каналы и сегмент редактора
                        без записи в БД.
                      </span>
                      <button className="action-button" type="submit" disabled={!broadcastIsDraft || broadcastSubmitting}>
                        {broadcastSubmitting
                          ? "Сохраняем..."
                          : broadcastEditorMode === "edit"
                            ? "Сохранить черновик"
                            : "Создать черновик"}
                      </button>
                    </div>
                  </form>
                </section>
              ) : null}

              <div className="broadcast-preview-grid">
                <article className="detail-section">
                  <div className="detail-section__header">
                    <div>
                      <span className="eyebrow">Telegram preview</span>
                      <h3>Сообщение в Telegram</h3>
                    </div>
                  </div>
                  <div className="broadcast-preview broadcast-preview--telegram">
                    {broadcastContentType === "photo" && broadcastImageUrl ? (
                      <div className="broadcast-preview__media">
                        <img src={broadcastImageUrl} alt="Broadcast preview" />
                      </div>
                    ) : null}
                    <div className="broadcast-preview__body">
                      <strong>{broadcastTitle || "Заголовок рассылки"}</strong>
                      <div
                        className="broadcast-preview__html"
                        dangerouslySetInnerHTML={{
                          __html: renderBroadcastPreviewHtml(
                            broadcastBodyHtml || "HTML-текст рассылки появится здесь после ввода",
                          ),
                        }}
                      />
                    </div>
                    {broadcastButtonDrafts.length > 0 ? (
                      <div className="broadcast-preview__buttons">
                        {broadcastButtonDrafts
                          .filter((button) => button.text.trim() && button.url.trim())
                          .map((button) => (
                            <button key={button.id} className="broadcast-preview__button" type="button">
                              {button.text}
                            </button>
                          ))}
                      </div>
                    ) : null}
                  </div>
                </article>

                <article className="detail-section">
                  <div className="detail-section__header">
                    <div>
                      <span className="eyebrow">In-app preview</span>
                      <h3>Карточка внутри приложения</h3>
                    </div>
                  </div>
                  <div className="broadcast-preview broadcast-preview--app">
                    <div className="broadcast-preview__header">
                      <strong>{broadcastTitle || "Заголовок уведомления"}</strong>
                      <span>{selectedBroadcast ? humanizeBroadcastStatus(selectedBroadcast.status) : "черновик"}</span>
                    </div>
                    {broadcastContentType === "photo" && broadcastImageUrl ? (
                      <div className="broadcast-preview__media broadcast-preview__media--app">
                        <img src={broadcastImageUrl} alt="Broadcast preview" />
                      </div>
                    ) : null}
                    <div
                      className="broadcast-preview__html"
                      dangerouslySetInnerHTML={{
                        __html: renderBroadcastPreviewHtml(
                          broadcastBodyHtml || "Тело уведомления появится после заполнения формы",
                        ),
                      }}
                    />
                    {broadcastButtonDrafts.length > 0 ? (
                      <div className="broadcast-preview__actions">
                        {broadcastButtonDrafts
                          .filter((button) => button.text.trim() && button.url.trim())
                          .map((button) => (
                            <a
                              key={button.id}
                              className="detail-link"
                              href={button.url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {button.text}
                            </a>
                          ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="section-footer">
                    <span className="form-hint">
                      {`${broadcastAudiencePreviewSummary} · ${
                        broadcastChannels.length > 0
                          ? humanizeBroadcastChannels(broadcastChannels)
                          : "каналы не выбраны"
                      }`}
                    </span>
                  </div>
                </article>
              </div>
            </section>

            {showBroadcastRuntime ? (
              <section className="detail-sections-grid detail-sections-grid--runtime">
                <section className="detail-section detail-section--action">
                <div className="detail-section__header detail-section__header--stacked">
                  <div>
                    <span className="eyebrow">Runtime</span>
                    <h3>Запуск и управление кампанией</h3>
                  </div>
                  <span className="form-hint">
                    Автообновление отключено. Боевые действия доступны только superuser. Все даты и время для
                    расписания считаются по Москве.
                  </span>
                </div>

                <form
                  className="adjustment-form adjustment-form--runtime"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void submitBroadcastRuntimeAction("schedule");
                  }}
                >
                  <label className="form-field form-field--wide">
                    <span>Комментарий runtime</span>
                    <textarea
                      value={broadcastRuntimeComment}
                      onChange={(event) => setBroadcastRuntimeComment(event.target.value)}
                      placeholder="Почему запускаем, ставим на паузу или отменяем кампанию"
                      rows={3}
                      disabled={!canManageBroadcastRuntime || broadcastRuntimeSubmitting}
                    />
                  </label>
                  <label className="form-field">
                    <span>Дата и время запуска</span>
                    <input
                      type="datetime-local"
                      value={broadcastScheduleAtInput}
                      onChange={(event) => setBroadcastScheduleAtInput(event.target.value)}
                      disabled={!canManageBroadcastRuntime || broadcastRuntimeSubmitting}
                    />
                  </label>
                  <div className="adjustment-form__footer">
                    <span className="form-hint">
                      {selectedBroadcast?.latest_run
                        ? `${humanizeBroadcastRunType(selectedBroadcast.latest_run.run_type)} · ${humanizeBroadcastRunStatus(
                            selectedBroadcast.latest_run.status,
                          )}`
                        : "У кампании еще нет боевого запуска."}
                    </span>
                    <div className="action-cluster">
                      {selectedBroadcast?.status === "draft" ? (
                        <>
                          <button
                            className="ghost-button"
                            type="button"
                            onClick={() => void submitBroadcastRuntimeAction("send-now")}
                            disabled={!canManageBroadcastRuntime || broadcastRuntimeSubmitting}
                          >
                            Отправить сейчас
                          </button>
                          <button
                            className="action-button"
                            type="submit"
                            disabled={!canManageBroadcastRuntime || broadcastRuntimeSubmitting}
                          >
                            Поставить в расписание
                          </button>
                          <button
                            className="ghost-button ghost-button--danger"
                            type="button"
                            onClick={() => void handleDeleteBroadcastDraft()}
                            disabled={broadcastRuntimeSubmitting || selectedBroadcastId === null}
                          >
                            Удалить черновик
                          </button>
                        </>
                      ) : null}
                      {selectedBroadcast?.status === "scheduled" || selectedBroadcast?.status === "running" ? (
                        <>
                          <button
                            className="ghost-button"
                            type="button"
                            onClick={() => void submitBroadcastRuntimeAction("pause")}
                            disabled={!canManageBroadcastRuntime || broadcastRuntimeSubmitting}
                          >
                            Пауза
                          </button>
                          <button
                            className="ghost-button ghost-button--danger"
                            type="button"
                            onClick={() => void submitBroadcastRuntimeAction("cancel")}
                            disabled={!canManageBroadcastRuntime || broadcastRuntimeSubmitting}
                          >
                            Отменить кампанию
                          </button>
                        </>
                      ) : null}
                      {selectedBroadcast?.status === "paused" ? (
                        <>
                          <button
                            className="ghost-button"
                            type="button"
                            onClick={() => void submitBroadcastRuntimeAction("resume")}
                            disabled={!canManageBroadcastRuntime || broadcastRuntimeSubmitting}
                          >
                            Возобновить
                          </button>
                          <button
                            className="ghost-button ghost-button--danger"
                            type="button"
                            onClick={() => void submitBroadcastRuntimeAction("cancel")}
                            disabled={!canManageBroadcastRuntime || broadcastRuntimeSubmitting}
                          >
                            Отменить кампанию
                          </button>
                        </>
                      ) : null}
                    </div>
                  </div>
                </form>
                </section>
              </section>
            ) : null}

          </div>
        </section>
      ) : (
        <section className="search-shell">
          <aside className="search-column">
            <section className="search-panel">
              <span className="eyebrow">Очередь выводов</span>
              <h2>Новые и в работе</h2>
              <p className="queue-panel__copy">
                Здесь живут только активные заявки. При отклонении резерв вернется на баланс
                пользователя, при выплате заявка уйдет из очереди.
              </p>
              <div className="queue-summary">
                <article className="queue-summary__item">
                  <span>Всего в очереди</span>
                  <strong>{withdrawalTotal}</strong>
                </article>
                <article className="queue-summary__item">
                  <span>Новые</span>
                  <strong>{withdrawalStats.newCount}</strong>
                </article>
                <article className="queue-summary__item">
                  <span>В работе</span>
                  <strong>{withdrawalStats.inProgressCount}</strong>
                </article>
              </div>
            </section>

            <div className="results-list">
              {withdrawalsLoading ? (
                <div className="empty-state">Загружаем очередь выводов...</div>
              ) : withdrawalItems.length === 0 ? (
                <div className="empty-state">Очередь пуста. Новых заявок сейчас нет.</div>
              ) : (
                withdrawalItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={
                      selectedWithdrawalId === item.id
                        ? "result-card result-card--active result-card--withdrawal"
                        : "result-card result-card--withdrawal"
                    }
                    onClick={() => setSelectedWithdrawalId(item.id)}
                  >
                    <div className="result-card__top">
                      <strong>
                        #{item.id} · {formatMoney(item.amount)}
                      </strong>
                      <span className={`status-pill status-pill--${item.status}`}>
                        {humanizeWithdrawalStatus(item.status)}
                      </span>
                    </div>
                    <span>
                      {item.account_display_name ||
                        item.account_username ||
                        item.account_email ||
                        item.account_id}
                    </span>
                    <span>
                      {humanizeWithdrawalDestinationType(item.destination_type)}:{" "}
                      {item.destination_value}
                    </span>
                    <span>Создан: {formatDate(item.created_at)}</span>
                  </button>
                ))
              )}
            </div>
          </aside>

          <div className="detail-column">
            {withdrawalsLoading ? (
              <div className="detail-skeleton">Загружаем детали заявки...</div>
            ) : null}
            {!withdrawalsLoading && !selectedWithdrawal ? (
              <div className="detail-skeleton">Выбери заявку на вывод из очереди.</div>
            ) : null}
            {!withdrawalsLoading && selectedWithdrawal ? (
              <>
                <section className="detail-header">
                  <div>
                    <span className="eyebrow">Заявка на вывод</span>
                    <h2>
                      {selectedWithdrawal.account_display_name ||
                        selectedWithdrawal.account_username ||
                        selectedWithdrawal.account_email ||
                        selectedWithdrawal.account_id}
                    </h2>
                    <p>
                      {selectedWithdrawal.account_email || "Без email"} ·{" "}
                      {selectedWithdrawal.account_telegram_id
                        ? `Telegram ${selectedWithdrawal.account_telegram_id}`
                        : "Telegram не привязан"}
                    </p>
                  </div>
                  <span className={`status-pill status-pill--${selectedWithdrawal.status}`}>
                    {humanizeWithdrawalStatus(selectedWithdrawal.status)}
                  </span>
                </section>

                <section className="detail-facts-grid">
                  <DetailFact label="Сумма" value={formatMoney(selectedWithdrawal.amount)} />
                  <DetailFact
                    label="Канал"
                    value={humanizeWithdrawalDestinationType(selectedWithdrawal.destination_type)}
                  />
                  <DetailFact
                    label="Статус аккаунта"
                    value={humanizeAccountStatus(selectedWithdrawal.account_status)}
                  />
                  <DetailFact label="Создан" value={formatDate(selectedWithdrawal.created_at)} />
                </section>

                <section className="detail-sections-grid">
                  <article className="detail-section">
                    <span className="eyebrow">Реквизиты и аккаунт</span>
                    <div className="detail-kv">
                      <div>
                        <span>Назначение</span>
                        <strong>
                          {humanizeWithdrawalDestinationType(selectedWithdrawal.destination_type)}
                        </strong>
                      </div>
                      <div>
                        <span>Реквизиты</span>
                        <strong>{selectedWithdrawal.destination_value}</strong>
                      </div>
                      <div>
                        <span>Username</span>
                        <strong>{selectedWithdrawal.account_username || "-"}</strong>
                      </div>
                      <div>
                        <span>Статус аккаунта</span>
                        <strong>{humanizeAccountStatus(selectedWithdrawal.account_status)}</strong>
                      </div>
                    </div>
                    <button
                      className="ghost-button detail-inline-button"
                      type="button"
                      onClick={() => void handleOpenWithdrawalAccount(selectedWithdrawal.account_id)}
                    >
                      Открыть карточку пользователя
                    </button>
                  </article>

                  <article className="detail-section">
                    <span className="eyebrow">Комментарии</span>
                    <div className="note-card">
                      <strong>Комментарий пользователя</strong>
                      <p>{selectedWithdrawal.user_comment || "Пользователь ничего не указал."}</p>
                    </div>
                    {selectedWithdrawal.admin_comment ? (
                      <div className="note-card note-card--secondary">
                        <strong>Текущий admin comment</strong>
                        <p>{selectedWithdrawal.admin_comment}</p>
                      </div>
                    ) : null}
                  </article>
                </section>

                <section className="detail-section detail-section--action">
                  <span className="eyebrow">Обработка заявки</span>
                  <div className="detail-section__intro">
                    <h3>Комментарий обязателен для каждого действия</h3>
                    <p>
                      Перевод в работу просто фиксирует ownership состояния. Отклонение делает
                      compensating release записи в ledger, а выплата окончательно закрывает заявку.
                    </p>
                  </div>
                  <div className="adjustment-form">
                    <div className="form-field">
                      <span>Текущее состояние</span>
                      <div className="status-action-summary">
                        <strong>{humanizeWithdrawalStatus(selectedWithdrawal.status)}</strong>
                        <small>
                          {selectedWithdrawal.status === "new"
                            ? "Новая заявка: резерв уже удержан, дальше ее можно взять в работу или отклонить."
                            : "Заявка уже в работе: после фактической выплаты отметь ее как выплаченную или отклони с возвратом резерва."}
                        </small>
                      </div>
                    </div>
                    <label className="form-field form-field--wide">
                      <span>Комментарий</span>
                      <textarea
                        value={withdrawalComment}
                        onChange={(event) => setWithdrawalComment(event.target.value)}
                        placeholder="Что проверили, кто выплачивает или почему отклоняем"
                        rows={4}
                        required
                      />
                    </label>
                    <div className="adjustment-form__footer">
                      <span className="form-hint">
                        Комментарий попадет в audit trail. При отклонении {formatMoney(selectedWithdrawal.amount)}{" "}
                        вернутся на баланс пользователя.
                      </span>
                      <div className="action-cluster">
                        {selectedWithdrawal.status === "new" ? (
                          <button
                            className="action-button"
                            type="button"
                            disabled={withdrawalSubmitting}
                            onClick={() => void handleWithdrawalStatusChange("in_progress")}
                          >
                            {withdrawalSubmitting ? "Сохраняем..." : "Взять в работу"}
                          </button>
                        ) : null}
                        {selectedWithdrawal.status === "in_progress" ? (
                          <button
                            className="action-button"
                            type="button"
                            disabled={withdrawalSubmitting}
                            onClick={() => void handleWithdrawalStatusChange("paid")}
                          >
                            {withdrawalSubmitting ? "Сохраняем..." : "Отметить выплаченным"}
                          </button>
                        ) : null}
                        <button
                          className="action-button action-button--danger"
                          type="button"
                          disabled={withdrawalSubmitting}
                          onClick={() => void handleWithdrawalStatusChange("rejected")}
                        >
                          {withdrawalSubmitting ? "Сохраняем..." : "Отклонить и вернуть резерв"}
                        </button>
                      </div>
                    </div>
                  </div>
                </section>
              </>
            ) : null}
          </div>
        </section>
      )}
    </main>
  );
}
