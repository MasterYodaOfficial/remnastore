import React, { useEffect, useRef, useState } from 'react';
import { supabase } from '../../utils/supabase/client';
import {
  loadTelegramScript,
  getTelegramWebApp,
  openTelegramInvoice,
  openTelegramLink,
} from '../../utils/telegram';
import { LoginPage } from './components/LoginPage';
import { Header } from './components/Header';
import { HomePage } from './components/HomePage';
import { PlansPage } from './components/PlansPage';
import { ReferralPage } from './components/ReferralPage';
import { ReferralCard } from './components/ReferralCard';
import { SettingsPage } from './components/SettingsPage';
import { SubscriptionCard } from './components/SubscriptionCard';
import { ThemeToggle } from './components/ThemeToggle';
import { BottomNav } from './components/BottomNav';
import { PaymentMethodSheet, type PaymentMethodOption, type PaymentMethodProvider } from './components/PaymentMethodSheet';
import { TopUpModal } from './components/TopUpModal';
import { LoadingScreen } from './components/LoadingScreen';
import { NotificationsPage, type NotificationItemView } from './components/NotificationsPage';
import { PendingPaymentsPage, type PendingPaymentView } from './components/PendingPaymentsPage';
import { FaqPage } from './components/FaqPage';
import { LegalDocumentPage } from './components/LegalDocumentPage';
import { BalanceHistoryPage, type BalanceHistoryItemView } from './components/BalanceHistoryPage';
import { formatRubles } from '../lib/currency';
import { toast, Toaster } from 'sonner';
import {
  buildBrowserReferralLink,
  buildTelegramShareReferralUrl,
  capturePendingReferralCodeFromUrl,
  readPendingReferralCode,
  clearPendingReferralCode,
} from './lib/referrals';
import {
  getEffectiveStoredPaymentAttemptStatus,
  getStoredPaymentAttempt,
  isStoredPaymentAttemptActive,
  listStoredPaymentAttemptsForAccount,
  removeStoredPaymentAttempt,
  replaceStoredPaymentAttemptsForAccount,
  upsertStoredPaymentAttempt,
  type StoredPaymentAttempt,
  type StoredPaymentAttemptProvider,
  type StoredPaymentAttemptStatus,
} from './lib/payments';
import {
  Bell,
  CreditCard,
  FileText,
  Gift,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  MessageCircle,
  Moon,
  Settings as SettingsIcon,
  Shield,
  Sparkles,
  Sun,
  Wallet,
} from 'lucide-react';

const BACKEND_API = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(
  /\/+$/,
  ""
);
const TELEGRAM_BOT_URL = (import.meta.env.VITE_TELEGRAM_BOT_URL || '').trim().replace(/\/+$/, '');
const SUPPORT_TELEGRAM_URL = (import.meta.env.VITE_SUPPORT_TELEGRAM_URL || '').trim();
const BROWSER_TOKEN_STORAGE_KEY = 'remnastore.browser_access_token';
const TELEGRAM_AUTH_STORAGE_KEY = 'remnastore.telegram_auth';
const PASSWORD_RECOVERY_STORAGE_KEY = 'remnastore.password_recovery_active';
const THEME_STORAGE_KEY = 'remnastore.theme';
type AuthView = 'default' | 'recovery' | 'recovery-expired';
type AppTab =
  | 'home'
  | 'plans'
  | 'notifications'
  | 'payments'
  | 'balance-history'
  | 'referral'
  | 'settings'
  | 'faq'
  | 'privacy'
  | 'terms';
type PrimaryAppTab = 'home' | 'plans' | 'referral' | 'settings';

const APP_THEME_TOKENS = {
  light: {
    '--tg-theme-bg-color': '#f8fafc',
    '--tg-theme-text-color': '#0f172a',
    '--tg-theme-hint-color': '#64748b',
    '--tg-theme-link-color': '#2563eb',
    '--tg-theme-button-color': '#2563eb',
    '--tg-theme-button-text-color': '#ffffff',
    '--tg-theme-secondary-bg-color': '#e5edf8',
    '--app-surface-color': '#dbe4f2',
    '--app-border-color': 'rgba(15, 23, 42, 0.12)',
    '--app-toggle-track': '#dbe7ff',
    '--app-toggle-thumb': '#ffffff',
    '--app-danger-bg': '#ef4444',
    '--app-danger-bg-hover': '#dc2626',
    '--app-danger-text': '#ffffff',
    '--app-success-color': '#16a34a',
    '--app-success-bg': '#16a34a',
    '--app-success-bg-hover': '#15803d',
    '--app-success-text': '#ffffff',
    '--app-warning-color': '#ca8a04',
    '--app-muted-contrast': '#475569',
  },
  dark: {
    '--tg-theme-bg-color': '#0b1220',
    '--tg-theme-text-color': '#e5edf8',
    '--tg-theme-hint-color': '#8ea0b9',
    '--tg-theme-link-color': '#67d0ff',
    '--tg-theme-button-color': '#67d0ff',
    '--tg-theme-button-text-color': '#04111d',
    '--tg-theme-secondary-bg-color': '#162033',
    '--app-surface-color': '#22304a',
    '--app-border-color': 'rgba(148, 163, 184, 0.18)',
    '--app-toggle-track': '#22304a',
    '--app-toggle-thumb': '#ffffff',
    '--app-danger-bg': '#f87171',
    '--app-danger-bg-hover': '#ef4444',
    '--app-danger-text': '#ffffff',
    '--app-success-color': '#4ade80',
    '--app-success-bg': '#22c55e',
    '--app-success-bg-hover': '#16a34a',
    '--app-success-text': '#04110d',
    '--app-warning-color': '#facc15',
    '--app-muted-contrast': '#cbd5e1',
  },
} as const;

interface BackendAccount {
  id: string;
  telegram_id?: number | null;
  email?: string | null;
  display_name?: string | null;
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  balance: number;
  referral_code?: string | null;
  referral_earnings?: number;
  referral_earnings_cents?: number;
  referrals_count: number;
  referred_by_account_id?: string | null;
  has_used_trial?: boolean;
  subscription_status?: string | null;
  subscription_url?: string | null;
  subscription_expires_at?: string | null;
  subscription_last_synced_at?: string | null;
  subscription_is_trial?: boolean;
  trial_used_at?: string | null;
  trial_ends_at?: string | null;
}

interface BackendSubscriptionState {
  remnawave_user_uuid?: string | null;
  subscription_url?: string | null;
  status?: string | null;
  expires_at?: string | null;
  last_synced_at?: string | null;
  is_active: boolean;
  is_trial: boolean;
  has_used_trial: boolean;
  trial_used_at?: string | null;
  trial_ends_at?: string | null;
  days_left?: number | null;
}

interface BackendTrialUi {
  can_start_now: boolean;
  reason?: string | null;
  has_used_trial: boolean;
  checked_at: string;
  strict_check_required_on_start: boolean;
}

interface BackendBootstrapResponse {
  account: BackendAccount;
  subscription: BackendSubscriptionState;
  trial_ui: BackendTrialUi;
}

interface BackendPlan {
  code: string;
  name: string;
  price_rub: number;
  price_stars?: number | null;
  duration_days: number;
  features: string[];
  popular?: boolean;
}

interface BackendPaymentIntent {
  provider: string;
  flow_type: string;
  account_id: string;
  status: string;
  amount: number;
  currency: string;
  provider_payment_id: string;
  external_reference?: string | null;
  confirmation_url?: string | null;
  expires_at?: string | null;
}

interface BackendPaymentStatusResponse {
  provider: string;
  flow_type: string;
  status: string;
  amount: number;
  currency: string;
  provider_payment_id: string;
  confirmation_url?: string | null;
  expires_at?: string | null;
  finalized_at?: string | null;
}

interface BackendPaymentListItem {
  id: number;
  provider: 'yookassa' | 'telegram_stars';
  flow_type: 'wallet_topup' | 'direct_plan_purchase';
  status: 'created' | 'pending' | 'requires_action' | 'succeeded' | 'failed' | 'cancelled' | 'expired';
  amount: number;
  currency: string;
  provider_payment_id: string;
  plan_code?: string | null;
  description?: string | null;
  confirmation_url?: string | null;
  expires_at?: string | null;
  finalized_at?: string | null;
  created_at: string;
}

interface BackendPaymentListResponse {
  items: BackendPaymentListItem[];
  total: number;
  limit: number;
  offset: number;
}

interface BackendLedgerEntry {
  id: number;
  entry_type: string;
  amount: number;
  currency: string;
  balance_before: number;
  balance_after: number;
  reference_type?: string | null;
  reference_id?: string | null;
  comment?: string | null;
  created_at: string;
}

interface BackendLedgerHistoryResponse {
  items: BackendLedgerEntry[];
  total: number;
  limit: number;
  offset: number;
}

interface BackendReferralSummaryItem {
  referred_account_id: string;
  display_name: string;
  created_at: string;
  reward_amount: number;
  status: 'active' | 'pending';
}

interface BackendReferralSummary {
  referral_code: string;
  referrals_count: number;
  referral_earnings: number;
  available_for_withdraw: number;
  effective_reward_rate: number;
  items: BackendReferralSummaryItem[];
}

interface BackendNotificationItem {
  id: number;
  type:
    | 'broadcast'
    | 'payment_succeeded'
    | 'payment_failed'
    | 'subscription_expiring'
    | 'subscription_expired'
    | 'referral_reward_received'
    | 'withdrawal_created'
    | 'withdrawal_paid'
    | 'withdrawal_rejected';
  title: string;
  body: string;
  priority: 'info' | 'success' | 'warning' | 'error';
  payload?: NotificationItemView['payload'];
  action_label?: string | null;
  action_url?: string | null;
  read_at?: string | null;
  is_read: boolean;
  created_at: string;
}

interface BackendNotificationListResponse {
  items: BackendNotificationItem[];
  total: number;
  unread_count: number;
}

interface BackendNotificationUnreadCountResponse {
  unread_count: number;
}

interface StoredTelegramAuth {
  accessToken: string;
  telegramUserId: number;
}

interface BackendTelegramReferralResult {
  applied: boolean;
  created: boolean;
  reason?: string | null;
}

interface User {
  id: string;
  name: string;
  email: string;
  telegram_id?: number | null;
  balance: number;
  referralCode: string;
  referralsCount: number;
  referralEarnings: number;
  referredByAccountId?: string | null;
  hasUsedTrial: boolean;
  avatar?: string;
}

interface Subscription {
  isActive: boolean;
  daysLeft?: number;
  totalDays?: number;
  hasTrial: boolean;
  hasUsedTrial: boolean;
  isTrial: boolean;
  status?: string | null;
  expiresAt?: string | null;
  subscriptionUrl?: string | null;
  trialEligibilityReason?: string | null;
}

interface Plan {
  id: string;
  name: string;
  price: number;
  priceStars?: number | null;
  duration: number;
  features: string[];
  popular?: boolean;
}

type PaymentSelectionState =
  | {
      kind: 'plan';
      planId: string;
      planName: string;
      methods: PaymentMethodOption[];
    }
  | {
      kind: 'topup';
      amount: number;
      methods: PaymentMethodOption[];
    };

interface SupabaseIdentityLike {
  provider?: string;
  identity_data?: Record<string, unknown> | null;
}

interface SupabaseUserLike {
  user_metadata?: Record<string, unknown> | null;
  identities?: SupabaseIdentityLike[] | null;
}

