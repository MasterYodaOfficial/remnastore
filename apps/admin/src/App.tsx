import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

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
  pending_withdrawals: number;
  pending_payments: number;
  blocked_accounts: number;
  new_accounts_last_7d: number;
  total_wallet_balance: number;
  total_referral_earnings: number;
  pending_withdrawals_amount: number;
  paid_withdrawals_amount_last_30d: number;
  successful_payments_last_30d: number;
  successful_payments_amount_last_30d: number;
  wallet_topups_amount_last_30d: number;
  direct_plan_revenue_last_30d: number;
};

type AdminAuthResponse = {
  access_token: string;
  token_type: string;
  admin: AdminProfile;
};

type DashboardCardProps = {
  label: string;
  value: string | number;
  hint: string;
};

type AdminAccountSearchItem = {
  id: string;
  email: string | null;
  display_name: string | null;
  telegram_id: number | null;
  username: string | null;
  status: "active" | "blocked";
  balance: number;
  subscription_status: string | null;
  subscription_expires_at: string | null;
  created_at: string;
};

type AdminAccountSearchResponse = {
  items: AdminAccountSearchItem[];
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
  segment: "all" | "active" | "with_telegram" | "paid" | "expired";
  exclude_blocked: boolean;
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

type AdminBroadcastRunDetailResponse = {
  run: AdminBroadcastRun;
  deliveries: AdminBroadcastRunDelivery[];
  total_deliveries: number;
  limit: number;
  offset: number;
};

type BroadcastButtonDraft = {
  id: string;
  text: string;
  url: string;
};

type BroadcastAudienceSegment = AdminBroadcastAudience["segment"];
type BroadcastContentType = AdminBroadcast["content_type"];
type BroadcastStatus = AdminBroadcast["status"];
type BroadcastChannel = AdminBroadcast["channels"][number];
type BroadcastRunStatus = AdminBroadcastRun["status"];
type BroadcastRunType = AdminBroadcastRun["run_type"];

type AdminView = "dashboard" | "accounts" | "broadcasts" | "withdrawals";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") || "http://localhost:8000";
const TOKEN_KEY = "remnastore_admin_token";
const ADMIN_LEDGER_HISTORY_PAGE_SIZE = 20;
const BROADCAST_AUDIENCE_SEGMENTS = ["all", "active", "with_telegram", "paid", "expired"] as const;
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

type LedgerEntryFilterOption = (typeof LEDGER_ENTRY_FILTER_OPTIONS)[number];

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
    return "Не было";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Некорректная дата";
  }

  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatDateMoscow(value: string | null): string {
  if (!value) {
    return "Не было";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Некорректная дата";
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
    const parsed = JSON.parse(text) as { detail?: string };
    return parsed.detail || text;
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

  return (await response.json()) as T;
}

function humanizeAccountStatus(status: string): string {
  return status === "blocked" ? "Полная блокировка" : "Активен";
}

function humanizePaymentStatus(status: string): string {
  switch (status) {
    case "created":
      return "Создан";
    case "pending":
      return "Ожидает";
    case "requires_action":
      return "Ждет действия";
    case "succeeded":
      return "Успешен";
    case "failed":
      return "Ошибка";
    case "cancelled":
      return "Отменен";
    case "expired":
      return "Истек";
    default:
      return status;
  }
}

function humanizePaymentFlow(flow: string): string {
  return flow === "wallet_topup" ? "Пополнение" : "Покупка тарифа";
}

function humanizeLedgerType(entryType: string): string {
  switch (entryType) {
    case "topup_manual":
      return "Ручное пополнение";
    case "topup_payment":
      return "Пополнение по платежу";
    case "subscription_debit":
      return "Оплата подписки";
    case "referral_reward":
      return "Реферальное начисление";
    case "withdrawal_reserve":
      return "Резерв на вывод";
    case "withdrawal_release":
      return "Возврат резерва";
    case "withdrawal_payout":
      return "Выплата вывода";
    case "promo_credit":
      return "Промо-зачисление";
    case "refund":
      return "Возврат";
    case "admin_credit":
      return "Зачисление админом";
    case "admin_debit":
      return "Списание админом";
    case "merge_credit":
      return "Баланс перенесен в аккаунт";
    case "merge_debit":
      return "Баланс перенесен из аккаунта";
    default:
      return entryType;
  }
}

function humanizeLedgerEntryFilter(entryType: LedgerEntryFilterOption): string {
  if (entryType === "all") {
    return "Все типы";
  }
  return humanizeLedgerType(entryType);
}

function describeLedgerEntryContext(entry: AdminAccountLedgerEntry): string {
  const context: string[] = [];

  if (entry.reference_type || entry.reference_id) {
    context.push(`${entry.reference_type || "reference"} ${entry.reference_id || ""}`.trim());
  }
  if (entry.created_by_admin_id) {
    context.push("инициатор: admin");
  } else if (entry.created_by_account_id) {
    context.push("инициатор: account");
  }
  if (entry.idempotency_key) {
    context.push(`key ${entry.idempotency_key}`);
  }

  return context.join(" · ");
}

function humanizeWithdrawalStatus(status: string): string {
  switch (status) {
    case "new":
      return "Новый";
    case "in_progress":
      return "В работе";
    case "paid":
      return "Выплачен";
    case "rejected":
      return "Отклонен";
    case "cancelled":
      return "Отменен";
    default:
      return status;
  }
}

function humanizeWithdrawalDestinationType(destinationType: string): string {
  switch (destinationType) {
    case "card":
      return "Карта";
    case "sbp":
      return "СБП";
    default:
      return destinationType;
  }
}

function humanizeBroadcastStatus(status: BroadcastStatus): string {
  switch (status) {
    case "draft":
      return "Черновик";
    case "scheduled":
      return "Запланирована";
    case "running":
      return "В работе";
    case "paused":
      return "Пауза";
    case "completed":
      return "Завершена";
    case "failed":
      return "Ошибка";
    case "cancelled":
      return "Отменена";
    default:
      return status;
  }
}

function humanizeBroadcastAudienceSegment(segment: BroadcastAudienceSegment): string {
  switch (segment) {
    case "all":
      return "Все аккаунты";
    case "active":
      return "Активные аккаунты";
    case "with_telegram":
      return "Только с Telegram";
    case "paid":
      return "Только платившие";
    case "expired":
      return "С истекшей подпиской";
    default:
      return segment;
  }
}

function humanizeBroadcastChannel(channel: BroadcastChannel): string {
  return channel === "telegram" ? "Telegram" : "In-app";
}

function humanizeBroadcastChannels(channels: BroadcastChannel[]): string {
  return channels.map((channel) => humanizeBroadcastChannel(channel)).join(" + ");
}

function formatAccountIdentity(account: {
  account_id?: string;
  id?: string;
  display_name?: string | null;
  username?: string | null;
  email?: string | null;
}): string {
  return account.display_name || account.username || account.email || account.account_id || account.id || "Безымянный аккаунт";
}

function formatRewardRate(value: number): string {
  return `${new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 2,
  }).format(value)}%`;
}

function humanizeReferralRewardStatus(status: AdminReferralChainItem["reward_status"]): string {
  return status === "rewarded" ? "Награда начислена" : "Ждет оплату";
}

function humanizeBroadcastTestSendStatus(status: AdminBroadcastTestSendTargetResult["status"]): string {
  switch (status) {
    case "sent":
      return "Отправлено";
    case "partial":
      return "Частично";
    case "failed":
      return "Ошибка";
    case "skipped":
      return "Пропущено";
    default:
      return status;
  }
}

function humanizeBroadcastRunType(runType: BroadcastRunType): string {
  return runType === "scheduled" ? "По расписанию" : "Сразу";
}

function humanizeBroadcastRunStatus(status: BroadcastRunStatus): string {
  switch (status) {
    case "running":
      return "В работе";
    case "paused":
      return "Пауза";
    case "completed":
      return "Завершен";
    case "failed":
      return "Ошибка";
    case "cancelled":
      return "Отменен";
    default:
      return status;
  }
}

function humanizeBroadcastDeliveryStatus(status: AdminBroadcastRunDelivery["status"]): string {
  switch (status) {
    case "pending":
      return "Ожидает";
    case "delivered":
      return "Доставлено";
    case "failed":
      return "Ошибка";
    case "skipped":
      return "Пропущено";
    default:
      return status;
  }
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

function DashboardCard({ label, value, hint }: DashboardCardProps) {
  return (
    <article className="metric-card">
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      <span className="metric-hint">{hint}</span>
    </article>
  );
}

function DetailFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
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
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<AdminAccountSearchItem[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<AdminAccountDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [ledgerHistoryItems, setLedgerHistoryItems] = useState<AdminAccountLedgerEntry[]>([]);
  const [ledgerHistoryTotal, setLedgerHistoryTotal] = useState(0);
  const [ledgerHistoryFilter, setLedgerHistoryFilter] = useState<LedgerEntryFilterOption>("all");
  const [ledgerHistoryLoading, setLedgerHistoryLoading] = useState(false);
  const [ledgerHistoryLoadingMore, setLedgerHistoryLoadingMore] = useState(false);
  const [subscriptionPlans, setSubscriptionPlans] = useState<AdminSubscriptionPlan[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);
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
  const [selectedBroadcast, setSelectedBroadcast] = useState<AdminBroadcast | null>(null);
  const [broadcastsLoading, setBroadcastsLoading] = useState(false);
  const [broadcastSubmitting, setBroadcastSubmitting] = useState(false);
  const [broadcastEstimate, setBroadcastEstimate] = useState<AdminBroadcastEstimate | null>(null);
  const [broadcastEstimateLoading, setBroadcastEstimateLoading] = useState(false);
  const [broadcastEstimateError, setBroadcastEstimateError] = useState<string | null>(null);
  const [broadcastTestEmailsInput, setBroadcastTestEmailsInput] = useState("");
  const [broadcastTestTelegramIdsInput, setBroadcastTestTelegramIdsInput] = useState("");
  const [broadcastTestComment, setBroadcastTestComment] = useState("");
  const [broadcastTestSubmitting, setBroadcastTestSubmitting] = useState(false);
  const [broadcastTestResult, setBroadcastTestResult] = useState<AdminBroadcastTestSendResponse | null>(null);
  const [broadcastRuntimeComment, setBroadcastRuntimeComment] = useState("");
  const [broadcastScheduleAtInput, setBroadcastScheduleAtInput] = useState("");
  const [broadcastRuntimeSubmitting, setBroadcastRuntimeSubmitting] = useState(false);
  const [broadcastRunItems, setBroadcastRunItems] = useState<AdminBroadcastRun[]>([]);
  const [broadcastRunTotal, setBroadcastRunTotal] = useState(0);
  const [selectedBroadcastRunId, setSelectedBroadcastRunId] = useState<number | null>(null);
  const [selectedBroadcastRun, setSelectedBroadcastRun] = useState<AdminBroadcastRun | null>(null);
  const [broadcastRunsLoading, setBroadcastRunsLoading] = useState(false);
  const [broadcastRunDetailLoading, setBroadcastRunDetailLoading] = useState(false);
  const [broadcastRunDeliveries, setBroadcastRunDeliveries] = useState<AdminBroadcastRunDelivery[]>([]);
  const [broadcastRunDeliveriesTotal, setBroadcastRunDeliveriesTotal] = useState(0);
  const [broadcastRunStatusFilter, setBroadcastRunStatusFilter] = useState<BroadcastRunStatus | "all">("all");
  const [broadcastRunTypeFilter, setBroadcastRunTypeFilter] = useState<BroadcastRunType | "all">("all");
  const [broadcastRunChannelFilter, setBroadcastRunChannelFilter] = useState<BroadcastChannel | "all">("all");
  const [broadcastName, setBroadcastName] = useState("");
  const [broadcastTitle, setBroadcastTitle] = useState("");
  const [broadcastBodyHtml, setBroadcastBodyHtml] = useState("");
  const [broadcastContentType, setBroadcastContentType] = useState<BroadcastContentType>("text");
  const [broadcastImageUrl, setBroadcastImageUrl] = useState("");
  const [broadcastButtonDrafts, setBroadcastButtonDrafts] = useState<BroadcastButtonDraft[]>([]);
  const [broadcastAudienceSegment, setBroadcastAudienceSegment] = useState<BroadcastAudienceSegment>("all");
  const [broadcastAudienceExcludeBlocked, setBroadcastAudienceExcludeBlocked] = useState(true);
  const [broadcastSendInApp, setBroadcastSendInApp] = useState(true);
  const [broadcastSendTelegram, setBroadcastSendTelegram] = useState(false);
  const [broadcastEditorDirty, setBroadcastEditorDirty] = useState(false);
  const [broadcastFormSourceId, setBroadcastFormSourceId] = useState<number | null>(null);
  const [broadcastWorkspaceRefreshing, setBroadcastWorkspaceRefreshing] = useState(false);

  const cards = useMemo(() => {
    if (!summary) {
      return [];
    }
    return [
      {
        label: "Пользователи",
        value: summary.total_accounts,
        hint: "всего локальных аккаунтов",
      },
      {
        label: "Активные подписки",
        value: summary.active_subscriptions,
        hint: "текущий рабочий пул",
      },
      {
        label: "Выводы",
        value: summary.pending_withdrawals,
        hint: "очередь к обработке",
      },
      {
        label: "Платежи",
        value: summary.pending_payments,
        hint: "незавершенные попытки",
      },
    ];
  }, [summary]);
  const financeCards = useMemo(() => {
    if (!summary) {
      return [];
    }
    return [
      {
        label: "Баланс кошельков",
        value: formatMoney(summary.total_wallet_balance),
        hint: "суммарный snapshot по аккаунтам",
      },
      {
        label: "Резерв выводов",
        value: formatMoney(summary.pending_withdrawals_amount),
        hint: "сейчас висит в pending и in_progress",
      },
      {
        label: "Платежи 30д",
        value: formatMoney(summary.successful_payments_amount_last_30d),
        hint: `${summary.successful_payments_last_30d} успешных оплат за 30 дней`,
      },
      {
        label: "Выводы 30д",
        value: formatMoney(summary.paid_withdrawals_amount_last_30d),
        hint: "фактически выплаченные заявки",
      },
    ];
  }, [summary]);
  const activityCards = useMemo(() => {
    if (!summary) {
      return [];
    }
    return [
      {
        label: "Новые аккаунты 7д",
        value: summary.new_accounts_last_7d,
        hint: "свежий приток пользователей",
      },
      {
        label: "Заблокированные",
        value: summary.blocked_accounts,
        hint: "аккаунты на полном стопе",
      },
      {
        label: "Пополнения 30д",
        value: formatMoney(summary.wallet_topups_amount_last_30d),
        hint: "wallet_topup через провайдеров",
      },
      {
        label: "Покупки тарифов 30д",
        value: formatMoney(summary.direct_plan_revenue_last_30d),
        hint: "direct plan purchase",
      },
      {
        label: "Реферальные начисления",
        value: formatMoney(summary.total_referral_earnings),
        hint: "накоплено по всем аккаунтам",
      },
    ];
  }, [summary]);

  const selectedGrantPlan = useMemo(
    () => subscriptionPlans.find((plan) => plan.code === subscriptionGrantPlanCode) || null,
    [subscriptionGrantPlanCode, subscriptionPlans],
  );
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
  const hasMoreLedgerHistory = ledgerHistoryItems.length < ledgerHistoryTotal;
  const broadcastEditorMode = selectedBroadcastId ? "edit" : "create";
  const broadcastIsDraft = !selectedBroadcast || selectedBroadcast.status === "draft";
  const canManageBroadcastRuntime = Boolean(profile?.is_superuser && selectedBroadcastId !== null);
  const broadcastChannels = useMemo(() => {
    const channels: BroadcastChannel[] = [];
    if (broadcastSendInApp) {
      channels.push("in_app");
    }
    if (broadcastSendTelegram) {
      channels.push("telegram");
    }
    return channels;
  }, [broadcastSendInApp, broadcastSendTelegram]);
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

  function resetBroadcastEditorForm() {
    setBroadcastName("");
    setBroadcastTitle("");
    setBroadcastBodyHtml("");
    setBroadcastContentType("text");
    setBroadcastImageUrl("");
    setBroadcastButtonDrafts([]);
    setBroadcastAudienceSegment("all");
    setBroadcastAudienceExcludeBlocked(true);
    setBroadcastSendInApp(true);
    setBroadcastSendTelegram(false);
    setBroadcastEditorDirty(false);
    setBroadcastFormSourceId(null);
  }

  function hydrateBroadcastEditorForm(broadcast: AdminBroadcast) {
    setBroadcastName(broadcast.name);
    setBroadcastTitle(broadcast.title);
    setBroadcastBodyHtml(broadcast.body_html);
    setBroadcastContentType(broadcast.content_type);
    setBroadcastImageUrl(broadcast.image_url || "");
    setBroadcastButtonDrafts(broadcast.buttons.map((button) => createBroadcastButtonDraft(button)));
    setBroadcastAudienceSegment(broadcast.audience.segment);
    setBroadcastAudienceExcludeBlocked(broadcast.audience.exclude_blocked);
    setBroadcastSendInApp(broadcast.channels.includes("in_app"));
    setBroadcastSendTelegram(broadcast.channels.includes("telegram"));
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

  const loadSubscriptionPlans = useCallback(
    async (activeToken: string): Promise<AdminSubscriptionPlan[]> => {
      setPlansLoading(true);
      try {
        const plans = await adminFetch<AdminSubscriptionPlan[]>(
          "/api/v1/admin/accounts/subscription-plans",
          activeToken,
        );
        setSubscriptionPlans(plans);
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
        const params = new URLSearchParams({
          limit: "20",
          offset: "0",
        });
        if (broadcastRunStatusFilter !== "all") {
          params.set("status", broadcastRunStatusFilter);
        }
        if (broadcastRunTypeFilter !== "all") {
          params.set("run_type", broadcastRunTypeFilter);
        }
        if (broadcastRunChannelFilter !== "all") {
          params.set("channel", broadcastRunChannelFilter);
        }

        const response = await adminFetch<AdminBroadcastRunListResponse>(
          `/api/v1/admin/broadcasts/runs?${params.toString()}`,
          activeToken,
        );
        setBroadcastRunItems(response.items);
        setBroadcastRunTotal(response.total);
        setSelectedBroadcastRunId((currentSelection) =>
          response.items.some((item) => item.id === currentSelection)
            ? currentSelection
            : (response.items[0]?.id ?? null),
        );
        return response.items;
      } catch (fetchError) {
        setBroadcastRunItems([]);
        setBroadcastRunTotal(0);
        setSelectedBroadcastRunId(null);
        setSelectedBroadcastRun(null);
        setBroadcastRunDeliveries([]);
        setBroadcastRunDeliveriesTotal(0);
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить журнал запусков");
        return [];
      } finally {
        setBroadcastRunsLoading(false);
      }
    },
    [broadcastRunChannelFilter, broadcastRunStatusFilter, broadcastRunTypeFilter],
  );

  const loadBroadcastRunDetail = useCallback(
    async (runId: number, activeToken: string): Promise<AdminBroadcastRun | null> => {
      setBroadcastRunDetailLoading(true);
      try {
        const response = await adminFetch<AdminBroadcastRunDetailResponse>(
          `/api/v1/admin/broadcasts/runs/${runId}?limit=50&offset=0`,
          activeToken,
        );
        setSelectedBroadcastRun(response.run);
        setBroadcastRunDeliveries(response.deliveries);
        setBroadcastRunDeliveriesTotal(response.total_deliveries);
        return response.run;
      } catch (fetchError) {
        setSelectedBroadcastRun(null);
        setBroadcastRunDeliveries([]);
        setBroadcastRunDeliveriesTotal(0);
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить run-detail");
        return null;
      } finally {
        setBroadcastRunDetailLoading(false);
      }
    },
    [],
  );

  function updateSearchResultSnapshot(account: Pick<AdminAccountDetail, "id" | "balance" | "status" | "subscription_status" | "subscription_expires_at">) {
    setSearchResults((items) =>
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
      setSearchResults([]);
      setSelectedAccount(null);
      setLedgerHistoryItems([]);
      setLedgerHistoryTotal(0);
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
      setBroadcastSendInApp(true);
      setBroadcastSendTelegram(false);
      setBroadcastEditorDirty(false);
      setBroadcastFormSourceId(null);
      setBroadcastWorkspaceRefreshing(false);
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
        setSearchResults([]);
        setSelectedAccount(null);
        setLedgerHistoryItems([]);
        setLedgerHistoryTotal(0);
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
    if (!token || activeView !== "accounts" || subscriptionPlans.length > 0) {
      return;
    }

    void loadSubscriptionPlans(token);
  }, [activeView, loadSubscriptionPlans, subscriptionPlans.length, token]);

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
    void loadBroadcastRuns(token);
  }, [activeView, loadBroadcastRuns, loadBroadcasts, token]);

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
    if (!token || activeView !== "broadcasts") {
      return;
    }
    if (selectedBroadcastRunId === null) {
      setSelectedBroadcastRun(null);
      setBroadcastRunDeliveries([]);
      setBroadcastRunDeliveriesTotal(0);
      return;
    }

    void loadBroadcastRunDetail(selectedBroadcastRunId, token);
  }, [activeView, loadBroadcastRunDetail, selectedBroadcastRunId, token]);

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
  }, [selectedAccountId]);

  useEffect(() => {
    setWithdrawalComment("");
  }, [selectedWithdrawalId]);

  useEffect(() => {
    if (!selectedBroadcast) {
      setBroadcastEstimate(null);
      setBroadcastEstimateError(null);
      setBroadcastTestResult(null);
      setBroadcastRuntimeComment("");
      setBroadcastScheduleAtInput("");
      resetBroadcastEditorForm();
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
    setBroadcastTestResult(null);
    setBroadcastRuntimeComment("");
    setBroadcastScheduleAtInput(toMoscowDateTimeInputValue(selectedBroadcast.scheduled_at));
  }, [broadcastEditorDirty, broadcastFormSourceId, selectedBroadcast]);

  useEffect(() => {
    if (!token || activeView !== "broadcasts") {
      return;
    }

    if (broadcastChannels.length === 0) {
      setBroadcastEstimate(null);
      setBroadcastEstimateLoading(false);
      setBroadcastEstimateError("Выбери хотя бы один канал доставки, чтобы посчитать аудиторию.");
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        setBroadcastEstimateLoading(true);
        try {
          const estimate = await adminFetch<AdminBroadcastEstimate>(
            "/api/v1/admin/broadcasts/estimate",
            token,
            {
              method: "POST",
              body: JSON.stringify({
                channels: broadcastChannels,
                audience: {
                  segment: broadcastAudienceSegment,
                  exclude_blocked: broadcastAudienceExcludeBlocked,
                },
              }),
            },
          );
          if (cancelled) {
            return;
          }
          setBroadcastEstimate(estimate);
          setBroadcastEstimateError(null);
        } catch (estimateError) {
          if (cancelled) {
            return;
          }
          setBroadcastEstimateError(
            estimateError instanceof Error ? estimateError.message : "Не удалось пересчитать аудиторию",
          );
        } finally {
          if (!cancelled) {
            setBroadcastEstimateLoading(false);
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
    broadcastAudienceSegment,
    broadcastChannels,
    token,
  ]);

  useEffect(() => {
    if (!token || activeView !== "broadcasts") {
      return;
    }

    void loadBroadcastRuns(token);
  }, [activeView, broadcastRunChannelFilter, broadcastRunStatusFilter, broadcastRunTypeFilter, loadBroadcastRuns, token]);

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
    setSearchResults([]);
    setSelectedAccount(null);
    setLedgerHistoryItems([]);
    setLedgerHistoryTotal(0);
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
    setBroadcastSendInApp(true);
    setBroadcastSendTelegram(false);
    setBroadcastEditorDirty(false);
    setBroadcastFormSourceId(null);
    setBroadcastWorkspaceRefreshing(false);
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
      if (activeView === "accounts" && subscriptionPlans.length === 0) {
        await loadSubscriptionPlans(token);
      }
      if (activeView === "accounts" && selectedAccountId) {
        await loadLedgerHistory(selectedAccountId, token, {
          offset: 0,
          append: false,
          entryType: ledgerHistoryFilter,
        });
      }
      if (activeView === "withdrawals") {
        await loadWithdrawals(token);
      }
      if (activeView === "broadcasts") {
        await loadBroadcasts(token);
        await loadBroadcastRuns(token);
      }
      if (selectedAccountId) {
        await loadAccountDetail(selectedAccountId, token);
      }
      if (activeView === "broadcasts" && selectedBroadcastId !== null) {
        await loadBroadcastDetail(selectedBroadcastId, token);
      }
      if (activeView === "broadcasts" && selectedBroadcastRunId !== null) {
        await loadBroadcastRunDetail(selectedBroadcastRunId, token);
      }
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Не удалось обновить данные");
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !searchQuery.trim()) {
      return;
    }

    setSearching(true);
    setError(null);
    setNotice(null);
    setSelectedAccount(null);
    try {
      const response = await adminFetch<AdminAccountSearchResponse>(
        `/api/v1/admin/accounts/search?query=${encodeURIComponent(searchQuery.trim())}`,
        token,
      );
      setSearchResults(response.items);
      if (response.items[0]) {
        await loadAccountDetail(response.items[0].id, token);
      } else {
        setSelectedAccountId(null);
      }
    } catch (searchError) {
      setSearchResults([]);
      setSelectedAccountId(null);
      setError(searchError instanceof Error ? searchError.message : "Не удалось выполнить поиск");
    } finally {
      setSearching(false);
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
    setSelectedBroadcastId(broadcastId);
    setError(null);
    setNotice(null);
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

  function parseBroadcastTargetText(value: string): string[] {
    return value
      .split(/[\n,;]+/g)
      .map((item) => item.trim())
      .filter(Boolean);
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
        audience: {
          segment: broadcastAudienceSegment,
          exclude_blocked: broadcastAudienceExcludeBlocked,
        },
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

  async function handleBroadcastTestSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || selectedBroadcastId === null) {
      setError("Сначала сохрани черновик рассылки, затем запускай test send");
      return;
    }
    if (!broadcastIsDraft) {
      setError("Test send доступен только для черновика рассылки");
      return;
    }
    if (broadcastEditorDirty) {
      setError("Сначала сохрани черновик, затем запускай test send.");
      return;
    }

    const emails = parseBroadcastTargetText(broadcastTestEmailsInput).map((item) => item.toLowerCase());
    const telegramIdTokens = parseBroadcastTargetText(broadcastTestTelegramIdsInput);
    const telegramIds: number[] = [];
    for (const token of telegramIdTokens) {
      const normalized = token.replace(/^@/, "");
      if (!/^-?\d+$/.test(normalized)) {
        setError(`Некорректный telegram_id: ${token}`);
        return;
      }
      telegramIds.push(Number.parseInt(normalized, 10));
    }

    const trimmedComment = broadcastTestComment.trim();
    if (emails.length === 0 && telegramIds.length === 0) {
      setError("Добавь хотя бы один email или telegram_id для test send");
      return;
    }
    if (!trimmedComment) {
      setError("Комментарий для test send обязателен");
      return;
    }

    setBroadcastTestSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const idempotencyKey =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `broadcast-test-${Date.now()}`;

      const result = await adminFetch<AdminBroadcastTestSendResponse>(
        `/api/v1/admin/broadcasts/${selectedBroadcastId}/test-send`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            emails,
            telegram_ids: telegramIds,
            comment: trimmedComment,
            idempotency_key: idempotencyKey,
          }),
        },
      );
      setBroadcastTestResult(result);
      setNotice(
        `Test send завершен: отправлено ${result.sent_targets}, частично ${result.partial_targets}, ошибок ${result.failed_targets}, пропущено ${result.skipped_targets}.`,
      );
    } catch (testSendError) {
      setError(testSendError instanceof Error ? testSendError.message : "Не удалось выполнить test send");
    } finally {
      setBroadcastTestSubmitting(false);
    }
  }

  async function refreshBroadcastRuntimeState(activeToken: string, broadcastId?: number | null) {
    await loadBroadcasts(activeToken);
    await loadBroadcastRuns(activeToken);
    if (broadcastId !== null && broadcastId !== undefined) {
      await loadBroadcastDetail(broadcastId, activeToken);
    }
    if (selectedBroadcastRunId !== null) {
      await loadBroadcastRunDetail(selectedBroadcastRunId, activeToken);
    }
  }

  async function handleRefreshBroadcastWorkspace() {
    if (!token) {
      return;
    }

    setBroadcastWorkspaceRefreshing(true);
    setError(null);
    try {
      await refreshBroadcastRuntimeState(token, selectedBroadcastId);
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
      setSelectedBroadcastRunId(updated.latest_run?.id ?? selectedBroadcastRunId);
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
        updateSearchResultSnapshot(refreshedAccount);
      } else {
        setSearchResults((items) =>
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
        updateSearchResultSnapshot(refreshedAccount);
      } else {
        setSearchResults((items) =>
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
        updateSearchResultSnapshot(refreshedAccount);
      } else {
        setSearchResults((items) =>
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
        <section className="auth-panel">
          <div className="auth-copy">
            <span className="eyebrow">Remnastore Admin</span>
            <h1>Операционная панель проекта</h1>
            <p>
              Светлая админка для поддержки, платежей, выводов и рассылок. Для первого входа задай
              `ADMIN_BOOTSTRAP_USERNAME` и `ADMIN_BOOTSTRAP_PASSWORD` в `.env`.
            </p>
            <div className="scene-panel">
              <div className="sage-portrait" aria-hidden="true">
                <span className="sage-aura" />
                <span className="sage-head" />
                <span className="sage-ears sage-ears--left" />
                <span className="sage-ears sage-ears--right" />
                <span className="sage-robe" />
                <span className="energy-blade" />
                <span className="energy-hilt" />
              </div>
              <div className="scene-copy">
                <span className="scene-label">Рабочий контур</span>
                <strong>Одна панель для пользователей, финансовых действий и кампаний.</strong>
                <p>
                  Сначала безопасный вход, затем единый интерфейс для ежедневной операционной работы.
                </p>
              </div>
            </div>
          </div>
          <form className="auth-form" onSubmit={handleLogin}>
            <label>
              <span>Логин или email</span>
              <input
                autoComplete="username"
                value={login}
                onChange={(event) => setLogin(event.target.value)}
                placeholder="root или root@example.com"
                required
              />
            </label>
            <label>
              <span>Пароль</span>
              <input
                autoComplete="current-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Введите пароль"
                required
              />
            </label>
            {error ? <div className="form-error">{error}</div> : null}
            <button type="submit" disabled={submitting}>
              {submitting ? "Входим..." : "Войти"}
            </button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="admin-shell">
      <section className="dashboard-hero">
        <div className="hero-copy">
          <span className="eyebrow">Remnastore Admin</span>
          <h1>Единая операционная панель</h1>
          <p>
            Здесь собраны сводка, пользователи, выводы и runtime рассылок. Приоритет интерфейса:
            быстро читать состояние системы, безопасно выполнять действия и не терять контекст при работе.
          </p>
        </div>
        <div className="hero-side">
          <div className="hero-blade" aria-hidden="true">
            <span className="hero-blade__beam" />
            <span className="hero-blade__hilt" />
          </div>
          <div className="hero-actions">
            <button className="ghost-button" type="button" onClick={handleRefresh} disabled={loading}>
              {loading ? "Обновляем..." : "Обновить"}
            </button>
            <button className="ghost-button" type="button" onClick={handleLogout}>
              Выйти
            </button>
          </div>
        </div>
      </section>

      <nav className="module-nav" aria-label="Модули админки">
        <button
          type="button"
          className={activeView === "dashboard" ? "module-nav__button module-nav__button--active" : "module-nav__button"}
          onClick={() => setActiveView("dashboard")}
        >
          Сводка
        </button>
        <button
          type="button"
          className={activeView === "accounts" ? "module-nav__button module-nav__button--active" : "module-nav__button"}
          onClick={() => setActiveView("accounts")}
        >
          Пользователи
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
          Рассылки
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
          Выводы
        </button>
      </nav>

      {error ? <div className="form-error form-error--banner">{error}</div> : null}
      {notice ? <div className="form-success form-success--banner">{notice}</div> : null}

      {activeView === "dashboard" ? (
        <>
          <section className="dashboard-grid">
            <article className="profile-card">
              <span className="eyebrow">Профиль оператора</span>
              <h2>{profile?.full_name || profile?.username || "Администратор"}</h2>
              <dl className="profile-list">
                <div>
                  <dt>Логин</dt>
                  <dd>{profile?.username}</dd>
                </div>
                <div>
                  <dt>Email</dt>
                  <dd>{profile?.email || "Не задан"}</dd>
                </div>
                <div>
                  <dt>Роль</dt>
                  <dd>{profile?.is_superuser ? "Суперадмин" : "Оператор"}</dd>
                </div>
                <div>
                  <dt>Последний вход</dt>
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
                  <span className="eyebrow">Финансовый срез</span>
                  <h2>Деньги и очереди</h2>
                </div>
                <p>Snapshot на сейчас и агрегаты за последние 30 дней.</p>
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
                  <span className="eyebrow">Операционный срез</span>
                  <h2>Поток пользователей и продаж</h2>
                </div>
                <p>Здесь виден приток, блокировки, топапы, direct purchase и общий referral хвост.</p>
              </div>
              <div className="metrics-grid metrics-grid--dense">
                {activityCards.map((card) => (
                  <DashboardCard key={card.label} {...card} />
                ))}
              </div>
            </article>
          </section>

          <section className="roadmap-card">
            <span className="eyebrow">Следующий сектор</span>
            <ul>
              <li>Рассылки</li>
              <li>Довести audit trail до всех admin actions</li>
              <li>Фильтры и экспорт для очереди выводов</li>
            </ul>
          </section>
        </>
      ) : activeView === "accounts" ? (
        <section className="search-shell">
          <aside className="search-column">
            <form className="search-panel" onSubmit={handleSearch}>
              <span className="eyebrow">Поиск пользователя</span>
              <h2>telegram_id, email или username</h2>
              <div className="search-bar">
                <input
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Например: 777000111 или user@example.com"
                  required
                />
                <button type="submit" disabled={searching}>
                  {searching ? "Ищем..." : "Найти"}
                </button>
              </div>
            </form>

            <div className="results-list">
              {searchResults.length === 0 ? (
                <div className="empty-state">Список пуст. Сначала выполни поиск.</div>
              ) : (
                searchResults.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={selectedAccountId === item.id ? "result-card result-card--active" : "result-card"}
                    onClick={() => void handleSelectAccount(item.id)}
                  >
                    <div className="result-card__top">
                      <strong>{item.display_name || item.username || item.email || item.id}</strong>
                      <span className={`status-pill status-pill--${item.status}`}>{humanizeAccountStatus(item.status)}</span>
                    </div>
                    <span>{item.email || item.username || "Без email и username"}</span>
                    <span>Баланс: {formatMoney(item.balance)}</span>
                    <span>Telegram: {item.telegram_id ? item.telegram_id : "не привязан"}</span>
                  </button>
                ))
              )}
            </div>
          </aside>

          <div className="detail-column">
            {detailLoading ? <div className="detail-skeleton">Загружаем карточку пользователя...</div> : null}
            {!detailLoading && !selectedAccount ? (
              <div className="detail-skeleton">Выбери пользователя из результата поиска.</div>
            ) : null}
            {!detailLoading && selectedAccount ? (
              <>
                <section className="detail-header">
                  <div>
                    <span className="eyebrow">Карточка пользователя</span>
                    <h2>{selectedAccount.display_name || selectedAccount.username || selectedAccount.email || selectedAccount.id}</h2>
                    <p>
                      {selectedAccount.email || "Без email"} · {selectedAccount.telegram_id ? `Telegram ${selectedAccount.telegram_id}` : "Telegram не привязан"}
                    </p>
                  </div>
                  <span className={`status-pill status-pill--${selectedAccount.status}`}>
                    {humanizeAccountStatus(selectedAccount.status)}
                  </span>
                </section>

                <section className="detail-facts-grid">
                  <DetailFact label="Баланс" value={formatMoney(selectedAccount.balance)} />
                  <DetailFact label="Реферальный доход" value={formatMoney(selectedAccount.referral_earnings)} />
                  <DetailFact label="Подписка" value={selectedAccount.subscription_status || "нет"} />
                  <DetailFact label="Создан" value={formatDate(selectedAccount.created_at)} />
                </section>

                <section className="detail-section detail-section--action">
                  <span className="eyebrow">Ручная корректировка баланса</span>
                  <div className="detail-section__intro">
                    <h3>Зачисление или списание без захода в БД</h3>
                    <p>
                      Положительная сумма делает `admin_credit`, отрицательная делает `admin_debit`.
                      Комментарий обязателен и попадет в ledger.
                    </p>
                  </div>
                  <form className="adjustment-form" onSubmit={handleBalanceAdjustment}>
                    <label className="form-field">
                      <span>Сумма, RUB</span>
                      <input
                        type="number"
                        step="1"
                        value={balanceAdjustmentAmount}
                        onChange={(event) => setBalanceAdjustmentAmount(event.target.value)}
                        placeholder="Например: 500 или -300"
                        required
                      />
                    </label>
                    <label className="form-field form-field--wide">
                      <span>Комментарий</span>
                      <textarea
                        value={balanceAdjustmentComment}
                        onChange={(event) => setBalanceAdjustmentComment(event.target.value)}
                        placeholder="Почему меняем баланс и на каком основании"
                        rows={3}
                        required
                      />
                    </label>
                    <div className="adjustment-form__footer">
                      <span className="form-hint">
                        `+500` зачислит средства, `-300` спишет. Повторный клик не должен заменять
                        комментарий вроде "поправить баланс".
                      </span>
                      <button className="action-button" type="submit" disabled={balanceSubmitting}>
                        {balanceSubmitting ? "Проводим..." : "Провести корректировку"}
                      </button>
                    </div>
                  </form>
                </section>

                <section className="detail-section detail-section--action">
                  <span className="eyebrow">Ручная выдача подписки</span>
                  <div className="detail-section__intro">
                    <h3>Продление доступа без платежного flow</h3>
                    <p>
                      Выбор тарифа идет из backend-каталога. Комментарий обязателен, а операция
                      фиксируется в audit trail как admin action.
                    </p>
                  </div>
                  <form className="adjustment-form" onSubmit={handleSubscriptionGrant}>
                    <label className="form-field">
                      <span>Тариф</span>
                      <select
                        value={subscriptionGrantPlanCode}
                        onChange={(event) => setSubscriptionGrantPlanCode(event.target.value)}
                        disabled={plansLoading || subscriptionPlans.length === 0}
                        required
                      >
                        {subscriptionPlans.length === 0 ? (
                          <option value="">
                            {plansLoading ? "Загружаем тарифы..." : "Тарифы недоступны"}
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
                      <span>Комментарий</span>
                      <textarea
                        value={subscriptionGrantComment}
                        onChange={(event) => setSubscriptionGrantComment(event.target.value)}
                        placeholder="Почему выдаем подписку вручную и что это компенсирует"
                        rows={3}
                        required
                      />
                    </label>
                    <div className="adjustment-form__footer">
                      <span className="form-hint">
                        {selectedGrantPlan
                          ? `Будет выдан тариф ${selectedGrantPlan.name} на ${selectedGrantPlan.duration_days} дней. Повторный клик защищен idempotency key.`
                          : "Сначала загрузим тарифы из backend-каталога."}
                      </span>
                      <button
                        className="action-button"
                        type="submit"
                        disabled={
                          plansLoading || subscriptionPlans.length === 0 || subscriptionSubmitting
                        }
                      >
                        {subscriptionSubmitting ? "Выдаем..." : "Выдать подписку"}
                      </button>
                    </div>
                  </form>
                </section>

                <section className="detail-sections-grid">
                  <article className="detail-section">
                    <span className="eyebrow">Идентичность</span>
                    <div className="detail-kv">
                      <div><span>Username</span><strong>{selectedAccount.username || "-"}</strong></div>
                      <div><span>Имя</span><strong>{[selectedAccount.first_name, selectedAccount.last_name].filter(Boolean).join(" ") || "-"}</strong></div>
                      <div><span>Locale</span><strong>{selectedAccount.locale || "-"}</strong></div>
                      <div><span>Referral code</span><strong>{selectedAccount.referral_code || "-"}</strong></div>
                      <div><span>Referrals</span><strong>{selectedAccount.referrals_count}</strong></div>
                      <div><span>Last seen</span><strong>{formatDate(selectedAccount.last_seen_at)}</strong></div>
                    </div>
                  </article>

                  <article className="detail-section">
                    <span className="eyebrow">Подписка</span>
                    <div className="detail-kv">
                      <div><span>Статус</span><strong>{selectedAccount.subscription_status || "нет"}</strong></div>
                      <div><span>Истекает</span><strong>{formatDate(selectedAccount.subscription_expires_at)}</strong></div>
                      <div><span>Trial</span><strong>{selectedAccount.subscription_is_trial ? "Да" : "Нет"}</strong></div>
                      <div><span>Trial used</span><strong>{formatDate(selectedAccount.trial_used_at)}</strong></div>
                      <div><span>Sync</span><strong>{formatDate(selectedAccount.subscription_last_synced_at)}</strong></div>
                      <div><span>Remnawave UUID</span><strong>{selectedAccount.remnawave_user_uuid || "-"}</strong></div>
                    </div>
                    {selectedAccount.subscription_url ? (
                      <a className="detail-link" href={selectedAccount.subscription_url} target="_blank" rel="noreferrer">
                        Открыть subscription URL
                      </a>
                    ) : null}
                  </article>
                </section>

                <section className="detail-facts-grid detail-facts-grid--compact">
                  <DetailFact label="Ledger entries" value={String(selectedAccount.ledger_entries_count)} />
                  <DetailFact label="Payments" value={String(selectedAccount.payments_count)} />
                  <DetailFact label="Pending payments" value={String(selectedAccount.pending_payments_count)} />
                  <DetailFact label="Withdrawals" value={String(selectedAccount.withdrawals_count)} />
                </section>

                <section className="detail-section">
                  <div className="detail-section__header detail-section__header--stacked">
                    <div>
                      <span className="eyebrow">Referral chain</span>
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
                                    : "Награды нет"}
                                </strong>
                                <span>
                                  {referral.reward_created_at
                                    ? `Начислено ${formatDate(referral.reward_created_at)}`
                                    : "Ждет первую успешную оплату"}
                                </span>
                                {referral.purchase_amount !== null && referral.reward_rate !== null ? (
                                  <span>
                                    Покупка {formatMoney(referral.purchase_amount)} · ставка{" "}
                                    {formatRewardRate(referral.reward_rate)}
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
                  <span className="eyebrow">Auth identities</span>
                  <div className="activity-list">
                    {selectedAccount.auth_accounts.length === 0 ? (
                      <div className="activity-empty">Привязанных identity нет.</div>
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
                </section>

                <section className="detail-section">
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
                </section>

                <section className="detail-section detail-section--action detail-section--danger">
                  <span className="eyebrow">Опасная зона</span>
                  <div className="detail-section__intro">
                    <h3>Полная блокировка пользователя</h3>
                    <p>
                      Это удаленное административное действие. Полная блокировка режет protected API,
                      Telegram WebApp auth, новые платежи, wallet-покупки, новые выводы и заставляет
                      бота молчать на обычные сообщения и `/start`.
                    </p>
                  </div>
                  <form className="adjustment-form" onSubmit={handleAccountStatusChange}>
                    <div className="form-field">
                      <span>Текущий статус</span>
                      <div className="status-action-summary status-action-summary--danger">
                        <strong>{humanizeAccountStatus(selectedAccount.status)}</strong>
                        <small>
                          {selectedAccount.status === "blocked"
                            ? "Сейчас для пользователя действует полный стоп по доступу и основным входным точкам."
                            : "Сейчас пользователь работает в обычном режиме. Полную блокировку применяй только как крайнее действие."}
                        </small>
                      </div>
                    </div>
                    <label className="form-field form-field--wide">
                      <span>Комментарий</span>
                      <textarea
                        value={statusChangeComment}
                        onChange={(event) => setStatusChangeComment(event.target.value)}
                        placeholder="Почему включаем или снимаем полную блокировку"
                        rows={3}
                        required
                      />
                    </label>
                    <div className="adjustment-form__footer">
                      <span className="form-hint">
                        Следующее действие:{" "}
                        {selectedAccount.status === "blocked"
                          ? "снять полную блокировку"
                          : "включить полную блокировку"}
                        . Комментарий попадет в audit trail.
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
                          ? "Сохраняем..."
                          : selectedAccount.status === "blocked"
                            ? "Снять полную блокировку"
                            : "Включить полную блокировку"}
                      </button>
                    </div>
                  </form>
                </section>
              </>
            ) : null}
          </div>
        </section>
      ) : activeView === "broadcasts" ? (
        <section className="search-shell search-shell--broadcasts">
          <aside className="search-column search-column--broadcasts">
            <section className="search-panel search-panel--broadcasts">
              <div className="panel-toolbar">
                <div>
                  <span className="eyebrow">Контур рассылок</span>
                  <h2>Кампании и черновики</h2>
                  <p className="queue-panel__copy">
                    Список кампаний живет отдельно от редактора. Пока ты работаешь с черновиком, данные не
                    перетираются автоматическими запросами.
                  </p>
                </div>
                <div className="panel-toolbar__actions">
                  <button className="ghost-button" type="button" onClick={handleNewBroadcastDraft}>
                    Новый черновик
                  </button>
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => void handleRefreshBroadcastWorkspace()}
                    disabled={broadcastWorkspaceRefreshing}
                  >
                    {broadcastWorkspaceRefreshing ? "Обновляем..." : "Обновить"}
                  </button>
                </div>
              </div>

              <div className="queue-summary">
                <article className="queue-summary__item">
                  <span>Всего кампаний</span>
                  <strong>{broadcastTotal}</strong>
                </article>
                <article className="queue-summary__item">
                  <span>В работе</span>
                  <strong>{broadcastItems.filter((item) => item.status === "running").length}</strong>
                </article>
                <article className="queue-summary__item">
                  <span>Журнал запусков</span>
                  <strong>{broadcastRunTotal}</strong>
                </article>
              </div>
            </section>

            <div className="results-list results-list--broadcasts">
              {broadcastsLoading ? (
                <div className="empty-state">Загружаем кампании...</div>
              ) : broadcastItems.length === 0 ? (
                <div className="empty-state">Кампаний пока нет. Создай первый черновик.</div>
              ) : (
                broadcastItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={
                      selectedBroadcastId === item.id
                        ? "result-card result-card--active result-card--broadcast"
                        : "result-card result-card--broadcast"
                    }
                    onClick={() => handleSelectBroadcast(item.id)}
                  >
                    <div className="result-card__top">
                      <strong>{item.name}</strong>
                      <span className={`status-pill status-pill--${item.status}`}>
                        {humanizeBroadcastStatus(item.status)}
                      </span>
                    </div>
                    <div className="broadcast-card-summary">
                      <span className="broadcast-card-summary__title">{item.title}</span>
                      <span>{humanizeBroadcastChannels(item.channels)}</span>
                      <span>
                        {humanizeBroadcastAudienceSegment(item.audience.segment)} · {item.estimated_total_accounts} акк.
                      </span>
                    </div>
                    <div className="broadcast-card-runtime">
                      <span>
                        {item.latest_run
                          ? `${humanizeBroadcastRunType(item.latest_run.run_type)} · ${humanizeBroadcastRunStatus(
                              item.latest_run.status,
                            )}`
                          : "Боевых запусков еще не было"}
                      </span>
                      <strong>
                        {item.latest_run
                          ? `Доставлено ${item.latest_run.delivered_deliveries}/${item.latest_run.total_deliveries}`
                          : "Только черновик"}
                      </strong>
                    </div>
                  </button>
                ))
              )}
            </div>
          </aside>

          <div className="detail-column detail-column--broadcasts">
            <section className="detail-header detail-header--broadcasts">
              <div className="broadcast-toolbar">
                <div>
                  <span className="eyebrow">Редактор кампании</span>
                  <h2>{selectedBroadcast ? selectedBroadcast.title : "Новый черновик"}</h2>
                  <p>
                    Рабочее место разделено на контент, превью, runtime и журнал запусков. Данные
                    обновляются только вручную или после явного действия оператора.
                  </p>
                </div>
              </div>
              <div className="broadcast-toolbar__meta">
                <div className="broadcast-badge-cluster">
                  <span className={`status-pill ${broadcastEditorDirty ? "status-pill--warning" : "status-pill--active"}`}>
                    {broadcastEditorDirty ? "Есть несохраненные изменения" : "Черновик синхронизирован"}
                  </span>
                  <span className={`status-pill ${selectedBroadcast ? `status-pill--${selectedBroadcast.status}` : "status-pill--draft"}`}>
                    {selectedBroadcast ? humanizeBroadcastStatus(selectedBroadcast.status) : "Новый черновик"}
                  </span>
                </div>
                <div className="broadcast-header-actions">
                  <button className="ghost-button" type="button" onClick={handleNewBroadcastDraft}>
                    Новый черновик
                  </button>
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => void handleRefreshBroadcastWorkspace()}
                    disabled={broadcastWorkspaceRefreshing}
                  >
                    {broadcastWorkspaceRefreshing ? "Обновляем..." : "Обновить данные"}
                  </button>
                </div>
              </div>
            </section>

            <section className="detail-facts-grid detail-facts-grid--compact detail-facts-grid--broadcast-overview">
              <DetailFact label="Кампания" value={selectedBroadcastId ? `#${selectedBroadcastId}` : "Новая"} />
              <DetailFact
                label="Каналы"
                value={broadcastChannels.length > 0 ? humanizeBroadcastChannels(broadcastChannels) : "Не выбраны"}
              />
              <DetailFact
                label="Аудитория"
                value={humanizeBroadcastAudienceSegment(broadcastAudienceSegment)}
              />
              <DetailFact
                label="Обновлено"
                value={selectedBroadcast ? formatDateMoscow(selectedBroadcast.updated_at) : "Пока не сохранено"}
              />
            </section>

            <section className="broadcast-workbench">
              <section className="detail-section detail-section--action detail-section--editor">
                <div className="detail-section__header">
                  <div>
                    <span className="eyebrow">Редактор</span>
                    <h3>{broadcastEditorMode === "edit" ? "Контент кампании" : "Создание новой кампании"}</h3>
                  </div>
                  {!broadcastIsDraft && selectedBroadcast ? (
                    <span className="form-hint">
                      Контент зафиксирован. Для новой версии создай отдельный черновик.
                    </span>
                  ) : null}
                </div>

                <form className="broadcast-editor-form" onSubmit={handleSaveBroadcast}>
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
                        <span className="eyebrow">Блок 2</span>
                        <h4>Аудитория и каналы</h4>
                      </div>
                      <span className="form-hint">Состав аудитории и каналы доставки задаются отдельно от текста.</span>
                    </div>
                    <div className="broadcast-form-grid">
                      <div className="broadcast-channel-grid">
                        <label className="checkbox-card">
                          <input
                            type="checkbox"
                            checked={broadcastSendInApp}
                            onChange={(event) => {
                              markBroadcastEditorDirty();
                              setBroadcastSendInApp(event.target.checked);
                            }}
                            disabled={!broadcastIsDraft || broadcastSubmitting}
                          />
                          <span>In-app</span>
                        </label>
                        <label className="checkbox-card">
                          <input
                            type="checkbox"
                            checked={broadcastSendTelegram}
                            onChange={(event) => {
                              markBroadcastEditorDirty();
                              setBroadcastSendTelegram(event.target.checked);
                            }}
                            disabled={!broadcastIsDraft || broadcastSubmitting}
                          />
                          <span>Telegram</span>
                        </label>
                      </div>
                      <label className="form-field">
                        <span>Сегмент аудитории</span>
                        <select
                          value={broadcastAudienceSegment}
                          onChange={(event) => {
                            markBroadcastEditorDirty();
                            setBroadcastAudienceSegment(event.target.value as BroadcastAudienceSegment);
                          }}
                          disabled={!broadcastIsDraft || broadcastSubmitting}
                        >
                          {BROADCAST_AUDIENCE_SEGMENTS.map((segment) => (
                            <option key={segment} value={segment}>
                              {humanizeBroadcastAudienceSegment(segment)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="checkbox-card checkbox-card--inline">
                        <input
                          type="checkbox"
                          checked={broadcastAudienceExcludeBlocked}
                          onChange={(event) => {
                            markBroadcastEditorDirty();
                            setBroadcastAudienceExcludeBlocked(event.target.checked);
                          }}
                          disabled={!broadcastIsDraft || broadcastSubmitting}
                        />
                        <span>Исключать полностью заблокированных</span>
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

              <aside className="broadcast-preview-column">
                <section className="detail-section detail-section--estimate">
                  <div className="detail-section__header detail-section__header--stacked">
                    <div>
                      <span className="eyebrow">Оценка аудитории</span>
                      <h3>Текущая аудитория</h3>
                    </div>
                  </div>
                  <section className="detail-facts-grid detail-facts-grid--compact">
                    <DetailFact
                      label="Всего"
                      value={
                        broadcastEstimateSnapshot ? String(broadcastEstimateSnapshot.estimated_total_accounts) : "—"
                      }
                    />
                    <DetailFact
                      label="In-app"
                      value={
                        broadcastEstimateSnapshot
                          ? String(broadcastEstimateSnapshot.estimated_in_app_recipients)
                          : "—"
                      }
                    />
                    <DetailFact
                      label="Telegram"
                      value={
                        broadcastEstimateSnapshot
                          ? String(broadcastEstimateSnapshot.estimated_telegram_recipients)
                          : "—"
                      }
                    />
                    <DetailFact
                      label="Статус"
                      value={broadcastEstimateLoading ? "Пересчет..." : broadcastEstimateError ? "Ошибка" : "Актуально"}
                    />
                  </section>
                  <div className="section-footer">
                    <span className="form-hint">
                      {broadcastEstimateError ||
                        "Estimate считает текущие сегмент и каналы редактора без сохранения кампании."}
                    </span>
                  </div>
                </section>

                <section className="detail-section detail-section--estimate">
                  <div className="detail-section__header detail-section__header--stacked">
                    <div>
                      <span className="eyebrow">Срез runtime</span>
                      <h3>Последний боевой запуск</h3>
                    </div>
                  </div>
                  {selectedBroadcast?.latest_run ? (
                    <>
                      <section className="detail-facts-grid detail-facts-grid--compact">
                        <DetailFact label="Запуск" value={`#${selectedBroadcast.latest_run.id}`} />
                        <DetailFact
                          label="Тип"
                          value={humanizeBroadcastRunType(selectedBroadcast.latest_run.run_type)}
                        />
                        <DetailFact
                          label="Статус"
                          value={humanizeBroadcastRunStatus(selectedBroadcast.latest_run.status)}
                        />
                        <DetailFact
                          label="Доставлено"
                          value={`${selectedBroadcast.latest_run.delivered_deliveries}/${selectedBroadcast.latest_run.total_deliveries}`}
                        />
                      </section>
                      <div className="section-footer">
                        <span className="form-hint">
                          {selectedBroadcast.latest_run.last_error
                            ? selectedBroadcast.latest_run.last_error
                            : `Старт: ${formatDateMoscow(selectedBroadcast.latest_run.started_at)}`}
                        </span>
                      </div>
                    </>
                  ) : (
                    <div className="activity-empty">Кампания еще не запускалась в боевой контур.</div>
                  )}
                </section>

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
                      {`${humanizeBroadcastAudienceSegment(broadcastAudienceSegment)} · ${
                        broadcastChannels.length > 0
                          ? humanizeBroadcastChannels(broadcastChannels)
                          : "каналы не выбраны"
                      }`}
                    </span>
                  </div>
                </article>
              </aside>
            </section>

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

              <section className="detail-section detail-section--action">
                <div className="detail-section__header detail-section__header--stacked">
                  <div>
                    <span className="eyebrow">Тестовая отправка</span>
                    <h3>Контрольная отправка</h3>
                  </div>
                  <span className="form-hint">
                    Контрольная отправка работает только по сохраненному черновику. Несохраненные правки сначала
                    фиксируются, затем отправляются на тестовых адресатов.
                  </span>
                </div>

                <form className="adjustment-form adjustment-form--runtime" onSubmit={handleBroadcastTestSend}>
                  <label className="form-field form-field--wide">
                    <span>Email получателей</span>
                    <textarea
                      value={broadcastTestEmailsInput}
                      onChange={(event) => setBroadcastTestEmailsInput(event.target.value)}
                      placeholder={"user@example.com\npartner@example.com"}
                      rows={4}
                      disabled={selectedBroadcastId === null || !broadcastIsDraft || broadcastTestSubmitting}
                    />
                  </label>
                  <label className="form-field form-field--wide">
                    <span>Telegram ID получателей</span>
                    <textarea
                      value={broadcastTestTelegramIdsInput}
                      onChange={(event) => setBroadcastTestTelegramIdsInput(event.target.value)}
                      placeholder={"777000111\n999888777"}
                      rows={4}
                      disabled={selectedBroadcastId === null || !broadcastIsDraft || broadcastTestSubmitting}
                    />
                  </label>
                  <label className="form-field form-field--wide">
                    <span>Комментарий</span>
                    <textarea
                      value={broadcastTestComment}
                      onChange={(event) => setBroadcastTestComment(event.target.value)}
                      placeholder="Что именно проверяем и кто подтверждает результат"
                      rows={3}
                      required
                      disabled={selectedBroadcastId === null || !broadcastIsDraft || broadcastTestSubmitting}
                    />
                  </label>
                  <div className="adjustment-form__footer">
                    <span className="form-hint">
                      `email` ищет локальный аккаунт. `telegram_id` может быть как локальным, так и внешним Telegram-only адресатом.
                    </span>
                    <button
                      className="action-button"
                      type="submit"
                      disabled={selectedBroadcastId === null || !broadcastIsDraft || broadcastTestSubmitting}
                    >
                      {broadcastTestSubmitting ? "Отправляем..." : "Запустить test send"}
                    </button>
                  </div>
                </form>

                {broadcastTestResult ? (
                  <>
                    <section className="detail-facts-grid detail-facts-grid--compact">
                      <DetailFact label="Получатели" value={String(broadcastTestResult.total_targets)} />
                      <DetailFact label="Отправлено" value={String(broadcastTestResult.sent_targets)} />
                      <DetailFact label="Частично" value={String(broadcastTestResult.partial_targets)} />
                      <DetailFact label="Ошибки" value={String(broadcastTestResult.failed_targets)} />
                    </section>
                    <section className="detail-facts-grid detail-facts-grid--compact">
                      <DetailFact label="Пропущено" value={String(broadcastTestResult.skipped_targets)} />
                      <DetailFact label="In-app" value={String(broadcastTestResult.in_app_notifications_created)} />
                      <DetailFact label="Telegram" value={String(broadcastTestResult.telegram_targets_sent)} />
                      <DetailFact label="Audit ID" value={String(broadcastTestResult.audit_log_id)} />
                    </section>

                    <div className="activity-list">
                      {broadcastTestResult.items.map((item) => (
                        <article key={`${item.source}:${item.target}`} className="activity-item">
                          <div>
                            <strong>{item.target}</strong>
                            <span>
                              {item.source === "email" ? "email" : "telegram_id"} · {item.resolution}
                            </span>
                            <span>
                              {item.channels_attempted.length > 0
                                ? humanizeBroadcastChannels(item.channels_attempted)
                                : "каналы не применялись"}
                            </span>
                            {item.detail ? <span>{item.detail}</span> : null}
                          </div>
                          <div className="activity-item__meta">
                            <span
                              className={`status-pill status-pill--${
                                item.status === "sent"
                                  ? "paid"
                                  : item.status === "partial"
                                    ? "in_progress"
                                    : item.status === "failed"
                                      ? "rejected"
                                      : "new"
                              }`}
                            >
                              {humanizeBroadcastTestSendStatus(item.status)}
                            </span>
                            {item.in_app_notification_id ? <span>In-app #{item.in_app_notification_id}</span> : null}
                            {item.telegram_message_ids.length > 0 ? (
                              <span>Telegram: {item.telegram_message_ids.join(", ")}</span>
                            ) : null}
                          </div>
                        </article>
                      ))}
                    </div>
                  </>
                ) : null}
              </section>
            </section>

            <section className="detail-section detail-section--action">
              <div className="detail-section__header detail-section__header--stacked">
                <div>
                  <span className="eyebrow">Журнал запусков</span>
                  <h3>История боевых запусков по всем кампаниям</h3>
                </div>
                <div className="panel-toolbar__actions">
                  <span className="form-hint">
                    Журнал обновляется вручную. Test send живет отдельно и не смешивается с боевыми run.
                  </span>
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => void handleRefreshBroadcastWorkspace()}
                    disabled={broadcastWorkspaceRefreshing}
                  >
                    {broadcastWorkspaceRefreshing ? "Обновляем..." : "Обновить журнал"}
                  </button>
                </div>
              </div>

              <div className="detail-facts-grid detail-facts-grid--compact">
                <DetailFact label="Всего run" value={String(broadcastRunTotal)} />
                <DetailFact
                  label="В работе"
                  value={String(broadcastRunItems.filter((item) => item.status === "running").length)}
                />
                <DetailFact
                  label="На паузе"
                  value={String(broadcastRunItems.filter((item) => item.status === "paused").length)}
                />
                <DetailFact
                  label="Выбран"
                  value={selectedBroadcastRun ? `#${selectedBroadcastRun.id}` : "—"}
                />
              </div>

              <div className="detail-sections-grid">
                <article className="detail-section">
                  <div className="detail-section__header detail-section__header--stacked">
                    <div>
                      <span className="eyebrow">Фильтры</span>
                      <h3>Список запусков</h3>
                    </div>
                  </div>
                  <div className="broadcast-channel-grid">
                    <label className="form-field">
                      <span>Статус</span>
                      <select
                        value={broadcastRunStatusFilter}
                        onChange={(event) =>
                          setBroadcastRunStatusFilter(event.target.value as BroadcastRunStatus | "all")
                        }
                      >
                        <option value="all">Все</option>
                        <option value="running">В работе</option>
                        <option value="paused">Пауза</option>
                        <option value="completed">Завершен</option>
                        <option value="failed">Ошибка</option>
                        <option value="cancelled">Отменен</option>
                      </select>
                    </label>
                    <label className="form-field">
                      <span>Тип запуска</span>
                      <select
                        value={broadcastRunTypeFilter}
                        onChange={(event) =>
                          setBroadcastRunTypeFilter(event.target.value as BroadcastRunType | "all")
                        }
                      >
                        <option value="all">Все</option>
                        <option value="send_now">Отправить сейчас</option>
                        <option value="scheduled">По расписанию</option>
                      </select>
                    </label>
                    <label className="form-field">
                      <span>Канал</span>
                      <select
                        value={broadcastRunChannelFilter}
                        onChange={(event) =>
                          setBroadcastRunChannelFilter(event.target.value as BroadcastChannel | "all")
                        }
                      >
                        <option value="all">Все</option>
                        <option value="in_app">In-app</option>
                        <option value="telegram">Telegram</option>
                      </select>
                    </label>
                  </div>

                  <div className="activity-list">
                    {broadcastRunsLoading ? (
                      <div className="activity-empty">Загружаем журнал запусков...</div>
                    ) : broadcastRunItems.length === 0 ? (
                      <div className="activity-empty">Под текущие фильтры run-ов пока нет.</div>
                    ) : (
                      broadcastRunItems.map((run) => (
                        <article
                          key={run.id}
                          className={
                            selectedBroadcastRunId === run.id
                              ? "activity-item activity-item--selectable activity-item--active"
                              : "activity-item activity-item--selectable"
                          }
                          onClick={() => setSelectedBroadcastRunId(run.id)}
                        >
                          <div>
                            <strong>Run #{run.id} · broadcast #{run.broadcast_id}</strong>
                            <span>
                              {humanizeBroadcastRunType(run.run_type)} · {formatDateMoscow(run.started_at)}
                            </span>
                            <span>
                              delivered {run.delivered_deliveries}/{run.total_deliveries} · pending {run.pending_deliveries}
                            </span>
                            {run.last_error ? <span>{run.last_error}</span> : null}
                          </div>
                          <div className="activity-item__meta">
                            <span className={`status-pill status-pill--${run.status}`}>
                              {humanizeBroadcastRunStatus(run.status)}
                            </span>
                          </div>
                        </article>
                      ))
                    )}
                  </div>
                </article>

                <article className="detail-section">
                  <div className="detail-section__header detail-section__header--stacked">
                    <div>
                      <span className="eyebrow">Run detail</span>
                      <h3>Delivery drill-down</h3>
                    </div>
                  </div>
                  {broadcastRunDetailLoading ? (
                    <div className="activity-empty">Загружаем delivery detail...</div>
                  ) : !selectedBroadcastRun ? (
                    <div className="activity-empty">Выбери run слева, чтобы посмотреть детали доставки.</div>
                  ) : (
                    <>
                      <section className="detail-facts-grid detail-facts-grid--compact">
                        <DetailFact label="Total" value={String(selectedBroadcastRun.total_deliveries)} />
                        <DetailFact label="Delivered" value={String(selectedBroadcastRun.delivered_deliveries)} />
                        <DetailFact label="Pending" value={String(selectedBroadcastRun.pending_deliveries)} />
                        <DetailFact label="Failed" value={String(selectedBroadcastRun.failed_deliveries)} />
                      </section>
                      <section className="detail-facts-grid detail-facts-grid--compact">
                        <DetailFact label="Skipped" value={String(selectedBroadcastRun.skipped_deliveries)} />
                        <DetailFact label="In-app" value={String(selectedBroadcastRun.in_app_delivered)} />
                        <DetailFact label="Telegram" value={String(selectedBroadcastRun.telegram_delivered)} />
                        <DetailFact label="Started" value={formatDateMoscow(selectedBroadcastRun.started_at)} />
                      </section>

                      <div className="activity-list">
                        {broadcastRunDeliveries.length === 0 ? (
                          <div className="activity-empty">У выбранного run пока нет delivery-строк.</div>
                        ) : (
                          broadcastRunDeliveries.map((delivery) => (
                            <article key={delivery.id} className="activity-item">
                              <div>
                                <strong>
                                  {delivery.account_display_name ||
                                    delivery.account_username ||
                                    delivery.account_email ||
                                    delivery.account_id}
                                </strong>
                                <span>
                                  {humanizeBroadcastChannel(delivery.channel)} · {humanizeBroadcastDeliveryStatus(delivery.status)}
                                </span>
                                <span>
                                  attempts {delivery.attempts_count}
                                  {delivery.provider_message_id ? ` · provider ${delivery.provider_message_id}` : ""}
                                  {delivery.notification_id ? ` · notification #${delivery.notification_id}` : ""}
                                </span>
                                {delivery.error_message ? <span>{delivery.error_message}</span> : null}
                              </div>
                              <div className="activity-item__meta">
                                <span className={`status-pill status-pill--${delivery.status}`}>
                                  {humanizeBroadcastDeliveryStatus(delivery.status)}
                                </span>
                                <span>{formatDateMoscow(delivery.updated_at)}</span>
                              </div>
                            </article>
                          ))
                        )}
                      </div>
                    </>
                  )}
                </article>
              </div>
            </section>
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