function pickAvatarUrl(source: Record<string, unknown> | null | undefined): string | undefined {
  if (!source) {
    return undefined;
  }

  for (const key of ['avatar_url', 'picture', 'photo_url', 'image', 'profile_image_url']) {
    const value = source[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }

  return undefined;
}

function getSupabaseAvatarUrl(user: SupabaseUserLike | null | undefined): string | undefined {
  if (!user) {
    return undefined;
  }

  const identities = Array.isArray(user.identities) ? user.identities : [];
  const googleIdentity = identities.find((identity) => identity?.provider === 'google');

  return (
    pickAvatarUrl(googleIdentity?.identity_data) ||
    pickAvatarUrl(user.user_metadata) ||
    identities
      .map((identity) => pickAvatarUrl(identity?.identity_data))
      .find((value): value is string => Boolean(value))
  );
}

function getReferralEarnings(account: BackendAccount): number {
  if (typeof account.referral_earnings === 'number' && Number.isFinite(account.referral_earnings)) {
    return Math.trunc(account.referral_earnings);
  }

  if (
    typeof account.referral_earnings_cents === 'number' &&
    Number.isFinite(account.referral_earnings_cents)
  ) {
    return Math.trunc(account.referral_earnings_cents / 100);
  }

  return 0;
}

function mapBackendAccountToUser(account: BackendAccount, avatar?: string): User {
  const name =
    account.display_name ||
    account.first_name ||
    account.username ||
    account.email ||
    'Пользователь';

  return {
    id: account.id,
    name,
    email: account.email || '',
    telegram_id: account.telegram_id ?? null,
    balance: account.balance || 0,
    referralCode: account.referral_code || '',
    referralsCount: account.referrals_count || 0,
    referralEarnings: getReferralEarnings(account),
    referredByAccountId: account.referred_by_account_id ?? null,
    hasUsedTrial: account.has_used_trial ?? Boolean(account.trial_used_at),
    avatar,
  };
}

function calculateTotalDays(
  startedAt?: string | null,
  endsAt?: string | null
): number | undefined {
  if (!startedAt || !endsAt) {
    return undefined;
  }

  const started = new Date(startedAt);
  const ends = new Date(endsAt);
  if (Number.isNaN(started.getTime()) || Number.isNaN(ends.getTime())) {
    return undefined;
  }

  const durationMs = ends.getTime() - started.getTime();
  if (durationMs <= 0) {
    return undefined;
  }

  return Math.max(1, Math.ceil(durationMs / (1000 * 60 * 60 * 24)));
}

function calculateDaysLeft(expiresAt?: string | null): number | undefined {
  if (!expiresAt) {
    return undefined;
  }

  const ends = new Date(expiresAt);
  if (Number.isNaN(ends.getTime())) {
    return undefined;
  }

  const durationMs = ends.getTime() - Date.now();
  if (durationMs <= 0) {
    return undefined;
  }

  return Math.max(1, Math.ceil(durationMs / (1000 * 60 * 60 * 24)));
}

function mapSubscriptionToView(
  account: BackendAccount,
  subscriptionState: BackendSubscriptionState | null,
  trialUi: BackendTrialUi | null
): Subscription {
  const hasUsedTrial =
    trialUi?.has_used_trial ??
    account.has_used_trial ??
    subscriptionState?.has_used_trial ??
    Boolean(account.trial_used_at);

  const status = subscriptionState?.status ?? account.subscription_status ?? null;
  const expiresAt = subscriptionState?.expires_at ?? account.subscription_expires_at ?? null;
  const trialUsedAt = subscriptionState?.trial_used_at ?? account.trial_used_at ?? null;
  const trialEndsAt = subscriptionState?.trial_ends_at ?? account.trial_ends_at ?? null;
  const isTrial = subscriptionState?.is_trial ?? account.subscription_is_trial ?? false;
  const fallbackDaysLeft = calculateDaysLeft(expiresAt);
  const isActive =
    subscriptionState?.is_active ??
    (status === 'ACTIVE' && fallbackDaysLeft !== undefined);
  const daysLeft = subscriptionState?.days_left ?? fallbackDaysLeft;

  return {
    isActive,
    daysLeft: daysLeft ?? undefined,
    totalDays: calculateTotalDays(trialUsedAt, trialEndsAt),
    hasTrial: trialUi?.can_start_now ?? !hasUsedTrial,
    hasUsedTrial,
    isTrial,
    status,
    expiresAt,
    subscriptionUrl: subscriptionState?.subscription_url ?? account.subscription_url ?? null,
    trialEligibilityReason: trialUi?.reason ?? null,
  };
}

function getTrialErrorMessage(detail: string): string {
  switch (detail) {
    case 'account_blocked':
      return 'Аккаунт заблокирован. Пробный период недоступен.';
    case 'trial_already_used':
      return 'Пробный период уже был использован.';
    case 'subscription_exists':
      return 'У аккаунта уже есть подписка в системе.';
    case 'remnawave_identity_conflict':
      return 'Для этого email или Telegram уже существует подписка в панели.';
    case 'remnawave_not_configured':
      return 'Интеграция с панелью подписок пока не настроена.';
    case 'remnawave_unavailable':
      return 'Панель подписок временно недоступна. Повтори позже.';
    default:
      return detail;
  }
}

function getPaymentErrorMessage(detail: string): string {
  switch (detail) {
    case 'YooKassa credentials are not configured':
      return 'Платежный шлюз пока не настроен.';
    case 'BOT_TOKEN is required for Telegram Stars':
      return 'Telegram Stars пока не настроены.';
    case 'API_TOKEN is required for Telegram Stars callbacks':
      return 'Внутренний callback для Telegram Stars пока не настроен.';
    case 'insufficient funds':
      return 'На балансе недостаточно средств для покупки тарифа.';
    default:
      if (detail.startsWith('Telegram Stars price is not configured for plan ')) {
        return 'Для этого тарифа пока не настроена цена в Telegram Stars.';
      }
      return detail;
  }
}

function mapBackendPlanToView(plan: BackendPlan): Plan {
  return {
    id: plan.code,
    name: plan.name,
    price: plan.price_rub,
    priceStars: plan.price_stars ?? null,
    duration: plan.duration_days,
    features: plan.features,
    popular: Boolean(plan.popular),
  };
}

function mapBackendNotificationToView(
  notification: BackendNotificationItem
): NotificationItemView {
  return {
    id: notification.id,
    type: notification.type,
    title: notification.title,
    body: notification.body,
    priority: notification.priority,
    payload: notification.payload ?? null,
    actionLabel: notification.action_label ?? null,
    actionUrl: notification.action_url ?? null,
    isRead: notification.is_read,
    createdAt: notification.created_at,
  };
}

function resolvePlanName(planCode: string | null | undefined, plans: Plan[]): string | null {
  if (!planCode) {
    return null;
  }

  return plans.find((plan) => plan.id === planCode)?.name ?? null;
}

function mapBackendPaymentItemToView(
  payment: BackendPaymentListItem,
  plans: Plan[]
): PendingPaymentView {
  return {
    provider: payment.provider,
    kind: payment.flow_type === 'wallet_topup' ? 'topup' : 'plan',
    amount: payment.amount,
    currency: payment.currency,
    providerPaymentId: payment.provider_payment_id,
    confirmationUrl: payment.confirmation_url ?? null,
    status: payment.status as PendingPaymentView['status'],
    expiresAt: payment.expires_at ?? null,
    createdAt: payment.created_at,
    planCode: payment.plan_code ?? null,
    planName: resolvePlanName(payment.plan_code, plans),
    description: payment.description ?? null,
  };
}

function mapStoredAttemptToPendingPaymentView(
  attempt: StoredPaymentAttempt,
  plans: Plan[]
): PendingPaymentView {
  return {
    provider: attempt.provider,
    kind: attempt.kind,
    amount: attempt.amount,
    currency: attempt.currency,
    providerPaymentId: attempt.providerPaymentId,
    confirmationUrl: attempt.confirmationUrl,
    status: attempt.status as PendingPaymentView['status'],
    expiresAt: attempt.expiresAt,
    createdAt: attempt.createdAt,
    planCode: attempt.planId ?? null,
    planName: attempt.planName ?? resolvePlanName(attempt.planId, plans),
    description:
      attempt.kind === 'topup'
        ? `Пополнение на ${formatRubles(attempt.amount)} ₽`
        : resolvePlanName(attempt.planId, plans),
  };
}

function mergePendingPayments(
  backendPayments: PendingPaymentView[],
  storedAttempts: StoredPaymentAttempt[],
  plans: Plan[]
): PendingPaymentView[] {
  const merged = new Map<string, PendingPaymentView>();

  for (const payment of backendPayments) {
    merged.set(`${payment.provider}:${payment.providerPaymentId}`, payment);
  }

  for (const attempt of storedAttempts) {
    const localView = mapStoredAttemptToPendingPaymentView(attempt, plans);
    const key = `${localView.provider}:${localView.providerPaymentId}`;
    const existing = merged.get(key);
    merged.set(key, {
      ...(existing ?? localView),
      ...localView,
      planName: localView.planName || existing?.planName || null,
      description: localView.description || existing?.description || null,
    });
  }

  return Array.from(merged.values()).sort((left, right) => right.createdAt.localeCompare(left.createdAt));
}

function mapBackendLedgerEntryToView(entry: BackendLedgerEntry): BalanceHistoryItemView {
  return {
    id: entry.id,
    entryType: entry.entry_type,
    amount: entry.amount,
    balanceAfter: entry.balance_after,
    comment: entry.comment ?? null,
    referenceType: entry.reference_type ?? null,
    referenceId: entry.reference_id ?? null,
    createdAt: entry.created_at,
  };
}

function createClientIdempotencyKey(prefix: string): string {
  const randomPart =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${randomPart}`;
}

function getPaymentReturnUrl(options: { preferTelegramBot?: boolean } = {}): string {
  if (typeof window === 'undefined') {
    return '';
  }

  if (options.preferTelegramBot && TELEGRAM_BOT_URL) {
    return TELEGRAM_BOT_URL;
  }

  const { origin, pathname } = window.location;
  return `${origin}${pathname}`;
}

function buildYooKassaMethod(isTelegramWebApp: boolean): PaymentMethodOption {
  return {
    provider: 'yookassa',
    label: 'Банковская карта',
    description: isTelegramWebApp
      ? 'Переход на YooKassa во внешнем браузере.'
      : 'Оплата картой через YooKassa.',
    note: isTelegramWebApp ? 'Мини-приложение откроет внешнюю ссылку на оплату.' : undefined,
  };
}

function buildWalletMethod(plan: Plan): PaymentMethodOption {
  return {
    provider: 'wallet',
    label: 'С баланса',
    description: 'Мгновенная активация без внешнего перехода.',
    note: `Списание ${formatRubles(plan.price)} ₽ с внутреннего баланса.`,
  };
}

function getAvailableTopUpPaymentMethods(isTelegramWebApp: boolean): PaymentMethodOption[] {
  return [buildYooKassaMethod(isTelegramWebApp)];
}

function getAvailablePlanPaymentMethods(
  plan: Plan,
  isTelegramWebApp: boolean,
  balance: number
): PaymentMethodOption[] {
  const methods: PaymentMethodOption[] = [];

  if (balance >= plan.price) {
    methods.push(buildWalletMethod(plan));
  }

  if (isTelegramWebApp && plan.priceStars) {
    methods.push({
      provider: 'telegram_stars',
      label: 'Telegram Stars',
      description: 'Оплата внутри Telegram без перехода в браузер.',
      note: `Списание ${plan.priceStars} Stars.`,
    });
  }

  methods.push(buildYooKassaMethod(isTelegramWebApp));
  return methods;
}

function getInitialTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined') {
    return 'light';
  }

  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (storedTheme === 'light' || storedTheme === 'dark') {
    return storedTheme;
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyAppThemeVariables(nextTheme: 'light' | 'dark') {
  if (typeof window === 'undefined') {
    return;
  }

  const root = window.document.documentElement;
  for (const [tokenName, tokenValue] of Object.entries(APP_THEME_TOKENS[nextTheme])) {
    root.style.setProperty(tokenName, tokenValue);
  }
}

function readStoredTelegramAuth(): StoredTelegramAuth | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const raw = window.localStorage.getItem(TELEGRAM_AUTH_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<StoredTelegramAuth>;
    if (
      typeof parsed.accessToken === 'string' &&
      parsed.accessToken &&
      typeof parsed.telegramUserId === 'number' &&
      Number.isFinite(parsed.telegramUserId)
    ) {
      return {
        accessToken: parsed.accessToken,
        telegramUserId: parsed.telegramUserId,
      };
    }
  } catch {
    /* ignore malformed storage */
  }

  window.localStorage.removeItem(TELEGRAM_AUTH_STORAGE_KEY);
  return null;
}

function writeStoredTelegramAuth(value: StoredTelegramAuth) {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.setItem(TELEGRAM_AUTH_STORAGE_KEY, JSON.stringify(value));
}

function clearStoredTelegramAuth() {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.removeItem(TELEGRAM_AUTH_STORAGE_KEY);
}

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isTelegramWebApp, setIsTelegramWebApp] = useState(false);
  const [authView, setAuthView] = useState<AuthView>('default');
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [isLoadingPlans, setIsLoadingPlans] = useState(false);
  const [isTopUpSubmitting, setIsTopUpSubmitting] = useState(false);
  const [checkoutPlanId, setCheckoutPlanId] = useState<string | null>(null);
  const [paymentMethodSelection, setPaymentMethodSelection] = useState<PaymentSelectionState | null>(null);
  const [paymentMethodSubmitting, setPaymentMethodSubmitting] = useState<PaymentMethodProvider | null>(null);
  const [checkoutAttempts, setCheckoutAttempts] = useState<StoredPaymentAttempt[]>([]);
  const [activeTab, setActiveTab] = useState<AppTab>('home');
  const [theme, setTheme] = useState<'light' | 'dark'>(getInitialTheme);
  const [referralCopied, setReferralCopied] = useState(false);
  const [referralSummary, setReferralSummary] = useState<BackendReferralSummary | null>(null);
  const [isLoadingReferralSummary, setIsLoadingReferralSummary] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItemView[]>([]);
  const [notificationsTotal, setNotificationsTotal] = useState(0);
  const [notificationsUnreadCount, setNotificationsUnreadCount] = useState(0);
  const [isLoadingNotifications, setIsLoadingNotifications] = useState(false);
  const [isLoadingMoreNotifications, setIsLoadingMoreNotifications] = useState(false);
  const [isUpdatingNotificationReadState, setIsUpdatingNotificationReadState] = useState(false);
  const [activePayments, setActivePayments] = useState<PendingPaymentView[]>([]);
  const [isLoadingActivePayments, setIsLoadingActivePayments] = useState(false);
  const [ledgerEntries, setLedgerEntries] = useState<BalanceHistoryItemView[]>([]);
  const [ledgerEntriesTotal, setLedgerEntriesTotal] = useState(0);
  const [isLoadingLedgerEntries, setIsLoadingLedgerEntries] = useState(false);
  const [isLoadingMoreLedgerEntries, setIsLoadingMoreLedgerEntries] = useState(false);
  const [isTopUpModalOpen, setIsTopUpModalOpen] = useState(false);
  const [isDesktopBrowser, setIsDesktopBrowser] = useState(
    () => typeof window !== 'undefined' && window.innerWidth >= 1200
  );
  const lastLoadedBrowserTokenRef = useRef<string | null>(null);
  const inFlightBrowserTokenRef = useRef<string | null>(null);
  const currentBrowserTokenRef = useRef<string | null>(null);
  const inFlightLinkTokenRef = useRef<string | null>(null);
  const pendingTelegramLinkRefreshRef = useRef(false);
  const pendingPaymentRefreshRef = useRef(false);
  const pendingReferralClaimRef = useRef(false);
  const attemptedPlansTokenRef = useRef<string | null>(null);
  const attemptedNotificationsTokenRef = useRef<string | null>(null);
  const attemptedActivePaymentsTokenRef = useRef<string | null>(null);
  const attemptedLedgerEntriesTokenRef = useRef<string | null>(null);
  const lastPrimaryTabRef = useRef<PrimaryAppTab>('home');
  const manualLogoutRef = useRef(false);
  const authViewRef = useRef<AuthView>('default');

  const setAuthViewMode = (view: AuthView) => {
    authViewRef.current = view;
    setAuthView(view);
  };

  const loadBootstrapSnapshot = async (token: string) => {
    const response = await fetch(`${BACKEND_API}/api/v1/bootstrap/me`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('Failed to load bootstrap from backend');
    }

    return await response.json() as BackendBootstrapResponse;
  };

  const loadPlansSnapshot = async (token: string) => {
    const response = await fetch(`${BACKEND_API}/api/v1/payments/plans`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('Failed to load plans from backend');
    }

    return await response.json() as BackendPlan[];
  };

  const loadNotificationsSnapshot = async (
    token: string,
    options: { limit?: number; offset?: number; unreadOnly?: boolean } = {}
  ) => {
    const params = new URLSearchParams();
    params.set('limit', String(options.limit ?? 20));
    params.set('offset', String(options.offset ?? 0));
    if (options.unreadOnly) {
      params.set('unread_only', 'true');
    }

    const response = await fetch(`${BACKEND_API}/api/v1/notifications?${params.toString()}`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('Failed to load notifications from backend');
    }

    return (await response.json()) as BackendNotificationListResponse;
  };

  const loadNotificationsUnreadCountSnapshot = async (token: string) => {
    const response = await fetch(`${BACKEND_API}/api/v1/notifications/unread-count`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('Failed to load notifications unread count from backend');
    }

    return (await response.json()) as BackendNotificationUnreadCountResponse;
  };

  const loadActivePaymentsSnapshot = async (
    token: string,
    options: { limit?: number; offset?: number } = {}
  ) => {
    const params = new URLSearchParams();
    params.set('active_only', 'true');
    params.set('limit', String(options.limit ?? 20));
    params.set('offset', String(options.offset ?? 0));

    const response = await fetch(`${BACKEND_API}/api/v1/payments?${params.toString()}`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('Failed to load active payments from backend');
    }

    return (await response.json()) as BackendPaymentListResponse;
  };

  const loadLedgerEntriesSnapshot = async (
    token: string,
    options: { limit?: number; offset?: number } = {}
  ) => {
    const params = new URLSearchParams();
    params.set('limit', String(options.limit ?? 20));
    params.set('offset', String(options.offset ?? 0));

    const response = await fetch(`${BACKEND_API}/api/v1/ledger/entries?${params.toString()}`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('Failed to load ledger history from backend');
    }

    return (await response.json()) as BackendLedgerHistoryResponse;
  };

  const loadReferralSummarySnapshot = async (token: string) => {
    const response = await fetch(`${BACKEND_API}/api/v1/referrals/summary`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('Failed to load referral summary from backend');
    }

    return await response.json() as BackendReferralSummary;
  };

  const loadPaymentStatusSnapshot = async (
    token: string,
    provider: StoredPaymentAttemptProvider,
    providerPaymentId: string
  ) => {
    const params = new URLSearchParams({
      provider,
      provider_payment_id: providerPaymentId,
    });
    const response = await fetch(`${BACKEND_API}/api/v1/payments/status?${params.toString()}`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (response.status === 404) {
      return null;
    }

    if (!response.ok) {
      throw new Error('Failed to load payment status from backend');
    }

    return (await response.json()) as BackendPaymentStatusResponse;
  };

  const getStoredPaymentAttemptMatch = (attempt: StoredPaymentAttempt) =>
    attempt.kind === 'plan'
      ? {
          accountId: attempt.accountId,
          kind: attempt.kind,
          provider: attempt.provider,
          planId: attempt.planId,
        }
      : {
          accountId: attempt.accountId,
          kind: attempt.kind,
          provider: attempt.provider,
          amount: attempt.amount,
        };

  const setVisibleStoredPaymentAttempts = (accountId: string) => {
    const visibleAttempts = listStoredPaymentAttemptsForAccount(accountId).filter((attempt) =>
      isStoredPaymentAttemptActive(attempt)
    );
    setCheckoutAttempts(visibleAttempts);
    return visibleAttempts;
  };

  const reconcileStoredPaymentAttempt = async (
    token: string,
    attempt: StoredPaymentAttempt
  ): Promise<{
    activeAttempt: StoredPaymentAttempt | null;
    finalStatus: StoredPaymentAttemptStatus | null;
  }> => {
    const nowIso = new Date().toISOString();
    let nextAttempt = attempt;

    try {
      const snapshot = await loadPaymentStatusSnapshot(token, attempt.provider, attempt.providerPaymentId);
      if (snapshot === null) {
        removeStoredPaymentAttempt(getStoredPaymentAttemptMatch(attempt));
        return {
          activeAttempt: null,
          finalStatus: isStoredPaymentAttemptActive(attempt) ? 'failed' : getEffectiveStoredPaymentAttemptStatus(attempt),
        };
      }

      nextAttempt = {
        ...attempt,
        status: snapshot.status as StoredPaymentAttemptStatus,
        confirmationUrl: snapshot.confirmation_url || attempt.confirmationUrl,
        expiresAt: snapshot.expires_at || attempt.expiresAt,
        updatedAt: nowIso,
      };
    } catch (err) {
      console.error('Payment status sync error:', err);
      const fallbackStatus = getEffectiveStoredPaymentAttemptStatus(attempt);
      if (!isStoredPaymentAttemptActive({ ...attempt, status: fallbackStatus })) {
        removeStoredPaymentAttempt(getStoredPaymentAttemptMatch(attempt));
        return {
          activeAttempt: null,
          finalStatus: fallbackStatus,
        };
      }
      upsertStoredPaymentAttempt(attempt);
      return {
        activeAttempt: attempt,
        finalStatus: null,
      };
    }

    const effectiveStatus = getEffectiveStoredPaymentAttemptStatus(nextAttempt);
    if (effectiveStatus !== nextAttempt.status) {
      nextAttempt = {
        ...nextAttempt,
        status: effectiveStatus,
        updatedAt: nowIso,
      };
    }

    if (isStoredPaymentAttemptActive(nextAttempt) && nextAttempt.confirmationUrl) {
      upsertStoredPaymentAttempt(nextAttempt);
      return {
        activeAttempt: nextAttempt,
        finalStatus: null,
      };
    }

    removeStoredPaymentAttempt(getStoredPaymentAttemptMatch(nextAttempt));
    return {
      activeAttempt: null,
      finalStatus: nextAttempt.confirmationUrl ? nextAttempt.status : 'failed',
    };
  };

  const reconcileStoredPaymentAttempts = async (token: string, accountId: string) => {
    const attempts = listStoredPaymentAttemptsForAccount(accountId);
    if (!attempts.length) {
      setCheckoutAttempts([]);
      return [];
    }

    const activeAttempts: StoredPaymentAttempt[] = [];
    for (const attempt of attempts) {
      const result = await reconcileStoredPaymentAttempt(token, attempt);
      if (result.activeAttempt) {
        activeAttempts.push(result.activeAttempt);
      }
    }

    replaceStoredPaymentAttemptsForAccount(accountId, activeAttempts);
    setCheckoutAttempts(activeAttempts);
    return activeAttempts;
  };

  const resolveStoredCheckoutAttempt = async (
    token: string,
    match:
      | {
          accountId: string;
          kind: 'plan';
          provider: StoredPaymentAttemptProvider;
          planId: string;
        }
      | {
          accountId: string;
          kind: 'topup';
          provider: StoredPaymentAttemptProvider;
          amount: number;
        }
  ) => {
    const storedAttempt = getStoredPaymentAttempt(match);
    if (!storedAttempt) {
      return {
        activeAttempt: null,
        finalStatus: null,
      };
    }

    return reconcileStoredPaymentAttempt(token, storedAttempt);
  };

  const persistCheckoutAttempt = (
    paymentIntent: BackendPaymentIntent,
    checkout:
      | {
          kind: 'plan';
          planId: string;
          planName: string;
        }
      | {
          kind: 'topup';
        }
  ) => {
    if (
      (paymentIntent.provider !== 'yookassa' && paymentIntent.provider !== 'telegram_stars') ||
      !paymentIntent.confirmation_url
    ) {
      return;
    }

    const nowIso = new Date().toISOString();
    const nextAttempt: StoredPaymentAttempt = {
      accountId: paymentIntent.account_id,
      kind: checkout.kind,
      provider: paymentIntent.provider,
      amount: paymentIntent.amount,
      currency: paymentIntent.currency,
      providerPaymentId: paymentIntent.provider_payment_id,
      confirmationUrl: paymentIntent.confirmation_url,
      status: paymentIntent.status as StoredPaymentAttemptStatus,
      expiresAt: paymentIntent.expires_at ?? null,
      createdAt: nowIso,
      updatedAt: nowIso,
      ...(checkout.kind === 'plan'
        ? {
            planId: checkout.planId,
            planName: checkout.planName,
          }
        : {}),
    };

    upsertStoredPaymentAttempt(nextAttempt);
    if (user?.id === paymentIntent.account_id) {
      setVisibleStoredPaymentAttempts(paymentIntent.account_id);
    }
    if (accessToken) {
      void loadActivePayments(accessToken, { silent: true });
    }
  };

  const describeClosedPaymentAttempt = (
    status: StoredPaymentAttemptStatus,
    options: {
      successMessage: string;
      retryMessage: string;
    }
  ) => {
    if (status === 'succeeded') {
      return options.successMessage;
    }
    if (status === 'cancelled') {
      return 'Предыдущая попытка оплаты была отменена. Создаем новую.';
    }
    if (status === 'expired') {
      return 'Предыдущая ссылка на оплату уже истекла. Создаем новую.';
    }
    if (status === 'failed') {
      return 'Предыдущая попытка оплаты завершилась ошибкой. Создаем новую.';
    }
    return options.retryMessage;
  };

  const markCheckoutAttemptStatus = (
    attempt: StoredPaymentAttempt,
    status: StoredPaymentAttemptStatus
  ) => {
    if (status === 'cancelled' || status === 'failed' || status === 'succeeded' || status === 'expired') {
      removeStoredPaymentAttempt(getStoredPaymentAttemptMatch(attempt));
    } else {
      upsertStoredPaymentAttempt({
        ...attempt,
        status,
        updatedAt: new Date().toISOString(),
      });
    }
    setVisibleStoredPaymentAttempts(attempt.accountId);
    if (accessToken) {
      void loadActivePayments(accessToken, { silent: true });
    }
  };

  const isPasswordRecoveryRequested = () => {
    const url = new URL(window.location.href);
    return url.searchParams.get('auth_action') === 'reset-password';
  };

  const clearAuthActionParam = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete('auth_action');
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  };

  const applyTelegramTheme = (nextTheme: 'light' | 'dark') => {
    const tg = getTelegramWebApp();
    if (!tg) {
      return;
    }

    try {
      tg.setHeaderColor?.(nextTheme === 'dark' ? '#0f172a' : '#ffffff');
    } catch (err) {
      console.error('Telegram header theme update error:', err);
    }

    try {
      tg.setBottomBarColor?.(nextTheme === 'dark' ? '#0f172a' : '#ffffff');
    } catch (err) {
      console.error('Telegram bottom bar theme update error:', err);
    }
  };

  const getRecoveryCallbackState = () => {
    const url = new URL(window.location.href);
    const hashValue = window.location.hash.startsWith('#')
      ? window.location.hash.slice(1)
      : window.location.hash;
    const hashParams = new URLSearchParams(hashValue);

    return {
      code: url.searchParams.get('code'),
      tokenHash: url.searchParams.get('token_hash') || hashParams.get('token_hash'),
      type: url.searchParams.get('type') || hashParams.get('type'),
      accessToken: hashParams.get('access_token'),
      refreshToken: hashParams.get('refresh_token'),
    };
  };

  const clearRecoveryCallbackState = (options: { clearHash?: boolean } = {}) => {
    const url = new URL(window.location.href);
    url.searchParams.delete('code');
    url.searchParams.delete('token_hash');
    url.searchParams.delete('type');

    if (options.clearHash) {
      url.hash = '';
    }

    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  };

  const getBrowserLinkCallbackState = () => {
    const url = new URL(window.location.href);
    return {
      linkToken: url.searchParams.get('link_token'),
      linkFlow: url.searchParams.get('link_flow'),
    };
  };

  const clearBrowserLinkCallbackState = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete('link_token');
    url.searchParams.delete('link_flow');
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  };

  const markPasswordRecoveryActive = () => {
    window.sessionStorage.setItem(PASSWORD_RECOVERY_STORAGE_KEY, '1');
  };

  const clearPasswordRecoveryActive = () => {
    window.sessionStorage.removeItem(PASSWORD_RECOVERY_STORAGE_KEY);
  };

  const hasPasswordRecoveryActive = () =>
    window.sessionStorage.getItem(PASSWORD_RECOVERY_STORAGE_KEY) === '1';

  // Check if running in Telegram WebApp
  useEffect(() => {
    capturePendingReferralCodeFromUrl();

    const initApp = async () => {
      // Load Telegram script first
      await loadTelegramScript();
      
      const tg = getTelegramWebApp();
      if (tg && tg.initData) {
        // Only treat as Telegram WebApp if it's not desktop web platform
        // Desktop Telegram app has platform='web' but should be treated like browser
        const isMobileWebApp = tg.platform !== 'web';
        setIsTelegramWebApp(isMobileWebApp);
        
        if (isMobileWebApp) {
          setAuthViewMode('default');
          // Apply Telegram theme
          if (tg.colorScheme === 'dark') {
            setTheme('dark');
          } else if (tg.colorScheme === 'light') {
            setTheme('light');
          }
          // Expand the WebApp to full height
          tg.expand();
          // Auto-authenticate Telegram users
          handleTelegramAuth(tg);
        } else {
          // Desktop Telegram app - treat as browser
          setIsTelegramWebApp(false);
          checkSupabaseAuth();
        }
      } else {
        setIsTelegramWebApp(false);
        checkSupabaseAuth();
      }
    };

    initApp();
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const root = window.document.documentElement;
    applyAppThemeVariables(theme);
    root.classList.toggle('dark', theme === 'dark');
    root.classList.toggle('theme-dark', theme === 'dark');
    root.classList.toggle('theme-light', theme === 'light');
    root.style.colorScheme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);

    if (isTelegramWebApp) {
      applyTelegramTheme(theme);
    }
  }, [theme, isTelegramWebApp]);

  useEffect(() => {
    if (!isTelegramWebApp) {
      return;
    }

    const tg = getTelegramWebApp();
    if (!tg?.onEvent) {
      return;
    }

    const handleThemeChanged = () => {
      if (tg.colorScheme === 'dark' || tg.colorScheme === 'light') {
        setTheme(tg.colorScheme);
        applyTelegramTheme(tg.colorScheme);
      }
    };

    tg.onEvent('themeChanged', handleThemeChanged);

    return () => {
      tg.offEvent?.('themeChanged', handleThemeChanged);
    };
  }, [isTelegramWebApp]);

  useEffect(() => {
    if (activeTab === 'home' || activeTab === 'plans' || activeTab === 'referral' || activeTab === 'settings') {
      lastPrimaryTabRef.current = activeTab;
    }
  }, [activeTab]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const mediaQuery = window.matchMedia('(min-width: 1200px)');
    const updateDesktopLayout = (matches: boolean) => {
      setIsDesktopBrowser(!isTelegramWebApp && matches);
    };

    updateDesktopLayout(mediaQuery.matches);

    const listener = (event: MediaQueryListEvent) => {
      updateDesktopLayout(event.matches);
    };

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', listener);
      return () => mediaQuery.removeEventListener('change', listener);
    }

    mediaQuery.addListener(listener);
    return () => mediaQuery.removeListener(listener);
  }, [isTelegramWebApp]);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      return;
    }

    const refreshPendingState = async () => {
      if (!pendingTelegramLinkRefreshRef.current && !pendingPaymentRefreshRef.current) {
        return;
      }

      const hadPendingTelegramRefresh = pendingTelegramLinkRefreshRef.current;
      const hadPendingPaymentRefresh = pendingPaymentRefreshRef.current;
      pendingTelegramLinkRefreshRef.current = false;
      pendingPaymentRefreshRef.current = false;

      const refreshed = await refreshUserData();
      if (!refreshed) {
        pendingTelegramLinkRefreshRef.current = hadPendingTelegramRefresh;
        pendingPaymentRefreshRef.current = hadPendingPaymentRefresh;
      }
    };

    const handleFocus = () => {
      void refreshPendingState();
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void refreshPendingState();
      }
    };

    window.addEventListener('focus', handleFocus);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      window.removeEventListener('focus', handleFocus);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [isAuthenticated, accessToken]);

  useEffect(() => {
    if (!user?.id) {
      setCheckoutAttempts([]);
      return;
    }

    setVisibleStoredPaymentAttempts(user.id);

    if (accessToken) {
      void reconcileStoredPaymentAttempts(accessToken, user.id);
    }
  }, [user?.id, accessToken]);

  const handleTelegramAuth = async (tg: any) => {
    try {
      const telegramUser = tg.initDataUnsafe?.user;
      if (!telegramUser) {
        setIsLoading(false);
        return;
      }

      const storedTelegramAuth = readStoredTelegramAuth();
      if (storedTelegramAuth?.telegramUserId === telegramUser.id) {
        setAccessToken(storedTelegramAuth.accessToken);
        const restored = await loadUserData(storedTelegramAuth.accessToken, telegramUser.photo_url);
        if (restored) {
          setIsAuthenticated(true);
          return;
        }

        clearStoredTelegramAuth();
      } else if (storedTelegramAuth) {
        clearStoredTelegramAuth();
      }

      try {
        const authResponse = await fetch(`${BACKEND_API}/api/v1/auth/telegram/webapp`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: tg.initData }),
        });

        if (!authResponse.ok) {
          const errorData = await authResponse.json().catch(() => null);
          const detail =
            errorData && typeof errorData.detail === 'string'
              ? errorData.detail
              : 'Не удалось подтвердить Telegram-сессию';
          throw new Error(detail);
        }

        const authData = await authResponse.json();
        const backendAccount = authData.account as BackendAccount;
        const referralResult = authData.referral_result as BackendTelegramReferralResult | null;
        setAccessToken(authData.access_token);
        writeStoredTelegramAuth({
          accessToken: authData.access_token,
          telegramUserId: telegramUser.id,
        });

        if (referralResult?.created) {
          toast.success('Реферальная ссылка успешно привязана');
        } else if (referralResult?.reason === 'self_referral') {
          toast.error('Нельзя использовать собственную реферальную ссылку');
        } else if (referralResult?.reason === 'referral_code_not_found') {
          toast.error('Реферальная ссылка недействительна');
        }

        const loaded = await loadUserData(authData.access_token, telegramUser.photo_url);
        if (loaded) {
          setIsAuthenticated(true);
          return;
        }

        setUser(mapBackendAccountToUser(backendAccount, telegramUser.photo_url));
        setSubscription(mapSubscriptionToView(backendAccount, null, null));
        setIsAuthenticated(true);
      } catch (err) {
        clearStoredTelegramAuth();
        setIsAuthenticated(false);
        setUser(null);
        setSubscription(null);
        setPlans([]);
        setNotifications([]);
        setNotificationsTotal(0);
        setNotificationsUnreadCount(0);
        setActivePayments([]);
        setLedgerEntries([]);
        setLedgerEntriesTotal(0);
        attemptedPlansTokenRef.current = null;
        attemptedNotificationsTokenRef.current = null;
        attemptedActivePaymentsTokenRef.current = null;
        attemptedLedgerEntriesTokenRef.current = null;
        setAccessToken(null);
        console.error('Telegram auth error:', err);
        toast.error(
          err instanceof Error ? err.message : 'Не удалось подтвердить Telegram-сессию'
        );
      }
    } catch (err) {
      clearStoredTelegramAuth();
      setIsAuthenticated(false);
      setUser(null);
      setSubscription(null);
      setPlans([]);
      setNotifications([]);
      setNotificationsTotal(0);
      setNotificationsUnreadCount(0);
      setActivePayments([]);
      setLedgerEntries([]);
      setLedgerEntriesTotal(0);
      attemptedPlansTokenRef.current = null;
      attemptedNotificationsTokenRef.current = null;
      attemptedActivePaymentsTokenRef.current = null;
      attemptedLedgerEntriesTokenRef.current = null;
      setAccessToken(null);
      console.error('Telegram auth error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const checkSupabaseAuth = async () => {
    let restored = false;

    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.access_token) {
        restored = await syncBrowserAuth(
          session.access_token,
          getSupabaseAvatarUrl(session.user as SupabaseUserLike)
        );
      } else {
        const cachedToken = window.localStorage.getItem(BROWSER_TOKEN_STORAGE_KEY);
        if (cachedToken) {
          restored = await syncBrowserAuth(cachedToken);
        }
      }
    } catch (err) {
      console.error('Auth check error:', err);
    } finally {
      setIsLoading(false);
    }

    return restored;
  };

  const preparePasswordRecovery = async () => {
    clearBrowserAuthState();
    const recoveryCallbackState = getRecoveryCallbackState();
    const hasRecoveryCallback =
      Boolean(recoveryCallbackState.code) ||
      Boolean(recoveryCallbackState.tokenHash) ||
      Boolean(recoveryCallbackState.accessToken && recoveryCallbackState.refreshToken);
    let lastError: unknown = null;

    try {
      const initializeResult = await supabase.auth.initialize();
      if (initializeResult.error) {
        lastError = initializeResult.error;
      }

      let {
        data: { session },
      } = await supabase.auth.getSession();

      if (!session?.access_token && recoveryCallbackState.code) {
        const { data, error } = await supabase.auth.exchangeCodeForSession(recoveryCallbackState.code);
        if (error) {
          lastError = error;
        } else {
          session = data.session;
          clearRecoveryCallbackState();
        }
      }

      if (
        !session?.access_token &&
        recoveryCallbackState.accessToken &&
        recoveryCallbackState.refreshToken
      ) {
        const { data, error } = await supabase.auth.setSession({
          access_token: recoveryCallbackState.accessToken,
          refresh_token: recoveryCallbackState.refreshToken,
        });
        if (error) {
          lastError = error;
        } else {
          session = data.session;
          clearRecoveryCallbackState({ clearHash: true });
        }
      }

      if (
        !session?.access_token &&
        recoveryCallbackState.tokenHash &&
        recoveryCallbackState.type === 'recovery'
      ) {
        const { data, error } = await supabase.auth.verifyOtp({
          token_hash: recoveryCallbackState.tokenHash,
          type: 'recovery',
        });
        if (error) {
          lastError = error;
        } else {
          session = data.session;
          clearRecoveryCallbackState();
        }
      }

      if (session?.access_token && (hasRecoveryCallback || hasPasswordRecoveryActive())) {
        markPasswordRecoveryActive();
        setAuthViewMode('recovery');
        return;
      }

      if (lastError) {
        console.error('Password recovery preparation error:', lastError);
      }

      clearPasswordRecoveryActive();
      clearAuthActionParam();
      const restored = await checkSupabaseAuth();
      setAuthViewMode(restored ? 'default' : 'recovery-expired');
    } catch (err) {
      console.error('Password recovery preparation error:', err);
      clearPasswordRecoveryActive();
      clearAuthActionParam();
      const restored = await checkSupabaseAuth();
      setAuthViewMode(restored ? 'default' : 'recovery-expired');
    } finally {
      setIsLoading(false);
    }
  };

  // Listen for auth changes
  useEffect(() => {
    const { data: authListener } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        if (event === 'PASSWORD_RECOVERY') {
          setAuthViewMode('recovery');
          clearBrowserAuthState();
          markPasswordRecoveryActive();
          setIsLoading(false);
          return;
        }

        if (authViewRef.current === 'recovery') {
          if (event === 'SIGNED_OUT') {
            if (manualLogoutRef.current) {
              manualLogoutRef.current = false;
            }
            clearBrowserAuthState();
          }
          return;
        }

        if ((event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') && session?.access_token) {
          await syncBrowserAuth(
            session.access_token,
            getSupabaseAvatarUrl(session.user as SupabaseUserLike)
          );
        } else if (event === 'SIGNED_OUT') {
          if (manualLogoutRef.current) {
            manualLogoutRef.current = false;
            clearBrowserAuthState();
            return;
          }

          if (currentBrowserTokenRef.current || lastLoadedBrowserTokenRef.current) {
            return;
          }

          clearBrowserAuthState();
        }
      }
    );

    return () => {
      authListener.subscription.unsubscribe();
    };
  }, []);

  const clearBrowserAuthState = () => {
    setIsAuthenticated(false);
    setUser(null);
    setAccessToken(null);
    setPlans([]);
    setReferralSummary(null);
    setNotifications([]);
    setNotificationsTotal(0);
    setNotificationsUnreadCount(0);
    setActivePayments([]);
    setLedgerEntries([]);
    setLedgerEntriesTotal(0);
    setCheckoutAttempts([]);
    attemptedPlansTokenRef.current = null;
    attemptedNotificationsTokenRef.current = null;
    attemptedActivePaymentsTokenRef.current = null;
    attemptedLedgerEntriesTokenRef.current = null;
    pendingTelegramLinkRefreshRef.current = false;
    pendingPaymentRefreshRef.current = false;
    pendingReferralClaimRef.current = false;
    currentBrowserTokenRef.current = null;
    lastLoadedBrowserTokenRef.current = null;
    inFlightBrowserTokenRef.current = null;
    window.localStorage.removeItem(BROWSER_TOKEN_STORAGE_KEY);
  };

  const syncBrowserAuth = async (token: string, browserAvatar?: string) => {
    if (!token) {
      return false;
    }

    setAccessToken(token);
    currentBrowserTokenRef.current = token;
    window.localStorage.setItem(BROWSER_TOKEN_STORAGE_KEY, token);

    if (lastLoadedBrowserTokenRef.current === token) {
      if (browserAvatar) {
        setUser((currentUser) =>
          currentUser ? { ...currentUser, avatar: browserAvatar } : currentUser
        );
      }
      setIsAuthenticated(true);
      return true;
    }

    if (inFlightBrowserTokenRef.current === token) {
      return false;
    }

    inFlightBrowserTokenRef.current = token;
    const loaded = await loadUserData(token, browserAvatar);
    if (loaded) {
      lastLoadedBrowserTokenRef.current = token;
      setIsAuthenticated(true);
    } else if (currentBrowserTokenRef.current === token) {
      currentBrowserTokenRef.current = null;
      window.localStorage.removeItem(BROWSER_TOKEN_STORAGE_KEY);
    }
    inFlightBrowserTokenRef.current = null;
    return loaded;
  };

  const loadUserData = async (token: string, browserAvatar?: string) => {
    try {
      const bootstrap = await loadBootstrapSnapshot(token);
      const accountData = bootstrap.account;
      const subscriptionData = bootstrap.subscription;
      const trialUi = bootstrap.trial_ui;

      setUser((currentUser) =>
        mapBackendAccountToUser(
          accountData,
          browserAvatar || currentUser?.avatar
        )
      );
      setSubscription(mapSubscriptionToView(accountData, subscriptionData, trialUi));
      setVisibleStoredPaymentAttempts(accountData.id);
      void reconcileStoredPaymentAttempts(token, accountData.id);
      void loadNotificationsUnreadCount(token);
      void loadActivePayments(token, { silent: true });

      return true;
    } catch (err) {
      console.error('Error loading user data:', err);
      return false;
    }
  };

  const loadPlans = async (token: string) => {
    attemptedPlansTokenRef.current = token;
    setIsLoadingPlans(true);

    try {
      const planData = await loadPlansSnapshot(token);
      setPlans(planData.map(mapBackendPlanToView));
      return true;
    } catch (err) {
      console.error('Error loading plans:', err);
      setPlans([]);
      return false;
    } finally {
      setIsLoadingPlans(false);
    }
  };

  const loadReferralSummary = async (token: string) => {
    setIsLoadingReferralSummary(true);

    try {
      const summary = await loadReferralSummarySnapshot(token);
      setReferralSummary(summary);
      return true;
    } catch (err) {
      console.error('Error loading referral summary:', err);
      return false;
    } finally {
      setIsLoadingReferralSummary(false);
    }
  };

  const loadNotifications = async (
    token: string,
    options: { offset?: number; append?: boolean; silent?: boolean } = {}
  ) => {
    const offset = options.offset ?? 0;
    const append = options.append ?? false;
    const silent = options.silent ?? false;

    if (append) {
      setIsLoadingMoreNotifications(true);
    } else if (!silent) {
      setIsLoadingNotifications(true);
    }

    if (!append) {
      attemptedNotificationsTokenRef.current = token;
    }

    try {
      const snapshot = await loadNotificationsSnapshot(token, { limit: 20, offset });
      const mappedItems = snapshot.items.map(mapBackendNotificationToView);
      setNotifications((current) => {
        if (!append) {
          return mappedItems;
        }

        const merged = [...current];
        for (const item of mappedItems) {
          const index = merged.findIndex((existing) => existing.id === item.id);
          if (index >= 0) {
            merged[index] = item;
          } else {
            merged.push(item);
          }
        }
        return merged;
      });
      setNotificationsTotal(snapshot.total);
      setNotificationsUnreadCount(snapshot.unread_count);
      return true;
    } catch (err) {
      console.error('Error loading notifications:', err);
      if (!append) {
        setNotifications([]);
        setNotificationsTotal(0);
      }
      return false;
    } finally {
      if (append) {
        setIsLoadingMoreNotifications(false);
      } else if (!silent) {
        setIsLoadingNotifications(false);
      }
    }
  };

  const loadNotificationsUnreadCount = async (token: string) => {
    try {
      const snapshot = await loadNotificationsUnreadCountSnapshot(token);
      setNotificationsUnreadCount(snapshot.unread_count);
      return snapshot.unread_count;
    } catch (err) {
      console.error('Error loading notifications unread count:', err);
      return null;
    }
  };

  const loadActivePayments = async (
    token: string,
    options: { silent?: boolean } = {}
  ) => {
    attemptedActivePaymentsTokenRef.current = token;
    if (!options.silent) {
      setIsLoadingActivePayments(true);
    }

    try {
      const snapshot = await loadActivePaymentsSnapshot(token);
      setActivePayments(snapshot.items.map((item) => mapBackendPaymentItemToView(item, plans)));
      return true;
    } catch (err) {
      console.error('Error loading active payments:', err);
      if (!options.silent) {
        setActivePayments([]);
      }
      return false;
    } finally {
      if (!options.silent) {
        setIsLoadingActivePayments(false);
      }
    }
  };

  const loadLedgerEntries = async (
    token: string,
    options: { offset?: number; append?: boolean; silent?: boolean } = {}
  ) => {
    const offset = options.offset ?? 0;
    const append = options.append ?? false;
    const silent = options.silent ?? false;

    attemptedLedgerEntriesTokenRef.current = token;
    if (append) {
      setIsLoadingMoreLedgerEntries(true);
    } else if (!silent) {
      setIsLoadingLedgerEntries(true);
    }

    try {
      const snapshot = await loadLedgerEntriesSnapshot(token, { limit: 20, offset });
      const mappedItems = snapshot.items.map(mapBackendLedgerEntryToView);
      setLedgerEntries((current) => {
        if (!append) {
          return mappedItems;
        }

        const merged = [...current];
        for (const item of mappedItems) {
          const index = merged.findIndex((existing) => existing.id === item.id);
          if (index >= 0) {
            merged[index] = item;
          } else {
            merged.push(item);
          }
        }
        return merged;
      });
      setLedgerEntriesTotal(snapshot.total);
      return true;
    } catch (err) {
      console.error('Error loading ledger entries:', err);
      if (!append) {
        setLedgerEntries([]);
        setLedgerEntriesTotal(0);
      }
      return false;
    } finally {
      if (append) {
        setIsLoadingMoreLedgerEntries(false);
      } else if (!silent) {
        setIsLoadingLedgerEntries(false);
      }
    }
  };

  const handleOpenNotificationsTab = () => {
    setActiveTab('notifications');
    if (accessToken) {
      void loadNotifications(accessToken);
    }
  };

  const handleOpenPendingPayments = () => {
    setActiveTab('payments');
    if (accessToken) {
      void loadActivePayments(accessToken);
    }
  };

  const handleOpenBalanceHistory = () => {
    setActiveTab('balance-history');
    if (accessToken) {
      void loadLedgerEntries(accessToken);
    }
  };

  const handleOpenSubscriptionAccess = () => {
    const subscriptionUrl = subscription?.subscriptionUrl?.trim();
    if (!subscriptionUrl) {
      toast.error('Ссылка подписки пока недоступна');
      return;
    }

    if (isTelegramWebApp) {
      window.location.assign(subscriptionUrl);
      return;
    }

    const popup = window.open(subscriptionUrl, '_blank', 'noopener,noreferrer');
    if (!popup) {
      window.location.assign(subscriptionUrl);
    }
  };

  const handleTabChange = (tab: string) => {
    const resolvedTab = tab as AppTab;
    setActiveTab(resolvedTab);
    if (resolvedTab === 'notifications' && accessToken) {
      void loadNotifications(accessToken);
    }
  };

  const handleOpenFaq = () => {
    setActiveTab('faq');
  };

  const handleOpenPrivacy = () => {
    setActiveTab('privacy');
  };

  const handleOpenTerms = () => {
    setActiveTab('terms');
  };

  const handleBackToPrimaryTab = () => {
    setActiveTab(lastPrimaryTabRef.current);
  };

  const handleBackToSettings = () => {
    setActiveTab('settings');
  };

  const handleOpenSupport = () => {
    if (!SUPPORT_TELEGRAM_URL) {
      toast.error('Не настроена ссылка на Telegram-поддержку');
      return;
    }

    if (
      (SUPPORT_TELEGRAM_URL.startsWith('https://t.me/') || SUPPORT_TELEGRAM_URL.startsWith('tg://')) &&
      openTelegramLink(SUPPORT_TELEGRAM_URL)
    ) {
      return;
    }

    const popup = window.open(SUPPORT_TELEGRAM_URL, '_blank', 'noopener,noreferrer');
    if (!popup) {
      window.location.assign(SUPPORT_TELEGRAM_URL);
    }
  };

  const markNotificationRead = async (notificationId: number) => {
    if (!accessToken) {
      return;
    }

    const target = notifications.find((notification) => notification.id === notificationId);
    if (!target || target.isRead) {
      return;
    }

    setIsUpdatingNotificationReadState(true);
    setNotifications((current) =>
      current.map((notification) =>
        notification.id === notificationId ? { ...notification, isRead: true } : notification
      )
    );
    setNotificationsUnreadCount((current) => Math.max(0, current - 1));

    try {
      const response = await fetch(`${BACKEND_API}/api/v1/notifications/${notificationId}/read`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (!response.ok) {
        throw new Error('Не удалось отметить уведомление как прочитанное');
      }
    } catch (err) {
      console.error('Mark notification read error:', err);
      toast.error(err instanceof Error ? err.message : 'Не удалось обновить уведомление');
      await loadNotifications(accessToken, { silent: true });
    } finally {
      setIsUpdatingNotificationReadState(false);
    }
  };

  const markAllNotificationsRead = async () => {
    if (!accessToken || notificationsUnreadCount === 0) {
      return;
    }

    setIsUpdatingNotificationReadState(true);
    setNotifications((current) => current.map((notification) => ({ ...notification, isRead: true })));
    setNotificationsUnreadCount(0);

    try {
      const response = await fetch(`${BACKEND_API}/api/v1/notifications/read-all`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (!response.ok) {
        throw new Error('Не удалось отметить все уведомления как прочитанные');
      }
    } catch (err) {
      console.error('Mark all notifications read error:', err);
      toast.error(err instanceof Error ? err.message : 'Не удалось обновить уведомления');
      await loadNotifications(accessToken, { silent: true });
    } finally {
      setIsUpdatingNotificationReadState(false);
    }
  };

  const handleNotificationAction = (
    notification: NotificationItemView,
    action?: { label: string; url: string }
  ) => {
    const targetUrl = action?.url ?? notification.actionUrl;
    if (targetUrl) {
      const internalTabByUrl: Partial<Record<string, AppTab>> = {
        '/': 'home',
        '/plans': 'plans',
        '/notifications': 'notifications',
        '/payments': 'payments',
        '/balance-history': 'balance-history',
        '/referral': 'referral',
        '/settings': 'settings',
        '/faq': 'faq',
        '/privacy': 'privacy',
        '/terms': 'terms',
      };
      const internalTab = internalTabByUrl[targetUrl];
      if (internalTab) {
        setActiveTab(internalTab);
      } else if (targetUrl.startsWith('https://t.me/') || targetUrl.startsWith('tg://')) {
        if (!openTelegramLink(targetUrl)) {
          window.open(targetUrl, '_blank', 'noopener,noreferrer');
        }
      } else {
        window.open(targetUrl, '_blank', 'noopener,noreferrer');
      }
    }

    if (!notification.isRead) {
      void markNotificationRead(notification.id);
    }
  };

  const handleLoadMoreNotifications = () => {
    if (!accessToken || notifications.length >= notificationsTotal) {
      return;
    }

    void loadNotifications(accessToken, {
      offset: notifications.length,
      append: true,
    });
  };

  const handleLoadMoreLedgerEntries = () => {
    if (!accessToken || ledgerEntries.length >= ledgerEntriesTotal) {
      return;
    }

    void loadLedgerEntries(accessToken, {
      offset: ledgerEntries.length,
      append: true,
    });
  };

  const handleResumePendingPayment = (payment: PendingPaymentView) => {
    if (!payment.confirmationUrl) {
      toast.error('Ссылка оплаты уже недоступна');
      return;
    }

    const localAttempt = checkoutAttempts.find(
      (attempt) =>
        attempt.provider === payment.provider &&
        attempt.providerPaymentId === payment.providerPaymentId
    );

    openCheckoutConfirmation(payment.confirmationUrl, {
      provider: payment.provider,
      onPaid: () => {
        if (accessToken) {
          void loadActivePayments(accessToken, { silent: true });
        }
      },
      onStatusChange: (status) => {
        if (localAttempt && (status === 'paid' || status === 'cancelled' || status === 'failed')) {
          markCheckoutAttemptStatus(
            localAttempt,
            (status === 'paid' ? 'succeeded' : status) as StoredPaymentAttemptStatus
          );
        }
        if (accessToken && (status === 'paid' || status === 'cancelled' || status === 'failed')) {
          void loadActivePayments(accessToken, { silent: true });
        }
      },
    });
  };

  const claimPendingReferralCode = async (token: string) => {
    const referralCode = readPendingReferralCode();
    if (!referralCode) {
      return false;
    }

    try {
      const response = await fetch(`${BACKEND_API}/api/v1/referrals/claim`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ referral_code: referralCode }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const detail =
          errorData && typeof errorData.detail === 'string'
            ? errorData.detail
            : 'Не удалось привязать реферальную ссылку';

        if (
          detail === 'referral already claimed' ||
          detail === 'referral attribution is closed after the first paid purchase'
        ) {
          clearPendingReferralCode();
          return false;
        }

        if (detail === 'self referral is not allowed') {
          clearPendingReferralCode();
          toast.error('Нельзя использовать собственную реферальную ссылку');
          return false;
        }

        if (detail === 'referral code not found') {
          clearPendingReferralCode();
          toast.error('Реферальная ссылка недействительна');
          return false;
        }

        throw new Error(detail);
      }

      const payload = (await response.json()) as { created: boolean };
      clearPendingReferralCode();
      if (payload.created) {
        toast.success('Реферальная ссылка успешно привязана');
      }
      return payload.created;
    } catch (err) {
      console.error('Referral claim error:', err);
      return false;
    }
  };

  const openCheckoutConfirmation = (
    confirmationUrl: string,
    options: {
      provider?: string;
      onPaid?: () => void;
      onStatusChange?: (status: string) => void;
    } = {}
  ) => {
    pendingPaymentRefreshRef.current = true;

    if (options.provider === 'telegram_stars' && isTelegramWebApp) {
      const opened = openTelegramInvoice(confirmationUrl, (status) => {
        options.onStatusChange?.(status);
        if (status === 'paid') {
          pendingPaymentRefreshRef.current = false;
          void refreshUserData();
          options.onPaid?.();
        } else if (status === 'cancelled' || status === 'failed') {
          pendingPaymentRefreshRef.current = false;
        }
      });
      if (opened) {
        return;
      }
    }

    if (isTelegramWebApp) {
      const tg = getTelegramWebApp();
      if (tg?.openLink) {
        tg.openLink(confirmationUrl, { try_browser: true });
        return;
      }
    }

    window.location.assign(confirmationUrl);
  };

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      return;
    }

    if (!isDesktopBrowser && activeTab !== 'plans') {
      return;
    }

    if (plans.length || isLoadingPlans || attemptedPlansTokenRef.current === accessToken) {
      return;
    }

    void loadPlans(accessToken);
  }, [isAuthenticated, accessToken, activeTab, isDesktopBrowser, plans.length, isLoadingPlans]);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      return;
    }

    if (attemptedActivePaymentsTokenRef.current === accessToken) {
      return;
    }

    void loadActivePayments(accessToken, { silent: true });
  }, [isAuthenticated, accessToken]);

  useEffect(() => {
    if (!plans.length) {
      return;
    }

    setActivePayments((current) =>
      current.map((payment) => ({
        ...payment,
        planName: payment.planName || resolvePlanName(payment.planCode, plans),
      }))
    );
  }, [plans]);

  useEffect(() => {
    if (!isAuthenticated || !accessToken || activeTab !== 'payments') {
      return;
    }

    void loadActivePayments(accessToken);
  }, [isAuthenticated, accessToken, activeTab]);

  useEffect(() => {
    if (!isAuthenticated || !accessToken || activeTab !== 'balance-history') {
      return;
    }

    void loadLedgerEntries(accessToken);
  }, [isAuthenticated, accessToken, activeTab]);

  useEffect(() => {
    if (!isAuthenticated || !accessToken || !user) {
      return;
    }

    const pendingReferralCode = readPendingReferralCode();
    if (!pendingReferralCode) {
      return;
    }

    if (user.referredByAccountId) {
      clearPendingReferralCode();
      return;
    }

    if (pendingReferralClaimRef.current) {
      return;
    }

    pendingReferralClaimRef.current = true;
    void (async () => {
      const claimed = await claimPendingReferralCode(accessToken);
      if (claimed) {
        await loadUserData(accessToken, user.avatar);
      }
    })().finally(() => {
      pendingReferralClaimRef.current = false;
    });
  }, [isAuthenticated, accessToken, user]);

  useEffect(() => {
    if (!isAuthenticated || !accessToken || !user) {
      return;
    }

    if (!isDesktopBrowser && activeTab !== 'referral') {
      return;
    }

    if (isLoadingReferralSummary) {
      return;
    }

    const shouldReload =
      !referralSummary ||
      referralSummary.referral_code !== (user.referralCode || '') ||
      referralSummary.referrals_count !== (user.referralsCount || 0) ||
      referralSummary.referral_earnings !== (user.referralEarnings || 0);

    if (!shouldReload) {
      return;
    }

    void loadReferralSummary(accessToken);
  }, [
    isAuthenticated,
    accessToken,
    user,
    activeTab,
    isDesktopBrowser,
    referralSummary,
    isLoadingReferralSummary,
  ]);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      return;
    }

    if (attemptedNotificationsTokenRef.current === accessToken) {
      return;
    }

    if (isDesktopBrowser || activeTab === 'notifications') {
      void loadNotifications(accessToken, { silent: isDesktopBrowser });
      return;
    }

    void loadNotificationsUnreadCount(accessToken);
  }, [
    isAuthenticated,
    accessToken,
    activeTab,
    isDesktopBrowser,
  ]);

  const handleTopUp = async () => {
    setIsTopUpModalOpen(true);
  };

  const attachPaymentAttemptNotes = (
    selection:
      | {
          kind: 'plan';
          planId: string;
        }
      | {
          kind: 'topup';
          amount: number;
        },
    methods: PaymentMethodOption[]
  ) =>
    methods.map((method) => {
      if (method.provider !== 'yookassa' && method.provider !== 'telegram_stars') {
        return method;
      }

      const matchingAttempt =
        selection.kind === 'plan'
          ? checkoutAttempts.find(
              (attempt) =>
                attempt.kind === 'plan' &&
                attempt.planId === selection.planId &&
                attempt.provider === method.provider
            )
          : checkoutAttempts.find(
              (attempt) =>
                attempt.kind === 'topup' &&
                attempt.amount === selection.amount &&
                attempt.provider === method.provider
            );

      if (!matchingAttempt) {
        return method;
      }

      const continuationNote =
        selection.kind === 'plan'
          ? 'Есть незавершенная оплата. Откроем текущую попытку, пока срок не истек.'
          : `Есть незавершенное пополнение на ${formatRubles(matchingAttempt.amount)} ₽. Откроем его повторно, пока срок не истек.`;

      return {
        ...method,
        note: method.note ? `${method.note} ${continuationNote}` : continuationNote,
      };
    });

  const createTopUpPayment = async (amount: number, provider: PaymentMethodProvider) => {
    if (!accessToken || !user) return;
    if (provider !== 'yookassa') {
      throw new Error('Этот способ пополнения пока не поддерживается.');
    }

    const resumableAttempt = await resolveStoredCheckoutAttempt(accessToken, {
      accountId: user.id,
      kind: 'topup',
      provider,
      amount,
    });

    if (resumableAttempt.activeAttempt) {
      setIsTopUpModalOpen(false);
      toast.success('Открываем незавершенное пополнение');
      openCheckoutConfirmation(resumableAttempt.activeAttempt.confirmationUrl, {
        provider: resumableAttempt.activeAttempt.provider,
        onStatusChange: (status) => {
          if (status === 'paid') {
            markCheckoutAttemptStatus(resumableAttempt.activeAttempt, 'succeeded');
            return;
          }
          if (status === 'cancelled' || status === 'failed') {
            markCheckoutAttemptStatus(
              resumableAttempt.activeAttempt,
              status as StoredPaymentAttemptStatus
            );
            toast.error(status === 'cancelled' ? 'Оплата была отменена.' : 'Оплата завершилась ошибкой.');
          }
        },
      });
      return;
    }

    if (resumableAttempt.finalStatus) {
      const message = describeClosedPaymentAttempt(resumableAttempt.finalStatus, {
        successMessage: 'Предыдущее пополнение уже завершено. Обновляем баланс.',
        retryMessage: 'Создаем новую попытку оплаты.',
      });
      if (resumableAttempt.finalStatus === 'succeeded') {
        toast.success(message);
        await refreshUserData();
        return;
      }
      toast.error(message);
    }

    setIsTopUpSubmitting(true);

    try {
      const response = await fetch(`${BACKEND_API}/api/v1/payments/yookassa/topup`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          amount_rub: amount,
          success_url: getPaymentReturnUrl({ preferTelegramBot: isTelegramWebApp }),
          description: `Пополнение баланса на ${formatRubles(amount)} ₽`,
          idempotency_key: createClientIdempotencyKey('topup'),
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const detail =
          errorData && typeof errorData.detail === 'string'
            ? getPaymentErrorMessage(errorData.detail)
            : 'Не удалось создать платёж на пополнение';
        throw new Error(detail);
      }

      const paymentIntent = (await response.json()) as BackendPaymentIntent;
      if (!paymentIntent.confirmation_url) {
        throw new Error('Платёж создан без ссылки на подтверждение');
      }

      persistCheckoutAttempt(paymentIntent, { kind: 'topup' });
      setIsTopUpModalOpen(false);
      toast.success('Открываем YooKassa для пополнения');
      openCheckoutConfirmation(paymentIntent.confirmation_url, {
        provider: paymentIntent.provider,
      });
    } catch (err) {
      console.error('Top-up payment error:', err);
      toast.error(err instanceof Error ? err.message : 'Не удалось создать платёж');
    } finally {
      setIsTopUpSubmitting(false);
    }
  };

  const handleTopUpAmount = async (amount: number) => {
    const methods = attachPaymentAttemptNotes(
      { kind: 'topup', amount },
      getAvailableTopUpPaymentMethods(isTelegramWebApp)
    );

    if (methods.length === 1) {
      await createTopUpPayment(amount, methods[0].provider);
      return;
    }

    setIsTopUpModalOpen(false);
    setPaymentMethodSelection({
      kind: 'topup',
      amount,
      methods,
    });
  };

  const handleActivateTrial = async () => {
    if (!accessToken) return;

    try {
      const response = await fetch(`${BACKEND_API}/api/v1/subscriptions/trial`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const detail =
          errorData && typeof errorData.detail === 'string'
            ? getTrialErrorMessage(errorData.detail)
            : 'Не удалось активировать пробный период';
        throw new Error(detail);
      }

      const reloaded = await loadUserData(accessToken, user?.avatar);
      if (!reloaded) {
        throw new Error('Пробный период активирован, но не удалось обновить профиль');
      }

      toast.success('Пробный период активирован');
    } catch (err) {
      console.error('Trial activation error:', err);
      toast.error(err instanceof Error ? err.message : 'Не удалось активировать пробный период');
    }
  };

  const createPlanPayment = async (planId: string, provider: PaymentMethodProvider) => {
    if (!accessToken || !user) return;

    const selectedPlan = plans.find((plan) => plan.id === planId);
    if (!selectedPlan) {
      throw new Error('Выбранный тариф не найден.');
    }

    setCheckoutPlanId(planId);

    try {
      if (provider === 'wallet') {
        const response = await fetch(
          `${BACKEND_API}/api/v1/subscriptions/wallet/plans/${encodeURIComponent(planId)}`,
          {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${accessToken}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              idempotency_key: createClientIdempotencyKey(`wallet-plan-${planId}`),
            }),
          }
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => null);
          const detail =
            errorData && typeof errorData.detail === 'string'
              ? getPaymentErrorMessage(errorData.detail)
              : 'Не удалось купить тариф с баланса';
          throw new Error(detail);
        }

        const reloaded = await loadUserData(accessToken, user?.avatar);
        if (!reloaded) {
          throw new Error('Тариф активирован, но не удалось обновить профиль');
        }

        toast.success('Тариф активирован с баланса');
        return;
      }

      if (provider === 'telegram_stars' && !selectedPlan.priceStars) {
        throw new Error('Для этого тарифа пока не настроена цена в Telegram Stars.');
      }

      if (provider === 'yookassa' || provider === 'telegram_stars') {
        const resumableAttempt = await resolveStoredCheckoutAttempt(accessToken, {
          accountId: user.id,
          kind: 'plan',
          provider,
          planId,
        });

        if (resumableAttempt.activeAttempt) {
          toast.success('Открываем незавершенную оплату тарифа');
          openCheckoutConfirmation(resumableAttempt.activeAttempt.confirmationUrl, {
            provider: resumableAttempt.activeAttempt.provider,
            onPaid: () => toast.success('Платёж подтверждён. Обновляем подписку.'),
            onStatusChange: (status) => {
              if (status === 'paid') {
                markCheckoutAttemptStatus(resumableAttempt.activeAttempt, 'succeeded');
                return;
              }
              if (status === 'cancelled' || status === 'failed') {
                markCheckoutAttemptStatus(
                  resumableAttempt.activeAttempt,
                  status as StoredPaymentAttemptStatus
                );
                toast.error(
                  status === 'cancelled' ? 'Оплата тарифа была отменена.' : 'Оплата тарифа завершилась ошибкой.'
                );
              }
            },
          });
          return;
        }

        if (resumableAttempt.finalStatus) {
          const message = describeClosedPaymentAttempt(resumableAttempt.finalStatus, {
            successMessage: 'Предыдущая оплата тарифа уже завершена. Обновляем подписку.',
            retryMessage: 'Создаем новую попытку оплаты тарифа.',
          });
          if (resumableAttempt.finalStatus === 'succeeded') {
            toast.success(message);
            await refreshUserData();
            return;
          }
          toast.error(message);
        }
      }

      const useTelegramStars = provider === 'telegram_stars';
      const endpoint = useTelegramStars
        ? `${BACKEND_API}/api/v1/payments/telegram-stars/plans/${encodeURIComponent(planId)}`
        : `${BACKEND_API}/api/v1/payments/yookassa/plans/${encodeURIComponent(planId)}`;
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          description: selectedPlan ? `Оплата тарифа ${selectedPlan.name}` : `Оплата тарифа ${planId}`,
          idempotency_key: createClientIdempotencyKey(`plan-${planId}`),
          ...(useTelegramStars
            ? {}
            : { success_url: getPaymentReturnUrl({ preferTelegramBot: isTelegramWebApp }) }),
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const detail =
          errorData && typeof errorData.detail === 'string'
            ? getPaymentErrorMessage(errorData.detail)
            : 'Не удалось создать платёж на покупку тарифа';
        throw new Error(detail);
      }

      const paymentIntent = (await response.json()) as BackendPaymentIntent;
      if (!paymentIntent.confirmation_url) {
        throw new Error('Платёж создан без ссылки на подтверждение');
      }

      persistCheckoutAttempt(paymentIntent, {
        kind: 'plan',
        planId,
        planName: selectedPlan.name,
      });
      toast.success(
        useTelegramStars ? 'Открываем оплату в Telegram Stars' : 'Открываем YooKassa для оплаты тарифа'
      );
      openCheckoutConfirmation(paymentIntent.confirmation_url, {
        provider: paymentIntent.provider,
        onPaid: () => toast.success('Платёж подтверждён. Обновляем подписку.'),
        onStatusChange: (status) => {
          if (status !== 'paid' && status !== 'cancelled' && status !== 'failed') {
            return;
          }

          const activeAttempt = getStoredPaymentAttempt({
            accountId: paymentIntent.account_id,
            kind: 'plan',
            provider: paymentIntent.provider as StoredPaymentAttemptProvider,
            planId,
          });

          if (!activeAttempt) {
            return;
          }

          if (status === 'paid') {
            markCheckoutAttemptStatus(activeAttempt, 'succeeded');
            return;
          }

          markCheckoutAttemptStatus(activeAttempt, status as StoredPaymentAttemptStatus);
          toast.error(
            status === 'cancelled' ? 'Оплата тарифа была отменена.' : 'Оплата тарифа завершилась ошибкой.'
          );
        },
      });
    } catch (err) {
      console.error('Plan payment error:', err);
      toast.error(err instanceof Error ? err.message : 'Не удалось создать платёж');
    } finally {
      setCheckoutPlanId(null);
    }
  };

  const handleBuyPlan = async (planId: string) => {
    const selectedPlan = plans.find((plan) => plan.id === planId);
    if (!selectedPlan) {
      toast.error('Выбранный тариф не найден.');
      return;
    }

    const methods = attachPaymentAttemptNotes(
      { kind: 'plan', planId },
      getAvailablePlanPaymentMethods(selectedPlan, isTelegramWebApp, user?.balance ?? 0)
    );

    if (!methods.length) {
      toast.error('Для этого тарифа пока не настроен ни один способ оплаты.');
      return;
    }

    if (methods.length === 1) {
      await createPlanPayment(planId, methods[0].provider);
      return;
    }

    setPaymentMethodSelection({
      kind: 'plan',
      planId,
      planName: selectedPlan.name,
      methods,
    });
  };

  const handlePaymentMethodSelect = async (provider: PaymentMethodProvider) => {
    if (!paymentMethodSelection) {
      return;
    }

    const selection = paymentMethodSelection;
    setPaymentMethodSelection(null);
    setPaymentMethodSubmitting(provider);

    try {
      if (selection.kind === 'plan') {
        await createPlanPayment(selection.planId, provider);
        return;
      }

      await createTopUpPayment(selection.amount, provider);
    } finally {
      setPaymentMethodSubmitting(null);
    }
  };

  const handleCopyReferral = () => {
    if (user?.referralCode) {
      const referralLink = buildBrowserReferralLink(user.referralCode);
      if (!referralLink) {
        toast.error('Не удалось подготовить реферальную ссылку');
        return;
      }

      void navigator.clipboard
        .writeText(referralLink)
        .then(() => {
          setReferralCopied(true);
          toast.success('Реферальная ссылка скопирована');
          window.setTimeout(() => setReferralCopied(false), 2000);
        })
        .catch((err) => {
          console.error('Referral copy error:', err);
          toast.error('Не удалось скопировать ссылку');
        });
    }
  };

  const handleShareReferralToTelegram = () => {
    if (!user?.referralCode) {
      return;
    }

    const shareUrl = buildTelegramShareReferralUrl(user.referralCode);
    if (!shareUrl) {
      toast.error('Не настроена ссылка на Telegram-бота');
      return;
    }

    if (isTelegramWebApp && openTelegramLink(shareUrl)) {
      return;
    }

    const popup = window.open(shareUrl, '_blank', 'noopener,noreferrer');
    if (!popup) {
      window.location.assign(shareUrl);
    }
  };

  const handleWithdraw = async () => {
    if (!accessToken) return;
    toast.error('Вывод пока не перенесен на новый API.');
  };

  const handleLogout = async () => {
    manualLogoutRef.current = true;
    clearPasswordRecoveryActive();
    clearBrowserLinkCallbackState();
    await supabase.auth.signOut();
    clearBrowserAuthState();
  };

  const handleLinkTelegram = async () => {
    if (!accessToken) {
      toast.error('Необходимо войти в аккаунт');
      return;
    }

    try {
      const response = await fetch(`${BACKEND_API}/api/v1/accounts/link-telegram`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${accessToken}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Не удалось создать ссылку');
      }

      const data = await response.json();
      pendingTelegramLinkRefreshRef.current = true;
      window.open(data.link_url, '_blank');
      toast.success('Ссылка для привязки Telegram открыта в новом окне');
    } catch (err) {
      console.error('Link Telegram error:', err);
      toast.error(err instanceof Error ? err.message : 'Не удалось привязать Telegram');
    }
  };

  const handleLinkBrowser = async () => {
    if (!accessToken) {
      toast.error('Необходимо войти в аккаунт');
      return;
    }

    try {
      const response = await fetch(`${BACKEND_API}/api/v1/accounts/link-browser`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${accessToken}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Не удалось создать ссылку');
      }

      const data = await response.json();
      const tg = getTelegramWebApp();
      if (isTelegramWebApp && tg?.openLink) {
        tg.openLink(data.link_url, { try_browser: true });
      } else {
        window.location.href = data.link_url;
      }
    } catch (err) {
      console.error('Link Browser error:', err);
      toast.error(err instanceof Error ? err.message : 'Не удалось привязать браузерный аккаунт');
    }
  };

  const completeBrowserLink = async (token: string, linkToken: string) => {
    if (!linkToken || inFlightLinkTokenRef.current === linkToken) {
      return;
    }

    inFlightLinkTokenRef.current = linkToken;

    try {
      const response = await fetch(`${BACKEND_API}/api/v1/accounts/link-browser-complete`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ link_token: linkToken }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Не удалось завершить привязку');
      }

      clearBrowserLinkCallbackState();
      await loadUserData(token);
      toast.success('Браузерный аккаунт успешно привязан');
    } catch (err) {
      console.error('Complete browser link error:', err);
      toast.error(err instanceof Error ? err.message : 'Не удалось завершить привязку аккаунта');
    } finally {
      if (inFlightLinkTokenRef.current === linkToken) {
        inFlightLinkTokenRef.current = null;
      }
    }
  };

  const refreshUserData = async () => {
    if (!accessToken) return false;
    
    try {
      const bootstrap = await loadBootstrapSnapshot(accessToken);
      const accountData = bootstrap.account;
      const subscriptionData = bootstrap.subscription;
      const trialUi = bootstrap.trial_ui;
      setUser((currentUser) =>
        mapBackendAccountToUser(
          accountData,
          currentUser?.avatar
        )
      );
      setSubscription(mapSubscriptionToView(accountData, subscriptionData, trialUi));
      setVisibleStoredPaymentAttempts(accountData.id);
      void reconcileStoredPaymentAttempts(accessToken, accountData.id);
      void loadNotificationsUnreadCount(accessToken);
      void loadActivePayments(accessToken, { silent: true });
      return true;
    } catch (err) {
      console.error('Error refreshing user data:', err);
      return false;
    }
  };

  useEffect(() => {
    if (isTelegramWebApp || !accessToken) {
      return;
    }

    const { linkToken, linkFlow } = getBrowserLinkCallbackState();
    if (linkFlow !== 'browser' || !linkToken) {
      return;
    }

    void completeBrowserLink(accessToken, linkToken);
  }, [accessToken, isTelegramWebApp]);

  const handlePasswordRecoveryComplete = async () => {
    setAuthViewMode('default');
    clearPasswordRecoveryActive();
    clearAuthActionParam();
    setIsLoading(true);

    try {
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (session?.access_token) {
        const loaded = await syncBrowserAuth(session.access_token);
        if (!loaded) {
          toast.success('Пароль обновлен. Войдите с новым паролем.');
        }
      } else {
        toast.success('Пароль обновлен. Войдите с новым паролем.');
      }
    } catch (err) {
      console.error('Password recovery completion error:', err);
      toast.success('Пароль обновлен. Войдите с новым паролем.');
    } finally {
      setIsLoading(false);
    }
  };

  const handlePasswordRecoveryCancel = async () => {
    setAuthViewMode('default');
    clearPasswordRecoveryActive();
    clearAuthActionParam();
    clearBrowserAuthState();
    manualLogoutRef.current = true;

    try {
      await supabase.auth.signOut();
    } catch (err) {
      console.error('Password recovery cancel error:', err);
      manualLogoutRef.current = false;
    }
  };

  const handleAuthViewReset = () => {
    clearPasswordRecoveryActive();
    clearAuthActionParam();
    setAuthViewMode('default');
  };

  const getSubscriptionData = () => {
    if (!subscription) {
      return {
        isActive: false,
        hasTrial: !user?.hasUsedTrial,
        hasUsedTrial: user?.hasUsedTrial || false,
        isTrial: false,
      };
    }

    return subscription;
  };

  if (isLoading) {
    return (
      <>
        <Toaster position="top-center" />
        <LoadingScreen />
      </>
    );
  }

  if (!isAuthenticated) {
    return (
      <>
        <Toaster position="top-center" />
        <LoginPage
          view={authView}
          onRecoveryComplete={handlePasswordRecoveryComplete}
          onRecoveryCancel={handlePasswordRecoveryCancel}
          onAuthViewReset={handleAuthViewReset}
        />
      </>
    );
  }

  if (!user) {
    return (
      <>
        <Toaster position="top-center" />
        <div className="min-h-screen flex items-center justify-center bg-[var(--tg-theme-bg-color,#ffffff)]">
          <div className="text-[var(--tg-theme-text-color,#000000)]">Загрузка профиля...</div>
        </div>
      </>
    );
  }

  const subscriptionData = getSubscriptionData();
  const resumablePlanIds = Array.from(
    new Set(
      checkoutAttempts
        .filter((attempt) => attempt.kind === 'plan' && attempt.planId)
        .map((attempt) => attempt.planId as string)
    )
  );
  const activeTopUpAttempt =
    checkoutAttempts
      .filter((attempt) => attempt.kind === 'topup')
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))[0] ?? null;
  const pendingPayments = mergePendingPayments(activePayments, checkoutAttempts, plans);
  const bottomNavActiveTab: PrimaryAppTab =
    activeTab === 'home' || activeTab === 'plans' || activeTab === 'referral' || activeTab === 'settings'
      ? activeTab
      : lastPrimaryTabRef.current;

  const renderContent = () => {
    switch (activeTab) {
      case 'home':
        return (
          <HomePage
            subscription={subscriptionData}
            referralData={{
              referralCode: user.referralCode || '',
              referralsCount: user.referralsCount || 0,
              referralEarnings: user.referralEarnings || 0,
              availableForWithdraw:
                referralSummary?.available_for_withdraw ?? (user.referralEarnings || 0),
            }}
            onActivateTrial={handleActivateTrial}
            onRenew={() => setActiveTab('plans')}
            onBuy={() => setActiveTab('plans')}
            onOpenAccess={handleOpenSubscriptionAccess}
            onCopyReferral={handleCopyReferral}
            onShareReferralToTelegram={handleShareReferralToTelegram}
            onWithdraw={handleWithdraw}
            referralCopied={referralCopied}
          />
        );
      case 'plans':
        return (
          <PlansPage
            plans={plans}
            balance={user.balance}
            onBuyPlan={handleBuyPlan}
            onTopUp={handleTopUp}
            isLoading={isLoadingPlans}
            checkoutPlanId={checkoutPlanId}
            isTelegramWebApp={isTelegramWebApp}
            resumablePlanIds={resumablePlanIds}
          />
        );
      case 'notifications':
        return (
          <NotificationsPage
            items={notifications}
            total={notificationsTotal}
            unreadCount={notificationsUnreadCount}
            isLoading={isLoadingNotifications}
            isLoadingMore={isLoadingMoreNotifications}
            isUpdatingReadState={isUpdatingNotificationReadState}
            onBack={handleBackToPrimaryTab}
            onMarkRead={(notificationId) => {
              void markNotificationRead(notificationId);
            }}
            onMarkAllRead={() => {
              void markAllNotificationsRead();
            }}
            onLoadMore={handleLoadMoreNotifications}
            onOpenAction={handleNotificationAction}
          />
        );
      case 'payments':
        return (
          <PendingPaymentsPage
            items={pendingPayments}
            isLoading={isLoadingActivePayments}
            onBack={handleBackToSettings}
            onResume={handleResumePendingPayment}
          />
        );
      case 'balance-history':
        return (
          <BalanceHistoryPage
            items={ledgerEntries}
            total={ledgerEntriesTotal}
            isLoading={isLoadingLedgerEntries}
            isLoadingMore={isLoadingMoreLedgerEntries}
            onBack={handleBackToSettings}
            onLoadMore={handleLoadMoreLedgerEntries}
          />
        );
      case 'faq':
        return <FaqPage onBack={handleBackToSettings} />;
      case 'privacy':
        return <LegalDocumentPage kind="privacy" onBack={handleBackToSettings} />;
      case 'terms':
        return <LegalDocumentPage kind="terms" onBack={handleBackToSettings} />;
      case 'referral':
        return (
          <ReferralPage
            referralCode={(referralSummary?.referral_code ?? user.referralCode) || ''}
            referrals={(referralSummary?.items || []).map((item) => ({
              id: item.referred_account_id,
              name: item.display_name,
              date: item.created_at,
              earned: item.reward_amount,
              status: item.status,
            }))}
            totalEarnings={referralSummary?.referral_earnings ?? (user.referralEarnings || 0)}
            availableForWithdraw={referralSummary?.available_for_withdraw ?? (user.referralEarnings || 0)}
            rewardRate={referralSummary?.effective_reward_rate ?? 20}
            isLoading={isLoadingReferralSummary}
            copied={referralCopied}
            onCopyLink={handleCopyReferral}
            onShareTelegram={handleShareReferralToTelegram}
            onWithdraw={handleWithdraw}
          />
        );
      case 'settings':
        return (
          <SettingsPage
            theme={theme}
            onThemeChange={setTheme}
            onLogout={handleLogout}
            showLogout={!isTelegramWebApp}
            user={user}
            onLinkTelegram={handleLinkTelegram}
            onLinkBrowser={handleLinkBrowser}
            isTelegramWebApp={isTelegramWebApp}
            notificationUnreadCount={notificationsUnreadCount}
            activePaymentsCount={pendingPayments.length}
            onOpenNotificationsCenter={handleOpenNotificationsTab}
            onOpenPendingPayments={handleOpenPendingPayments}
            onOpenBalanceHistory={handleOpenBalanceHistory}
            onOpenFaq={handleOpenFaq}
            onOpenPrivacy={handleOpenPrivacy}
            onOpenTerms={handleOpenTerms}
            onOpenSupport={handleOpenSupport}
          />
        );
      default:
        return null;
    }
  };

  const scrollToSection = (sectionId: string) => {
    document.getElementById(sectionId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const isStandaloneInfoTab =
    activeTab === 'notifications' ||
    activeTab === 'payments' ||
    activeTab === 'balance-history' ||
    activeTab === 'faq' ||
    activeTab === 'privacy' ||
    activeTab === 'terms';

  const desktopSections = [
    { id: 'overview', label: 'Обзор', icon: LayoutDashboard },
    { id: 'plans', label: 'Тарифы', icon: CreditCard },
    { id: 'notifications', label: 'Уведомления', icon: Bell },
    { id: 'referrals', label: 'Рефералы', icon: Gift },
    { id: 'settings', label: 'Настройки', icon: SettingsIcon },
  ];

  const renderDesktopPlans = () => {
    if (isLoadingPlans && !plans.length) {
      return (
        <div className="rounded-[28px] border border-dashed border-slate-300 bg-slate-50/70 p-6 dark:border-slate-700 dark:bg-slate-900/70">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-900 text-white dark:bg-sky-500 dark:text-slate-950">
              <Sparkles className="h-6 w-6" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-slate-900 dark:text-slate-50">
                Загружаем тарифы
              </h3>
              <p className="mt-2 max-w-xl text-sm leading-6 text-slate-500 dark:text-slate-300">
                Получаем актуальный каталог тарифов с backend.
              </p>
            </div>
          </div>
        </div>
      );
    }

    if (!plans.length) {
      return (
        <div className="rounded-[28px] border border-dashed border-slate-300 bg-slate-50/70 p-6 dark:border-slate-700 dark:bg-slate-900/70">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-900 text-white dark:bg-sky-500 dark:text-slate-950">
              <Sparkles className="h-6 w-6" />
            </div>
            <div className="space-y-3">
              <div>
                <h3 className="text-xl font-semibold text-slate-900 dark:text-slate-50">
                  Каталог тарифов переносится
                </h3>
                <p className="mt-2 max-w-xl text-sm leading-6 text-slate-500 dark:text-slate-300">
                  В browser dashboard уже работает новая авторизация, а тарифы и подписки
                  догружаем следующим этапом с вашего `FastAPI`.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={handleTopUp}
                  className="rounded-2xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
                >
                  Пополнить баланс
                </button>
                <button
                  onClick={() => scrollToSection('overview')}
                  className="rounded-2xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900"
                >
                  Вернуться к обзору
                </button>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="grid gap-4 xl:grid-cols-2">
        {plans.map((plan) => (
          <div
            key={plan.id}
            className={`relative rounded-[28px] border border-slate-200 bg-slate-50/70 p-6 dark:border-slate-800 dark:bg-slate-900/80 ${
              plan.popular ? 'ring-2 ring-sky-400/60' : ''
            }`}
          >
            {plan.popular && (
              <div className="absolute -top-3 left-6 rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-white dark:bg-sky-500 dark:text-slate-950">
                Лучший выбор
              </div>
            )}
            <div className="space-y-4">
              <div>
                <div className="text-sm font-medium uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                  {plan.duration} дней доступа
                </div>
                <h3 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-slate-50">
                  {plan.name}
                </h3>
                <div className="mt-3 flex items-end gap-2">
                  <span className="text-4xl font-bold text-slate-900 dark:text-slate-50">
                    {plan.price}
                  </span>
                  <span className="pb-1 text-sm text-slate-500 dark:text-slate-400">₽</span>
                </div>
              </div>
              <div className="space-y-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                {plan.features.map((feature, index) => (
                  <div key={index} className="flex items-start gap-3">
                    <span className="mt-1.5 h-2 w-2 rounded-full bg-sky-500" />
                    <span>{feature}</span>
                  </div>
                ))}
              </div>
              <button
                onClick={() => {
                  void handleBuyPlan(plan.id);
                }}
                disabled={checkoutPlanId === plan.id}
                className="w-full rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
              >
                {checkoutPlanId === plan.id
                  ? 'Открываем оплату...'
                  : resumablePlanIds.includes(plan.id)
                    ? 'Продолжить оплату'
                    : 'Оплатить тариф'}
              </button>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderDesktopBrowserLayout = () => (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,#dbeafe_0%,#eff6ff_24%,#f8fafc_58%,#eef2ff_100%)] px-8 py-8 dark:bg-[radial-gradient(circle_at_top_left,#0f172a_0%,#111827_28%,#020617_100%)]">
      <Toaster position="top-center" />
      <TopUpModal
        isOpen={isTopUpModalOpen}
        onClose={() => setIsTopUpModalOpen(false)}
        onTopUp={handleTopUpAmount}
        isSubmitting={isTopUpSubmitting}
        activeAttemptAmount={activeTopUpAttempt?.amount ?? null}
      />
      <PaymentMethodSheet
        isOpen={Boolean(paymentMethodSelection)}
        title={
          paymentMethodSelection?.kind === 'topup'
            ? 'Выберите способ пополнения'
            : 'Выберите способ оплаты'
        }
        subtitle={
          paymentMethodSelection?.kind === 'plan'
            ? `Тариф: ${paymentMethodSelection.planName}`
            : paymentMethodSelection?.kind === 'topup'
              ? `Сумма пополнения: ${formatRubles(paymentMethodSelection.amount)} ₽`
              : undefined
        }
        methods={paymentMethodSelection?.methods ?? []}
        isSubmitting={Boolean(paymentMethodSubmitting)}
        selectedProvider={paymentMethodSubmitting}
        onClose={() => {
          if (!paymentMethodSubmitting) {
            setPaymentMethodSelection(null);
          }
        }}
        onSelect={(provider) => {
          void handlePaymentMethodSelect(provider);
        }}
      />

      <div className="mx-auto flex max-w-[1520px] gap-6">
        <aside className="sticky top-8 h-[calc(100vh-4rem)] w-[310px] shrink-0 rounded-[32px] border border-white/70 bg-white/82 p-6 shadow-[0_32px_80px_rgba(15,23,42,0.14)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_32px_80px_rgba(2,6,23,0.55)]">
          <div className="flex h-full flex-col">
            <div className="space-y-6">
              <div className="space-y-3">
                <span className="inline-flex items-center rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-sky-700 dark:bg-sky-500/15 dark:text-sky-200">
                  Browser Workspace
                </span>
                <div>
                  <h1 className="text-2xl font-semibold text-slate-950 dark:text-slate-50">RemnaStore</h1>
                  <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                    Широкий desktop dashboard вместо мобильного контейнера по центру экрана.
                  </p>
                </div>
              </div>

              <div className="rounded-[28px] bg-slate-950 p-5 text-white shadow-[0_24px_48px_rgba(15,23,42,0.28)] dark:border dark:border-slate-800 dark:bg-slate-900/90 dark:shadow-[0_24px_48px_rgba(2,6,23,0.45)]">
                <div className="flex items-center gap-4">
                  <div className="flex h-14 w-14 items-center justify-center overflow-hidden rounded-2xl bg-white/10 text-lg font-semibold">
                    {user.avatar ? (
                      <img
                        src={user.avatar}
                        alt={user.name}
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      user.name.charAt(0).toUpperCase()
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-lg font-semibold">{user.name}</div>
                    <div className="truncate text-sm text-slate-300">
                      {user.email || 'Browser account'}
                    </div>
                  </div>
                </div>
                <div className="mt-5 rounded-2xl bg-white/8 p-4 dark:bg-white/5">
                  <div className="text-xs uppercase tracking-[0.16em] text-slate-300">Баланс</div>
                  <div className="mt-2 text-3xl font-semibold">{formatRubles(user.balance)} ₽</div>
                </div>
              </div>

              <nav className="space-y-2">
                {desktopSections.map((section) => {
                  const Icon = section.icon;
                  return (
                    <button
                      key={section.id}
                      onClick={() => scrollToSection(section.id)}
                      className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left text-sm font-semibold text-slate-700 transition hover:bg-white/70 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-slate-900 dark:hover:text-slate-50"
                    >
                      <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-900 dark:border dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100">
                        <Icon className="h-5 w-5" />
                      </span>
                      <span>{section.label}</span>
                    </button>
                  );
                })}
              </nav>

              <div className="rounded-[24px] border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-900/80">
                <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">Desktop quick note</div>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  Основные разделы собраны на одной странице. Скролл нужен только если контента
                  станет больше.
                </p>
              </div>
            </div>

            <button
              onClick={handleLogout}
              className="mt-auto flex items-center justify-center gap-2 rounded-2xl bg-[var(--app-danger-bg,#ef4444)] px-4 py-3 text-sm font-semibold text-[var(--app-danger-text,#ffffff)] transition hover:bg-[var(--app-danger-bg-hover,#dc2626)]"
            >
              <LogOut className="h-4 w-4" />
              Выйти из аккаунта
            </button>
          </div>
        </aside>

        <main className="min-w-0 flex-1 space-y-6">
          <section
            id="overview"
            className="rounded-[32px] border border-white/70 bg-white/82 p-8 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
          >
            <div className="flex flex-wrap items-start justify-between gap-6">
              <div className="max-w-3xl space-y-3">
                <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-600 dark:bg-slate-900 dark:text-slate-300">
                  Управление доступом
                </span>
                <h2 className="text-4xl font-semibold tracking-tight text-slate-950 dark:text-slate-50">
                  Вся работа с аккаунтом собрана в одном desktop dashboard
                </h2>
                <p className="text-base leading-7 text-slate-500 dark:text-slate-300">
                  Без имитации экрана телефона: обзор аккаунта, тарифы, реферальные метрики и
                  быстрые настройки теперь живут в одном широком рабочем пространстве.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={() => scrollToSection('plans')}
                  className="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900"
                >
                  Открыть тарифы
                </button>
                <button
                  onClick={handleTopUp}
                  className="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
                >
                  Пополнить баланс
                </button>
              </div>
            </div>

            <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-[26px] bg-slate-950 p-5 text-white dark:border dark:border-slate-800 dark:bg-slate-900/90">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-300">
                    Баланс
                  </span>
                  <Wallet className="h-5 w-5 text-slate-300" />
                </div>
                <div className="mt-4 text-3xl font-semibold">{formatRubles(user.balance)} ₽</div>
                <div className="mt-2 text-sm text-slate-300">Доступно для покупок и продления</div>
              </div>

              <div className="rounded-[26px] bg-white p-5 shadow-[0_20px_40px_rgba(15,23,42,0.06)] dark:bg-slate-900 dark:shadow-[0_20px_40px_rgba(2,6,23,0.35)]">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                    Статус
                  </span>
                  <LayoutDashboard className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                </div>
                <div className="mt-4 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                  {subscriptionData.isActive
                    ? `${subscriptionData.daysLeft ?? 0} дней`
                    : subscriptionData.hasTrial && !subscriptionData.hasUsedTrial
                      ? 'Trial доступен'
                      : 'Без подписки'}
                </div>
                <div className="mt-2 text-sm text-slate-500 dark:text-slate-300">
                  {subscriptionData.isActive
                    ? 'Подписка активна'
                    : 'Можно активировать пробный доступ или выбрать тариф'}
                </div>
              </div>

              <div className="rounded-[26px] bg-white p-5 shadow-[0_20px_40px_rgba(15,23,42,0.06)] dark:bg-slate-900 dark:shadow-[0_20px_40px_rgba(2,6,23,0.35)]">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                    Рефералы
                  </span>
                  <Gift className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                </div>
                <div className="mt-4 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                  {user.referralsCount || 0}
                </div>
                <div className="mt-2 text-sm text-slate-500 dark:text-slate-300">Активных приглашений в системе</div>
              </div>

              <div className="rounded-[26px] bg-white p-5 shadow-[0_20px_40px_rgba(15,23,42,0.06)] dark:bg-slate-900 dark:shadow-[0_20px_40px_rgba(2,6,23,0.35)]">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                    Доход
                  </span>
                  <Sparkles className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                </div>
                <div className="mt-4 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                  {formatRubles(user.referralEarnings)} ₽
                </div>
                <div className="mt-2 text-sm text-slate-500 dark:text-slate-300">Начислено по реферальной программе</div>
              </div>
            </div>
          </section>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
            <section
              className="rounded-[32px] border border-white/70 bg-white/82 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
            >
              <div className="border-b border-slate-200/80 px-6 py-5 dark:border-slate-800/80">
                <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">Подписка и доступ</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  Ключевой статус аккаунта и действия по доступу находятся здесь.
                </p>
              </div>
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
                <div className="min-w-0">
                  <SubscriptionCard
                    subscription={subscriptionData}
                    onActivateTrial={handleActivateTrial}
                    onRenew={() => scrollToSection('plans')}
                    onBuy={() => scrollToSection('plans')}
                    onOpenAccess={handleOpenSubscriptionAccess}
                  />
                </div>
                <div className="p-6">
                  <div className="rounded-[28px] bg-slate-50 p-5 dark:bg-slate-900">
                    <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">Что изменилось</div>
                    <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-500 dark:text-slate-300">
                      <li>Google и email живут в одном browser auth flow.</li>
                      <li>Telegram Mini App остается отдельным полноэкранным сценарием.</li>
                      <li>Desktop теперь использует нормальную панель, а не мобильный shell.</li>
                    </ul>
                  </div>
                </div>
              </div>
            </section>

            <section
              id="plans"
              className="rounded-[32px] border border-white/70 bg-white/82 p-6 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
            >
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">Тарифы</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                    Здесь будет коммерческий каталог после переноса subscription API.
                  </p>
                </div>
                <button
                  onClick={handleTopUp}
                  className="rounded-2xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900"
                >
                  Пополнить
                </button>
              </div>
              {renderDesktopPlans()}
            </section>
          </div>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <section
              id="referrals"
              className="rounded-[32px] border border-white/70 bg-white/82 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
            >
              <div className="border-b border-slate-200/80 px-6 py-5 dark:border-slate-800/80">
                <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">Реферальная программа</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  Код, начисления и быстрые действия собраны в одном блоке.
                </p>
              </div>
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
                <div className="min-w-0">
                  <ReferralCard
                    referralCode={user.referralCode || ''}
                    referralsCount={user.referralsCount || 0}
                    referralEarnings={user.referralEarnings || 0}
                    availableForWithdraw={
                      referralSummary?.available_for_withdraw ?? (user.referralEarnings || 0)
                    }
                    onCopy={handleCopyReferral}
                    onShareTelegram={handleShareReferralToTelegram}
                    onWithdraw={handleWithdraw}
                    copied={referralCopied}
                  />
                </div>
                <div className="p-6">
                  <div className="grid gap-4">
                    <div className="rounded-[24px] bg-slate-50 p-4 dark:bg-slate-900">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                        Приглашено
                      </div>
                      <div className="mt-3 text-3xl font-semibold text-slate-950 dark:text-slate-50">
                        {user.referralsCount || 0}
                      </div>
                    </div>
                    <div className="rounded-[24px] bg-slate-950 p-4 text-white dark:border dark:border-slate-800 dark:bg-slate-900">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-300">
                        Доступно к выводу
                      </div>
                      <div className="mt-3 text-3xl font-semibold">
                        {formatRubles(referralSummary?.available_for_withdraw ?? user.referralEarnings)} ₽
                      </div>
                    </div>
                    <div className="rounded-[24px] border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
                      {isLoadingReferralSummary
                        ? 'Загружаем детали реферальной активности.'
                        : 'Полный список рефералов и статусы начислений доступны во вкладке «Рефералы».'}
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <section
              id="settings"
              className="rounded-[32px] border border-white/70 bg-white/82 p-6 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
            >
              <div className="mb-6">
                <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">Быстрые настройки</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  Главное вынесено в отдельный блок, без ухода на отдельный экран.
                </p>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between rounded-[24px] bg-slate-50 px-4 py-4 dark:bg-slate-900">
                  <div className="flex items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100">
                      {theme === 'dark' ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">Тема интерфейса</div>
                      <div className="text-sm text-slate-500 dark:text-slate-300">Переключение локального режима</div>
                    </div>
                  </div>
                  <ThemeToggle
                    theme={theme}
                    onToggle={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                  />
                </div>

                <div className="flex items-center justify-between rounded-[24px] bg-slate-50 px-4 py-4 dark:bg-slate-900">
                  <div className="flex items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100">
                      <SettingsIcon className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">Язык интерфейса</div>
                      <div className="text-sm text-slate-500 dark:text-slate-300">Текущая локаль браузера</div>
                    </div>
                  </div>
                  <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">Русский</div>
                </div>

                <div className="grid gap-3">
                  <button
                    onClick={handleOpenPendingPayments}
                    className="flex items-center justify-between rounded-[24px] border border-slate-200 bg-white px-4 py-4 text-left transition hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-900"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100">
                        <CreditCard className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">Незавершенные оплаты</div>
                        <div className="text-sm text-slate-500 dark:text-slate-300">Живые ссылки оплаты, которые еще можно продолжить</div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                      {pendingPayments.length > 0 ? pendingPayments.length : 'Открыть'}
                    </div>
                  </button>

                  <button
                    onClick={handleOpenBalanceHistory}
                    className="flex items-center justify-between rounded-[24px] border border-slate-200 bg-white px-4 py-4 text-left transition hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-900"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100">
                        <Wallet className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">История баланса</div>
                        <div className="text-sm text-slate-500 dark:text-slate-300">Все начисления и списания по внутреннему счету</div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">Открыть</div>
                  </button>

                  <button
                    onClick={handleOpenSupport}
                    className="flex items-center justify-between rounded-[24px] border border-slate-200 bg-white px-4 py-4 text-left transition hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-900"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-white dark:border dark:border-slate-800 dark:bg-slate-900">
                        <MessageCircle className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">Поддержка в Telegram</div>
                        <div className="text-sm text-slate-500 dark:text-slate-300">Переход в support-группу</div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">Перейти</div>
                  </button>

                  <button
                    onClick={handleOpenFaq}
                    className="flex items-center justify-between rounded-[24px] border border-slate-200 bg-white px-4 py-4 text-left transition hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-900"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100">
                        <HelpCircle className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">FAQ</div>
                        <div className="text-sm text-slate-500 dark:text-slate-300">Базовые ответы по доступу и оплате</div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">Открыть</div>
                  </button>

                  <button
                    onClick={handleOpenPrivacy}
                    className="flex items-center justify-between rounded-[24px] border border-slate-200 bg-white px-4 py-4 text-left transition hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-900"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100">
                        <Shield className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">Политика конфиденциальности</div>
                        <div className="text-sm text-slate-500 dark:text-slate-300">Правила обработки данных и интеграций</div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">Открыть</div>
                  </button>

                  <button
                    onClick={handleOpenTerms}
                    className="flex items-center justify-between rounded-[24px] border border-slate-200 bg-white px-4 py-4 text-left transition hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-900"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100">
                        <FileText className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">Пользовательское соглашение</div>
                        <div className="text-sm text-slate-500 dark:text-slate-300">Условия использования продукта</div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">Открыть</div>
                  </button>
                </div>

                <button
                  onClick={handleLogout}
                  className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[var(--app-danger-bg,#ef4444)] px-4 py-3 text-sm font-semibold text-[var(--app-danger-text,#ffffff)] transition hover:bg-[var(--app-danger-bg-hover,#dc2626)]"
                >
                  <LogOut className="h-4 w-4" />
                  Выйти из аккаунта
                </button>
              </div>
            </section>
          </div>

          <section
            id="notifications"
            className="rounded-[32px] border border-white/70 bg-white/82 p-6 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
          >
            <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
              <div>
                <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">Центр уведомлений</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  События по подписке, оплатам, реферальным начислениям и заявкам на вывод.
                </p>
              </div>
              <div className="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white dark:border dark:border-slate-800 dark:bg-slate-900">
                {notificationsUnreadCount > 0
                  ? `${notificationsUnreadCount} непрочитанных`
                  : 'Все уведомления прочитаны'}
              </div>
            </div>

            <NotificationsPage
              items={notifications}
              total={notificationsTotal}
              unreadCount={notificationsUnreadCount}
              isLoading={isLoadingNotifications}
              isLoadingMore={isLoadingMoreNotifications}
              isUpdatingReadState={isUpdatingNotificationReadState}
              embedded
              onMarkRead={(notificationId) => {
                void markNotificationRead(notificationId);
              }}
              onMarkAllRead={() => {
                void markAllNotificationsRead();
              }}
              onLoadMore={handleLoadMoreNotifications}
              onOpenAction={handleNotificationAction}
            />
          </section>
        </main>
      </div>
    </div>
  );

  if (isDesktopBrowser && isStandaloneInfoTab) {
    return (
      <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,#dbeafe_0%,#eff6ff_24%,#f8fafc_58%,#eef2ff_100%)] px-6 py-8 dark:bg-[radial-gradient(circle_at_top_left,#0f172a_0%,#111827_28%,#020617_100%)]">
        <Toaster position="top-center" />
        <div className="mx-auto max-w-4xl rounded-[32px] border border-white/70 bg-white/82 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]">
          {renderContent()}
        </div>
      </div>
    );
  }

  if (isDesktopBrowser) {
    return renderDesktopBrowserLayout();
  }

  const isCompactBrowserLayout = !isTelegramWebApp;

  return (
    <div
      className={`${
        isCompactBrowserLayout
          ? 'h-[100dvh] overflow-hidden bg-[linear-gradient(180deg,#eef4ff_0%,#f8fafc_45%,#eef2f7_100%)] sm:px-4 sm:py-6 md:px-6 md:py-8 dark:bg-[linear-gradient(180deg,#0f172a_0%,#111827_45%,#020617_100%)]'
          : 'min-h-screen bg-[var(--tg-theme-bg-color,#ffffff)]'
      }`}
    >
      <Toaster position="top-center" />
      <TopUpModal
        isOpen={isTopUpModalOpen}
        onClose={() => setIsTopUpModalOpen(false)}
        onTopUp={handleTopUpAmount}
        isSubmitting={isTopUpSubmitting}
        activeAttemptAmount={activeTopUpAttempt?.amount ?? null}
      />
      <PaymentMethodSheet
        isOpen={Boolean(paymentMethodSelection)}
        title={
          paymentMethodSelection?.kind === 'topup'
            ? 'Выберите способ пополнения'
            : 'Выберите способ оплаты'
        }
        subtitle={
          paymentMethodSelection?.kind === 'plan'
            ? `Тариф: ${paymentMethodSelection.planName}`
            : paymentMethodSelection?.kind === 'topup'
              ? `Сумма пополнения: ${formatRubles(paymentMethodSelection.amount)} ₽`
              : undefined
        }
        methods={paymentMethodSelection?.methods ?? []}
        isSubmitting={Boolean(paymentMethodSubmitting)}
        selectedProvider={paymentMethodSubmitting}
        onClose={() => {
          if (!paymentMethodSubmitting) {
            setPaymentMethodSelection(null);
          }
        }}
        onSelect={(provider) => {
          void handlePaymentMethodSelect(provider);
        }}
      />

      <div
        className={`${
          isCompactBrowserLayout
            ? 'relative flex h-full w-full flex-col overflow-hidden bg-[var(--tg-theme-bg-color,#ffffff)] sm:mx-auto sm:max-w-[440px] sm:rounded-[30px] sm:border sm:border-white/70 sm:shadow-[0_28px_80px_rgba(15,23,42,0.16)] sm:backdrop-blur'
            : 'min-h-screen bg-[var(--tg-theme-bg-color,#ffffff)]'
        }`}
      >
        <div
          className={`${
            isCompactBrowserLayout
              ? 'safe-area-inset-top sticky top-0 z-20 shrink-0 bg-[var(--tg-theme-bg-color,#ffffff)]'
              : 'shrink-0'
          }`}
        >
          <Header
            user={{ name: user.name, avatar: user.avatar }}
            balance={user.balance}
            onTopUp={handleTopUp}
            onOpenNotifications={handleOpenNotificationsTab}
            unreadNotificationsCount={notificationsUnreadCount}
          />
        </div>
        <main
          className={`${
            isCompactBrowserLayout
              ? 'min-h-0 flex-1 overflow-y-auto overscroll-contain pb-24'
              : 'flex-1 pb-24'
          }`}
        >
          {renderContent()}
        </main>
        <BottomNav
          activeTab={bottomNavActiveTab}
          onTabChange={handleTabChange}
          compact={isCompactBrowserLayout}
        />
      </div>
    </div>
  );
}
