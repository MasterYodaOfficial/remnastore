import React, { Suspense, useEffect, useRef, useState } from 'react';
import { supabase } from '../../utils/supabase/client';
import {
  browserBrandName as BROWSER_BRAND_NAME,
  apiBaseUrl as BACKEND_API,
  supportEmail as SUPPORT_EMAIL,
  supportTelegramUrl as SUPPORT_TELEGRAM_URL,
  telegramBotUrl as TELEGRAM_BOT_URL,
} from '../../utils/runtime-config'
import browserTabLogoUrl from '../../../bot/bot/assets/menu/logo.jpg';
import {
  loadTelegramScript,
  hasTelegramLaunchParams,
  getTelegramWebApp,
  openTelegramInvoice,
  openTelegramExternalLink,
  openTelegramLink,
  type TelegramWebAppLike,
} from '../../utils/telegram';
import { LoginPage } from './components/LoginPage';
import { Header } from './components/Header';
import type { ReferralFeedFilter } from './components/ReferralPage';
import { ReferralCard } from './components/ReferralCard';
import { PromoRedeemCard, type PromoRedeemMessage } from './components/PromoRedeemCard';
import { SubscriptionCard } from './components/SubscriptionCard';
import { ThemeToggle } from './components/ThemeToggle';
import { BottomNav } from './components/BottomNav';
import type { PaymentMethodOption, PaymentMethodProvider } from './components/PaymentMethodSheet';
import { LoadingScreen } from './components/LoadingScreen';
import type { NotificationItemView } from './components/NotificationsPage';
import type { PendingPaymentView } from './components/PendingPaymentsPage';
import type { BalanceHistoryItemView } from './components/BalanceHistoryPage';
import { WithdrawalRequestsCard, type WithdrawalRequestItemView } from './components/WithdrawalRequestsCard';
import { formatRubles } from '../lib/currency';
import { getTranslationValue, t } from '../lib/i18n';
import { toast, Toaster } from 'sonner';
import {
  buildBrowserReferralLink,
  buildTelegramShareReferralUrl,
  capturePendingReferralCodeFromUrl,
  readPendingReferralCode,
  clearPendingReferralCode,
} from './lib/referrals';
import { buildSupportMailtoUrl } from './lib/support';
import { normalizeReferralMetric, resolveReferralAmount } from './lib/referral-metrics';
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
  Check,
  Copy,
  CreditCard,
  FileText,
  Gift,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  Mail,
  MessageCircle,
  Moon,
  Settings as SettingsIcon,
  Shield,
  Sparkles,
  Sun,
  Wallet,
} from 'lucide-react';
import {
  getLinkingErrorMessage,
  getPaymentErrorMessage,
  getPromoErrorMessage,
  getTrialErrorMessage,
  getWithdrawalErrorMessage,
  isReferralAlreadyHandledError,
  isReferralCodeNotFoundError,
  isReferralSelfError,
  parseApiErrorPayload,
} from './lib/api-errors';
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
type PromoLaunchState = {
  promoCode: string | null;
  planId: string | null;
  tab: AppTab | null;
};

const formatDocumentTitle = (pageTitle: string | null): string => {
  const normalizedPageTitle = pageTitle?.trim();
  if (!normalizedPageTitle || normalizedPageTitle === BROWSER_BRAND_NAME) {
    return BROWSER_BRAND_NAME;
  }

  return `${normalizedPageTitle} | ${BROWSER_BRAND_NAME}`;
};

const applyBrowserTabIcon = (href: string) => {
  const iconRels = ['icon', 'shortcut icon'] as const;

  for (const rel of iconRels) {
    let link = document.head.querySelector(`link[rel="${rel}"]`) as HTMLLinkElement | null;
    if (!link) {
      link = document.createElement('link');
      link.rel = rel;
      document.head.appendChild(link);
    }
    link.type = 'image/jpeg';
    link.href = href;
  }
};

const LazyHomePage = React.lazy(async () => ({
  default: (await import('./components/HomePage')).HomePage,
}));

const LazyPlansPage = React.lazy(async () => ({
  default: (await import('./components/PlansPage')).PlansPage,
}));

const LazyReferralPage = React.lazy(async () => ({
  default: (await import('./components/ReferralPage')).ReferralPage,
}));

const LazySettingsPage = React.lazy(async () => ({
  default: (await import('./components/SettingsPage')).SettingsPage,
}));

const LazyNotificationsPage = React.lazy(async () => ({
  default: (await import('./components/NotificationsPage')).NotificationsPage,
}));

const LazyPendingPaymentsPage = React.lazy(async () => ({
  default: (await import('./components/PendingPaymentsPage')).PendingPaymentsPage,
}));

const LazyFaqPage = React.lazy(async () => ({
  default: (await import('./components/FaqPage')).FaqPage,
}));

const LazyLegalDocumentPage = React.lazy(async () => ({
  default: (await import('./components/LegalDocumentPage')).LegalDocumentPage,
}));

const LazyBalanceHistoryPage = React.lazy(async () => ({
  default: (await import('./components/BalanceHistoryPage')).BalanceHistoryPage,
}));

const LazyTopUpModal = React.lazy(async () => ({
  default: (await import('./components/TopUpModal')).TopUpModal,
}));

const LazyWithdrawalRequestModal = React.lazy(async () => ({
  default: (await import('./components/WithdrawalRequestModal')).WithdrawalRequestModal,
}));

const LazyPaymentMethodSheet = React.lazy(async () => ({
  default: (await import('./components/PaymentMethodSheet')).PaymentMethodSheet,
}));

function ChunkFallback({
  className = 'p-6',
  minHeightClassName = 'min-h-[240px]',
}: {
  className?: string;
  minHeightClassName?: string;
}) {
  return (
    <div className={`${className} ${minHeightClassName} flex items-center justify-center`}>
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-[var(--tg-theme-button-color,#3390ec)] border-t-transparent" />
        <div className="text-sm font-medium text-[var(--tg-theme-text-color,#000000)]">
          {t('web.loadingScreen.title')}
        </div>
        <div className="text-xs text-[var(--tg-theme-hint-color,#999999)]">
          {t('web.loadingScreen.subtitle')}
        </div>
      </div>
    </div>
  );
}

function ModalChunkFallback() {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4">
      <div className="rounded-[28px] bg-[var(--tg-theme-bg-color,#ffffff)] px-6 py-5 shadow-[0_24px_64px_rgba(15,23,42,0.24)]">
        <ChunkFallback className="p-0" minHeightClassName="min-h-0" />
      </div>
    </div>
  );
}

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

interface BackendPromoPlanQuoteResponse {
  plan_code: string;
  promo_code: string;
  effect_type: string;
  original_amount: number;
  final_amount: number;
  discount_amount: number;
  currency: string;
  original_duration_days: number;
  final_duration_days: number;
}

interface BackendPromoRedeemResponse {
  promo_code: string;
  effect_type: string;
  status: string;
  balance: number;
  balance_credit_amount?: number | null;
  granted_duration_days?: number | null;
  subscription: BackendSubscriptionState;
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

interface BackendReferralFeedItem {
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
}

interface BackendReferralFeedResponse {
  items: BackendReferralFeedItem[];
  total: number;
  limit: number;
  offset: number;
  status_filter: ReferralFeedFilter;
}

interface BackendWithdrawalItem {
  id: number;
  amount: number;
  destination_type: 'card' | 'sbp';
  destination_value: string;
  user_comment?: string | null;
  admin_comment?: string | null;
  status: 'new' | 'in_progress' | 'paid' | 'rejected' | 'cancelled';
  reserved_ledger_entry_id?: number | null;
  released_ledger_entry_id?: number | null;
  processed_at?: string | null;
  created_at: string;
  updated_at: string;
}

interface BackendWithdrawalListResponse {
  items: BackendWithdrawalItem[];
  total: number;
  limit: number;
  offset: number;
  available_for_withdraw: number;
  minimum_amount_rub: number;
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

const REFERRAL_FEED_PAGE_SIZE = 20;

interface Plan {
  id: string;
  name: string;
  price: number;
  priceStars?: number | null;
  duration: number;
  features: string[];
  popular?: boolean;
}

interface PlanPromoContext {
  code: string | null;
  rubQuote: BackendPromoPlanQuoteResponse | null;
  starsQuote: BackendPromoPlanQuoteResponse | null;
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

  for (const key of [
    'avatar_url',
    'avatar',
    'picture',
    'photo',
    'photo_url',
    'photo_100',
    'photo_200',
    'image',
    'profile_image_url',
  ]) {
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
  const prioritizedProviderIds = ['google'];
  const preferredIdentity = prioritizedProviderIds
    .map((providerId) => identities.find((identity) => identity?.provider === providerId))
    .find((identity): identity is SupabaseIdentityLike => Boolean(identity));

  return (
    pickAvatarUrl(preferredIdentity?.identity_data) ||
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
    t('web.app.fallbackUserName');

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
    totalDays: isTrial ? calculateTotalDays(trialUsedAt, trialEndsAt) : undefined,
    hasTrial: trialUi?.can_start_now ?? !hasUsedTrial,
    hasUsedTrial,
    isTrial,
    status,
    expiresAt,
    subscriptionUrl: subscriptionState?.subscription_url ?? account.subscription_url ?? null,
    trialEligibilityReason: trialUi?.reason ?? null,
  };
}

function formatDayCount(count: number): string {
  const absoluteCount = Math.abs(count);
  const remainder10 = absoluteCount % 10;
  const remainder100 = absoluteCount % 100;
  let unitKey = 'many';

  if (remainder10 === 1 && remainder100 !== 11) {
    unitKey = 'one';
  } else if (remainder10 >= 2 && remainder10 <= 4 && (remainder100 < 12 || remainder100 > 14)) {
    unitKey = 'few';
  }

  return t(`web.app.units.day.${unitKey}`, { count });
}

function getFallbackErrorMessage(error: unknown, fallbackKey: string): string {
  return error instanceof Error ? error.message : t(fallbackKey);
}

function getPaymentSheetTitle(selection: PaymentSelectionState | null): string {
  return selection?.kind === 'topup'
    ? t('web.app.paymentSheet.topupTitle')
    : t('web.app.paymentSheet.planTitle');
}

function getPaymentSheetSubtitle(selection: PaymentSelectionState | null): string | undefined {
  if (selection?.kind === 'plan') {
    return t('web.app.paymentSheet.planSubtitle', { planName: selection.planName });
  }

  if (selection?.kind === 'topup') {
    return t('web.app.paymentSheet.topupSubtitle', {
      amount: formatRubles(selection.amount),
    });
  }

  return undefined;
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
        ? t('web.app.pendingPayments.topupDescription', {
            amount: formatRubles(attempt.amount),
          })
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

function mapBackendWithdrawalToView(entry: BackendWithdrawalItem): WithdrawalRequestItemView {
  return {
    id: entry.id,
    amount: entry.amount,
    destinationType: entry.destination_type,
    destinationLabel: entry.destination_value,
    status: entry.status,
    userComment: entry.user_comment ?? null,
    adminComment: entry.admin_comment ?? null,
    processedAt: entry.processed_at ?? null,
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

function normalizePromoCodeInput(value: string): string {
  return value.trim().toUpperCase();
}

function normalizePromoLaunchTab(value: string | null): AppTab | null {
  switch (value) {
    case 'home':
    case 'plans':
    case 'notifications':
    case 'payments':
    case 'balance-history':
    case 'referral':
    case 'settings':
    case 'faq':
    case 'privacy':
    case 'terms':
      return value;
    default:
      return null;
  }
}

function readPromoLaunchStateFromUrl(): PromoLaunchState | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const url = new URL(window.location.href);
  const promoCode = normalizePromoCodeInput(url.searchParams.get('promo') ?? '');
  const planId = (url.searchParams.get('plan') ?? '').trim();
  const tab = normalizePromoLaunchTab(url.searchParams.get('tab'));

  if (!promoCode && !planId && !tab) {
    return null;
  }

  url.searchParams.delete('promo');
  url.searchParams.delete('plan');
  url.searchParams.delete('tab');
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);

  return {
    promoCode: promoCode || null,
    planId: planId || null,
    tab,
  };
}

function formatAmountWithCurrency(amount: number, currency: string): string {
  if (currency === 'RUB') {
    return `${formatRubles(amount)} ₽`;
  }
  if (currency === 'XTR') {
    return `${amount} ${t('web.app.paymentMethods.telegramStarsLabel')}`;
  }
  return `${amount} ${currency}`;
}

function describePromoQuote(quote: BackendPromoPlanQuoteResponse): string {
  const parts: string[] = [];

  if (quote.final_amount < quote.original_amount) {
    parts.push(
      t('web.app.promo.discountComparison', {
        finalAmount: formatAmountWithCurrency(quote.final_amount, quote.currency),
        originalAmount: formatAmountWithCurrency(quote.original_amount, quote.currency),
      })
    );
  }

  if (quote.final_duration_days > quote.original_duration_days) {
    parts.push(
      t('web.app.promo.duration', {
        days: quote.final_duration_days,
      })
    );
  }

  return parts.length > 0 ? `${parts.join(' • ')}.` : t('web.app.promo.activeForPlan');
}

function getTelegramPreferredBrowser(): string | undefined {
  if (typeof navigator === 'undefined') {
    return undefined;
  }

  const userAgent = navigator.userAgent.toLowerCase();
  if (userAgent.includes('android')) {
    return 'chrome';
  }

  return undefined;
}

function buildTelegramMiniAppReturnUrl(): string {
  if (!TELEGRAM_BOT_URL) {
    return '';
  }

  try {
    const telegramUrl = new URL(TELEGRAM_BOT_URL);
    const isTelegramHost =
      telegramUrl.hostname === 't.me' || telegramUrl.hostname === 'telegram.me';
    const pathParts = telegramUrl.pathname.split('/').filter(Boolean);

    if (
      isTelegramHost &&
      pathParts.length === 1 &&
      !telegramUrl.searchParams.has('startapp') &&
      !telegramUrl.searchParams.has('start')
    ) {
      telegramUrl.searchParams.set('startapp', '');
    }

    return telegramUrl.toString();
  } catch {
    return TELEGRAM_BOT_URL;
  }
}

function getPaymentReturnUrl(options: { preferTelegramBot?: boolean } = {}): string {
  if (typeof window === 'undefined') {
    return '';
  }

  if (options.preferTelegramBot) {
    const telegramReturnUrl = buildTelegramMiniAppReturnUrl();
    if (telegramReturnUrl) {
      return telegramReturnUrl;
    }
  }

  const { origin, pathname } = window.location;
  return `${origin}${pathname}`;
}

function buildYooKassaMethod(
  isTelegramWebApp: boolean,
  promoContext?: PlanPromoContext
): PaymentMethodOption {
  const promoNote = promoContext?.rubQuote
    ? t('web.app.promo.prefix', { description: describePromoQuote(promoContext.rubQuote) })
    : promoContext?.code
      ? t('web.app.paymentMethods.cardPromoUnavailable')
      : undefined;

  return {
    provider: 'yookassa',
    label: t('web.app.paymentMethods.yookassaLabel'),
    description: isTelegramWebApp
      ? t('web.app.paymentMethods.yookassaDescriptionMiniApp')
      : t('web.app.paymentMethods.yookassaDescriptionBrowser'),
    note: [isTelegramWebApp ? t('web.app.paymentMethods.yookassaMiniAppNote') : undefined, promoNote]
      .filter(Boolean)
      .join(' '),
  };
}

function buildWalletMethod(plan: Plan, promoContext?: PlanPromoContext): PaymentMethodOption {
  const walletAmount = promoContext?.rubQuote?.final_amount ?? plan.price;
  const promoNote = promoContext?.rubQuote
    ? t('web.app.promo.prefix', { description: describePromoQuote(promoContext.rubQuote) })
    : promoContext?.code
      ? t('web.app.paymentMethods.walletPromoUnavailable')
      : undefined;

  return {
    provider: 'wallet',
    label: t('web.app.paymentMethods.walletLabel'),
    description: t('web.app.paymentMethods.walletDescription'),
    note: [
      t('web.app.paymentMethods.walletDebitNote', {
        amount: formatRubles(walletAmount),
      }),
      promoNote,
    ]
      .filter(Boolean)
      .join(' '),
  };
}

function getAvailableTopUpPaymentMethods(isTelegramWebApp: boolean): PaymentMethodOption[] {
  return [buildYooKassaMethod(isTelegramWebApp)];
}

function getAvailablePlanPaymentMethods(
  plan: Plan,
  isTelegramWebApp: boolean,
  balance: number,
  promoContext?: PlanPromoContext
): PaymentMethodOption[] {
  const methods: PaymentMethodOption[] = [];
  const walletAmount = promoContext?.rubQuote?.final_amount ?? plan.price;

  if (balance >= walletAmount) {
    methods.push(buildWalletMethod(plan, promoContext));
  }

  if (isTelegramWebApp && plan.priceStars) {
    methods.push({
      provider: 'telegram_stars',
      label: t('web.app.paymentMethods.telegramStarsLabel'),
      description: t('web.app.paymentMethods.telegramStarsDescription'),
      note: promoContext?.starsQuote
        ? t('web.app.paymentMethods.telegramStarsNoteWithPromo', {
            amount: promoContext.starsQuote.final_amount,
            description: describePromoQuote(promoContext.starsQuote),
          })
        : promoContext?.code
          ? t('web.app.paymentMethods.telegramStarsPromoUnavailable', {
              amount: plan.priceStars,
            })
          : t('web.app.paymentMethods.telegramStarsNote', {
              amount: plan.priceStars,
            }),
    });
  }

  methods.push(buildYooKassaMethod(isTelegramWebApp, promoContext));
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
  const [hasTelegramContext, setHasTelegramContext] = useState(false);
  const [authView, setAuthView] = useState<AuthView>('default');
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [isLoadingPlans, setIsLoadingPlans] = useState(false);
  const [isTopUpSubmitting, setIsTopUpSubmitting] = useState(false);
  const [checkoutPlanId, setCheckoutPlanId] = useState<string | null>(null);
  const [planPromoCode, setPlanPromoCode] = useState('');
  const [planPromoPlanId, setPlanPromoPlanId] = useState<string | null>(null);
  const [planPromoRubQuote, setPlanPromoRubQuote] = useState<BackendPromoPlanQuoteResponse | null>(null);
  const [planPromoStarsQuote, setPlanPromoStarsQuote] = useState<BackendPromoPlanQuoteResponse | null>(null);
  const [isApplyingPlanPromo, setIsApplyingPlanPromo] = useState(false);
  const [planPromoMessage, setPlanPromoMessage] = useState<PromoRedeemMessage | null>(null);
  const [paymentMethodSelection, setPaymentMethodSelection] = useState<PaymentSelectionState | null>(null);
  const [paymentMethodSubmitting, setPaymentMethodSubmitting] = useState<PaymentMethodProvider | null>(null);
  const [checkoutAttempts, setCheckoutAttempts] = useState<StoredPaymentAttempt[]>([]);
  const [desktopSelectedPlanId, setDesktopSelectedPlanId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<AppTab>('home');
  const [theme, setTheme] = useState<'light' | 'dark'>(getInitialTheme);
  const [referralCopied, setReferralCopied] = useState(false);
  const [supportEmailCopied, setSupportEmailCopied] = useState(false);
  const [referralSummary, setReferralSummary] = useState<BackendReferralSummary | null>(null);
  const [isLoadingReferralSummary, setIsLoadingReferralSummary] = useState(false);
  const [referralFeedFilter, setReferralFeedFilter] = useState<ReferralFeedFilter>('all');
  const [referralFeed, setReferralFeed] = useState<BackendReferralFeedResponse | null>(null);
  const [isLoadingReferralFeed, setIsLoadingReferralFeed] = useState(false);
  const [isLoadingMoreReferralFeed, setIsLoadingMoreReferralFeed] = useState(false);
  const [referralAvailableForWithdrawValue, setReferralAvailableForWithdrawValue] = useState<number | null>(null);
  const [withdrawals, setWithdrawals] = useState<WithdrawalRequestItemView[]>([]);
  const [withdrawalsTotal, setWithdrawalsTotal] = useState(0);
  const [withdrawalMinimumAmount, setWithdrawalMinimumAmount] = useState(0);
  const [isLoadingWithdrawals, setIsLoadingWithdrawals] = useState(false);
  const [isWithdrawalModalOpen, setIsWithdrawalModalOpen] = useState(false);
  const [isWithdrawalSubmitting, setIsWithdrawalSubmitting] = useState(false);
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
  const [settingsPromoCode, setSettingsPromoCode] = useState('');
  const [isRedeemingSettingsPromo, setIsRedeemingSettingsPromo] = useState(false);
  const [settingsPromoMessage, setSettingsPromoMessage] = useState<PromoRedeemMessage | null>(null);
  const [promoLaunchState, setPromoLaunchState] = useState<PromoLaunchState | null>(null);
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
  const settingsPromoIdempotencyKeyRef = useRef<string | null>(null);
  const attemptedWithdrawalsTokenRef = useRef<string | null>(null);
  const attemptedPlansTokenRef = useRef<string | null>(null);
  const attemptedReferralFeedKeyRef = useRef<string | null>(null);
  const referralFeedRequestIdRef = useRef(0);
  const attemptedNotificationsTokenRef = useRef<string | null>(null);
  const attemptedActivePaymentsTokenRef = useRef<string | null>(null);
  const attemptedLedgerEntriesTokenRef = useRef<string | null>(null);
  const lastPrimaryTabRef = useRef<PrimaryAppTab>('home');
  const manualLogoutRef = useRef(false);
  const authViewRef = useRef<AuthView>('default');
  const promoLaunchAppliedRef = useRef(false);
  const promoLaunchQuoteRequestedRef = useRef(false);

  useEffect(() => {
    const pageTitle = (() => {
      if (isLoading) {
        return t('web.loadingScreen.title');
      }

      if (!isAuthenticated) {
        if (authView === 'recovery') {
          return t('web.login.recoveryTitle');
        }

        if (authView === 'recovery-expired') {
          return t('web.login.expiredTitle');
        }

        return null;
      }

      switch (activeTab) {
        case 'home':
          return t('web.bottomNav.home');
        case 'plans':
          return t('web.plans.title');
        case 'notifications':
          return t('web.notificationsPage.title');
        case 'payments':
          return t('web.pendingPayments.title');
        case 'balance-history':
          return t('web.balanceHistory.title');
        case 'referral':
          return t('web.referralPage.title');
        case 'settings':
          return t('web.settings.title');
        case 'faq':
          return t('web.faq.title');
        case 'privacy':
          return t('web.legal.privacy.title');
        case 'terms':
          return t('web.legal.terms.title');
        default:
          return null;
      }
    })();

    document.title = formatDocumentTitle(pageTitle);
  }, [activeTab, authView, isAuthenticated, isLoading]);

  useEffect(() => {
    applyBrowserTabIcon(browserTabLogoUrl);
  }, []);

  const prefetchedBrowserLinkUrlRef = useRef<string | null>(null);
  const prefetchedBrowserLinkPromiseRef = useRef<Promise<string> | null>(null);

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

  const loadPlanPromoQuoteSnapshot = async (
    token: string,
    planId: string,
    promoCode: string,
    currency: 'RUB' | 'XTR'
  ) => {
    const response = await fetch(
      `${BACKEND_API}/api/v1/promos/plans/${encodeURIComponent(planId)}/quote`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          promo_code: promoCode,
          currency,
        }),
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      const { detail, errorCode } = parseApiErrorPayload(
        errorData,
        t('web.app.toasts.planPromoApplyFailed')
      );
      throw new Error(getPromoErrorMessage(errorCode, detail));
    }

    return (await response.json()) as BackendPromoPlanQuoteResponse;
  };

  const redeemPromoCodeSnapshot = async (
    token: string,
    promoCode: string,
    idempotencyKey: string
  ) => {
    const response = await fetch(`${BACKEND_API}/api/v1/promos/redeem`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        code: promoCode,
        idempotency_key: idempotencyKey,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      const { detail, errorCode } = parseApiErrorPayload(
        errorData,
        t('web.app.toasts.settingsPromoActivateFailed')
      );
      throw new Error(getPromoErrorMessage(errorCode, detail));
    }

    return (await response.json()) as BackendPromoRedeemResponse;
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

  const loadReferralFeedSnapshot = async (
    token: string,
    options: {
      limit?: number;
      offset?: number;
      status?: ReferralFeedFilter;
    } = {}
  ) => {
    const params = new URLSearchParams();
    params.set('limit', String(options.limit ?? REFERRAL_FEED_PAGE_SIZE));
    params.set('offset', String(options.offset ?? 0));
    params.set('status', options.status ?? 'all');

    const response = await fetch(`${BACKEND_API}/api/v1/referrals/feed?${params.toString()}`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('Failed to load referral feed from backend');
    }

    return (await response.json()) as BackendReferralFeedResponse;
  };

  const loadWithdrawalsSnapshot = async (
    token: string,
    options: { limit?: number; offset?: number } = {}
  ) => {
    const params = new URLSearchParams();
    params.set('limit', String(options.limit ?? 10));
    params.set('offset', String(options.offset ?? 0));

    const response = await fetch(`${BACKEND_API}/api/v1/withdrawals?${params.toString()}`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('Failed to load withdrawals from backend');
    }

    return (await response.json()) as BackendWithdrawalListResponse;
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
          promoCode: attempt.promoCode,
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
          promoCode?: string;
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
          promoCode?: string;
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
            promoCode: checkout.promoCode,
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
      return t('web.app.toasts.paymentAttemptCancelled');
    }
    if (status === 'expired') {
      return t('web.app.toasts.paymentAttemptExpired');
    }
    if (status === 'failed') {
      return t('web.app.toasts.paymentAttemptFailed');
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

  const openExternalBrowserWindow = (url: string): boolean => {
    if (typeof window === 'undefined' || typeof window.open !== 'function') {
      return false;
    }

    try {
      return window.open(url, '_blank', 'noopener,noreferrer') !== null;
    } catch (err) {
      console.error('External window open error:', err);
      return false;
    }
  };

  const resetPrefetchedBrowserLink = () => {
    prefetchedBrowserLinkUrlRef.current = null;
    prefetchedBrowserLinkPromiseRef.current = null;
  };

  const requestBrowserLinkUrl = async (token: string): Promise<string> => {
    const response = await fetch(`${BACKEND_API}/api/v1/accounts/link-browser`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      const { detail, errorCode } = parseApiErrorPayload(
        errorData,
        t('web.app.toasts.linkCreateFailed')
      );
      throw new Error(getLinkingErrorMessage(errorCode, detail));
    }

    const data = await response.json() as { link_url?: string };
    if (!data.link_url) {
      throw new Error(t('web.app.toasts.linkCreateFailed'));
    }

    return data.link_url;
  };

  const ensureBrowserLinkUrl = async (token: string): Promise<string> => {
    if (prefetchedBrowserLinkUrlRef.current) {
      return prefetchedBrowserLinkUrlRef.current;
    }

    if (!prefetchedBrowserLinkPromiseRef.current) {
      prefetchedBrowserLinkPromiseRef.current = requestBrowserLinkUrl(token)
        .then((linkUrl) => {
          prefetchedBrowserLinkUrlRef.current = linkUrl;
          return linkUrl;
        })
        .finally(() => {
          prefetchedBrowserLinkPromiseRef.current = null;
        });
    }

    return await prefetchedBrowserLinkPromiseRef.current;
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

  // Check if running in Telegram WebApp
  useEffect(() => {
    capturePendingReferralCodeFromUrl();
    const launchState = readPromoLaunchStateFromUrl();
    if (launchState) {
      setPromoLaunchState(launchState);
      setActiveTab(launchState.planId ? 'plans' : launchState.tab ?? (launchState.promoCode ? 'settings' : 'home'));
    }

    const initApp = async () => {
      const shouldInitializeTelegram =
        typeof window !== 'undefined' && hasTelegramLaunchParams();

      if (shouldInitializeTelegram) {
        void loadTelegramScript();
      }

      const tg = getTelegramWebApp();
      if (tg && tg.initData) {
        setHasTelegramContext(true);
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
          tg.expand?.();
          // Auto-authenticate Telegram users
          handleTelegramAuth(tg);
        } else {
          // Desktop Telegram app - treat as browser
          setIsTelegramWebApp(false);
          checkSupabaseAuth();
        }
      } else {
        setHasTelegramContext(false);
        setIsTelegramWebApp(false);
        checkSupabaseAuth();
      }
    };

    initApp();
  }, []);

  useEffect(() => {
    if (!promoLaunchState || promoLaunchAppliedRef.current || !isAuthenticated) {
      return;
    }

    if (promoLaunchState.planId) {
      if (!plans.length) {
        return;
      }

      const selectedPlan = plans.find((plan) => plan.id === promoLaunchState.planId);
      if (!selectedPlan) {
        promoLaunchAppliedRef.current = true;
        toast.error(t('web.app.toasts.promoLaunchPlanUnavailable'));
        return;
      }

      setActiveTab('plans');
      promoLaunchAppliedRef.current = true;
      promoLaunchQuoteRequestedRef.current = false;

      if (promoLaunchState.promoCode) {
        setPlanPromoCode(promoLaunchState.promoCode);
        setPlanPromoPlanId(promoLaunchState.planId);
        setPlanPromoRubQuote(null);
        setPlanPromoStarsQuote(null);
        setPlanPromoMessage({
          tone: 'neutral',
          text: t('web.app.toasts.promoLaunchPlanChecking'),
        });
      }

      void handleBuyPlan(promoLaunchState.planId);
      return;
    }

    if (promoLaunchState.promoCode) {
      const targetTab = promoLaunchState.tab ?? 'settings';
      setActiveTab(targetTab);
      if (targetTab === 'settings') {
        setSettingsPromoCode(promoLaunchState.promoCode);
        setSettingsPromoMessage({
          tone: 'neutral',
          text: t('web.app.toasts.promoLaunchRedeemReady'),
        });
      }
    } else if (promoLaunchState.tab) {
      setActiveTab(promoLaunchState.tab);
    }

    promoLaunchAppliedRef.current = true;
  }, [isAuthenticated, plans, promoLaunchState]);

  useEffect(() => {
    if (!isAuthenticated || !accessToken || !hasTelegramContext || user?.email) {
      resetPrefetchedBrowserLink();
      return;
    }

    void ensureBrowserLinkUrl(accessToken).catch((err) => {
      console.error('Browser link prefetch error:', err);
      resetPrefetchedBrowserLink();
    });
  }, [isAuthenticated, accessToken, hasTelegramContext, user?.email]);

  useEffect(() => {
    if (
      !promoLaunchState?.planId ||
      !promoLaunchState.promoCode ||
      promoLaunchQuoteRequestedRef.current ||
      paymentMethodSelection?.kind !== 'plan' ||
      paymentMethodSelection.planId !== promoLaunchState.planId
    ) {
      return;
    }

    if (
      planPromoPlanId !== promoLaunchState.planId ||
      normalizePromoCodeInput(planPromoCode) !== promoLaunchState.promoCode
    ) {
      return;
    }

    promoLaunchQuoteRequestedRef.current = true;
    void handleApplyPlanPromo();
  }, [paymentMethodSelection, planPromoPlanId, planPromoCode, promoLaunchState, accessToken]);

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

  const handleTelegramAuth = async (tg: TelegramWebAppLike) => {
    try {
      const telegramUser = tg.initDataUnsafe?.user;
      if (!telegramUser) {
        setIsLoading(false);
        return;
      }

      const storedTelegramAuth = readStoredTelegramAuth();
      if (storedTelegramAuth && storedTelegramAuth.telegramUserId === telegramUser.id) {
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
          const { detail } = parseApiErrorPayload(
            errorData,
            t('web.app.toasts.telegramSessionConfirmFailed')
          );
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
          toast.success(t('web.app.toasts.referralClaimed'));
        } else if (referralResult?.reason === 'self_referral') {
          toast.error(t('web.app.toasts.referralSelfNotAllowed'));
        } else if (referralResult?.reason === 'referral_code_not_found') {
          toast.error(t('web.app.toasts.referralInvalid'));
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
        setReferralSummary(null);
        setReferralAvailableForWithdrawValue(null);
        setReferralFeed(null);
        setReferralFeedFilter('all');
        setIsLoadingReferralFeed(false);
        setIsLoadingMoreReferralFeed(false);
        setWithdrawals([]);
        setWithdrawalsTotal(0);
        setWithdrawalMinimumAmount(0);
        setNotifications([]);
        setNotificationsTotal(0);
        setNotificationsUnreadCount(0);
        setActivePayments([]);
        setLedgerEntries([]);
        setLedgerEntriesTotal(0);
        attemptedWithdrawalsTokenRef.current = null;
        attemptedPlansTokenRef.current = null;
        attemptedReferralFeedKeyRef.current = null;
        referralFeedRequestIdRef.current += 1;
        attemptedNotificationsTokenRef.current = null;
        attemptedActivePaymentsTokenRef.current = null;
        attemptedLedgerEntriesTokenRef.current = null;
        setAccessToken(null);
        console.error('Telegram auth error:', err);
        toast.error(
          getFallbackErrorMessage(err, 'web.app.toasts.telegramSessionConfirmFailed')
        );
      }
    } catch (err) {
      clearStoredTelegramAuth();
      setIsAuthenticated(false);
      setUser(null);
      setSubscription(null);
      setPlans([]);
      setReferralSummary(null);
      setReferralAvailableForWithdrawValue(null);
      setReferralFeed(null);
      setReferralFeedFilter('all');
      setIsLoadingReferralFeed(false);
      setIsLoadingMoreReferralFeed(false);
      setWithdrawals([]);
      setWithdrawalsTotal(0);
      setWithdrawalMinimumAmount(0);
      setNotifications([]);
      setNotificationsTotal(0);
      setNotificationsUnreadCount(0);
      setActivePayments([]);
      setLedgerEntries([]);
      setLedgerEntriesTotal(0);
      attemptedWithdrawalsTokenRef.current = null;
      attemptedPlansTokenRef.current = null;
      attemptedReferralFeedKeyRef.current = null;
      referralFeedRequestIdRef.current += 1;
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
    setPlanPromoCode('');
    setPlanPromoPlanId(null);
    setPlanPromoRubQuote(null);
    setPlanPromoStarsQuote(null);
    setPlanPromoMessage(null);
    setReferralSummary(null);
    setReferralAvailableForWithdrawValue(null);
    setReferralFeed(null);
    setReferralFeedFilter('all');
    setIsLoadingReferralFeed(false);
    setIsLoadingMoreReferralFeed(false);
    setWithdrawals([]);
    setWithdrawalsTotal(0);
    setWithdrawalMinimumAmount(0);
    setNotifications([]);
    setNotificationsTotal(0);
    setNotificationsUnreadCount(0);
    setActivePayments([]);
    setLedgerEntries([]);
    setLedgerEntriesTotal(0);
    setCheckoutAttempts([]);
    setPaymentMethodSelection(null);
    setPaymentMethodSubmitting(null);
    setIsWithdrawalModalOpen(false);
    setIsWithdrawalSubmitting(false);
    setSettingsPromoCode('');
    setSettingsPromoMessage(null);
    setIsRedeemingSettingsPromo(false);
    settingsPromoIdempotencyKeyRef.current = null;
    attemptedWithdrawalsTokenRef.current = null;
    attemptedPlansTokenRef.current = null;
    attemptedReferralFeedKeyRef.current = null;
    referralFeedRequestIdRef.current += 1;
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
      setReferralAvailableForWithdrawValue(
        normalizeReferralMetric(summary.available_for_withdraw)
      );
      return true;
    } catch (err) {
      console.error('Error loading referral summary:', err);
      return false;
    } finally {
      setIsLoadingReferralSummary(false);
    }
  };

  const loadReferralFeed = async (
    token: string,
    options: {
      filter?: ReferralFeedFilter;
      silent?: boolean;
    } = {}
  ) => {
    const filter = options.filter ?? referralFeedFilter;
    const requestId = ++referralFeedRequestIdRef.current;
    if (!options.silent) {
      setIsLoadingReferralFeed(true);
    }

    try {
      const snapshot = await loadReferralFeedSnapshot(token, {
        limit: REFERRAL_FEED_PAGE_SIZE,
        offset: 0,
        status: filter,
      });
      if (requestId !== referralFeedRequestIdRef.current) {
        return null;
      }
      setReferralFeed(snapshot);
      return snapshot;
    } catch (err) {
      console.error('Error loading referral feed:', err);
      if (requestId !== referralFeedRequestIdRef.current) {
        return null;
      }
      setReferralFeed({
        items: [],
        total: 0,
        limit: REFERRAL_FEED_PAGE_SIZE,
        offset: 0,
        status_filter: filter,
      });
      return null;
    } finally {
      if (!options.silent && requestId === referralFeedRequestIdRef.current) {
        setIsLoadingReferralFeed(false);
      }
    }
  };

  const loadMoreReferralFeed = async (token: string) => {
    if (!referralFeed || isLoadingMoreReferralFeed) {
      return null;
    }

    if (referralFeed.items.length >= referralFeed.total) {
      return referralFeed;
    }

    const requestId = ++referralFeedRequestIdRef.current;
    setIsLoadingMoreReferralFeed(true);
    try {
      const snapshot = await loadReferralFeedSnapshot(token, {
        limit: REFERRAL_FEED_PAGE_SIZE,
        offset: referralFeed.items.length,
        status: referralFeedFilter,
      });
      if (requestId !== referralFeedRequestIdRef.current) {
        return null;
      }

      const mergedItems = [...referralFeed.items, ...snapshot.items];
      const dedupedItems = mergedItems.filter(
        (item, index, items) =>
          index === items.findIndex((candidate) => candidate.referred_account_id === item.referred_account_id)
      );
      const nextSnapshot: BackendReferralFeedResponse = {
        ...snapshot,
        items: dedupedItems,
      };
      setReferralFeed(nextSnapshot);
      return nextSnapshot;
    } catch (err) {
      console.error('Error loading more referral feed items:', err);
      return null;
    } finally {
      if (requestId === referralFeedRequestIdRef.current) {
        setIsLoadingMoreReferralFeed(false);
      }
    }
  };

  const loadWithdrawals = async (
    token: string,
    options: { silent?: boolean } = {}
  ) => {
    attemptedWithdrawalsTokenRef.current = token;
    if (!options.silent) {
      setIsLoadingWithdrawals(true);
    }

    try {
      const snapshot = await loadWithdrawalsSnapshot(token, { limit: 10, offset: 0 });
      setWithdrawals(snapshot.items.map(mapBackendWithdrawalToView));
      setWithdrawalsTotal(snapshot.total);
      setWithdrawalMinimumAmount(snapshot.minimum_amount_rub);
      setReferralAvailableForWithdrawValue(
        normalizeReferralMetric(snapshot.available_for_withdraw)
      );
      return snapshot;
    } catch (err) {
      console.error('Error loading withdrawals:', err);
      if (!options.silent) {
        setWithdrawals([]);
        setWithdrawalsTotal(0);
      }
      return null;
    } finally {
      if (!options.silent) {
        setIsLoadingWithdrawals(false);
      }
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
      toast.error(t('web.app.toasts.subscriptionLinkUnavailable'));
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
      toast.error(t('web.app.toasts.supportLinkUnavailable'));
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

  const handleOpenSupportEmail = () => {
    const mailtoUrl = buildSupportMailtoUrl({
      browserBrandName: BROWSER_BRAND_NAME,
      supportEmail: SUPPORT_EMAIL,
      user: user
        ? {
            id: user.id,
            name: user.name,
            email: user.email,
            telegramId: user.telegram_id,
          }
        : null,
      subscription: subscription
        ? {
            status: subscription.status,
            expiresAt: subscription.expiresAt,
            isTrial: subscription.isTrial,
          }
        : null,
    });

    if (!mailtoUrl) {
      toast.error(t('web.app.toasts.supportEmailUnavailable'));
      return;
    }

    window.location.assign(mailtoUrl);
  };

  const handleCopySupportEmail = () => {
    if (!SUPPORT_EMAIL) {
      toast.error(t('web.app.toasts.supportEmailUnavailable'));
      return;
    }

    if (typeof navigator === 'undefined' || !navigator.clipboard?.writeText) {
      toast.error(t('web.app.toasts.supportEmailCopyFailed'));
      return;
    }

    void navigator.clipboard
      .writeText(SUPPORT_EMAIL)
      .then(() => {
        setSupportEmailCopied(true);
        toast.success(t('web.app.toasts.supportEmailCopied'));
        window.setTimeout(() => setSupportEmailCopied(false), 2000);
      })
      .catch((err) => {
        console.error('Support email copy error:', err);
        toast.error(t('web.app.toasts.supportEmailCopyFailed'));
      });
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
        const errorData = await response.json().catch(() => null);
        const { detail } = parseApiErrorPayload(
          errorData,
          t('web.app.toasts.notificationReadFailed')
        );
        throw new Error(detail);
      }
    } catch (err) {
      console.error('Mark notification read error:', err);
      toast.error(getFallbackErrorMessage(err, 'web.app.toasts.notificationReadFailed'));
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
        const errorData = await response.json().catch(() => null);
        const { detail } = parseApiErrorPayload(
          errorData,
          t('web.app.toasts.notificationsReadFailed')
        );
        throw new Error(detail);
      }
    } catch (err) {
      console.error('Mark all notifications read error:', err);
      toast.error(getFallbackErrorMessage(err, 'web.app.toasts.notificationsReadFailed'));
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
      toast.error(t('web.app.toasts.paymentLinkUnavailable'));
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
        const { detail, errorCode } = parseApiErrorPayload(
          errorData,
          t('web.app.toasts.referralPrepareFailed')
        );

        if (isReferralAlreadyHandledError(errorCode, detail)) {
          clearPendingReferralCode();
          return false;
        }

        if (isReferralSelfError(errorCode, detail)) {
          clearPendingReferralCode();
          toast.error(t('web.app.toasts.referralSelfNotAllowed'));
          return false;
        }

        if (isReferralCodeNotFoundError(errorCode, detail)) {
          clearPendingReferralCode();
          toast.error(t('web.app.toasts.referralInvalid'));
          return false;
        }

        throw new Error(detail);
      }

      const payload = (await response.json()) as { created: boolean };
      clearPendingReferralCode();
      if (payload.created) {
        toast.success(t('web.app.toasts.referralClaimed'));
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

    if (options.provider === 'telegram_stars' && hasTelegramContext) {
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

    if (
      hasTelegramContext &&
      openTelegramExternalLink(confirmationUrl, {
        tryBrowser: getTelegramPreferredBrowser(),
      })
    ) {
      return;
    }

    if (hasTelegramContext && openExternalBrowserWindow(confirmationUrl)) {
      return;
    }

    if (hasTelegramContext) {
      pendingPaymentRefreshRef.current = false;
      toast.error(t('web.app.toasts.paymentLinkUnavailable'));
      return;
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

    if (!isDesktopBrowser && activeTab !== 'home' && activeTab !== 'referral') {
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
    if (!isAuthenticated || !accessToken || !user || isDesktopBrowser || activeTab !== 'referral') {
      return;
    }

    const nextFeedKey = [
      accessToken,
      user.id,
      referralFeedFilter,
      referralSummary?.referrals_count ?? (user.referralsCount || 0),
      referralSummary?.referral_earnings ?? (user.referralEarnings || 0),
    ].join(':');

    if (attemptedReferralFeedKeyRef.current === nextFeedKey) {
      return;
    }

    attemptedReferralFeedKeyRef.current = nextFeedKey;
    void loadReferralFeed(accessToken, { filter: referralFeedFilter });
  }, [
    isAuthenticated,
    accessToken,
    user,
    isDesktopBrowser,
    activeTab,
    referralFeedFilter,
    referralSummary,
  ]);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      return;
    }

    if (!isDesktopBrowser && activeTab !== 'referral') {
      return;
    }

    if (attemptedWithdrawalsTokenRef.current === accessToken) {
      return;
    }

    void loadWithdrawals(accessToken, { silent: isDesktopBrowser });
  }, [isAuthenticated, accessToken, activeTab, isDesktopBrowser]);

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
          promoCodeByProvider?: Partial<Record<PaymentMethodProvider, string>>;
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
                attempt.provider === method.provider &&
                attempt.promoCode === selection.promoCodeByProvider?.[method.provider]
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
          ? t('web.app.paymentMethods.resumePlanNote')
          : t('web.app.paymentMethods.resumeTopupNote', {
              amount: formatRubles(matchingAttempt.amount),
            });

      return {
        ...method,
        note: method.note ? `${method.note} ${continuationNote}` : continuationNote,
      };
    });

  const createTopUpPayment = async (amount: number, provider: PaymentMethodProvider) => {
    if (!accessToken || !user) return;
    if (provider !== 'yookassa') {
      throw new Error(t('web.app.toasts.topupUnsupportedMethod'));
    }

    const resumableAttempt = await resolveStoredCheckoutAttempt(accessToken, {
      accountId: user.id,
      kind: 'topup',
      provider,
      amount,
    });

    const activeAttempt = resumableAttempt.activeAttempt;
    if (activeAttempt) {
      setIsTopUpModalOpen(false);
      toast.success(t('web.app.toasts.topupResume'));
      openCheckoutConfirmation(activeAttempt.confirmationUrl, {
        provider: activeAttempt.provider,
        onStatusChange: (status) => {
          if (status === 'paid') {
            markCheckoutAttemptStatus(activeAttempt, 'succeeded');
            return;
          }
          if (status === 'cancelled' || status === 'failed') {
            markCheckoutAttemptStatus(activeAttempt, status as StoredPaymentAttemptStatus);
            toast.error(
              status === 'cancelled'
                ? t('web.app.toasts.topupCancelled')
                : t('web.app.toasts.topupFailed')
            );
          }
        },
      });
      return;
    }

    if (resumableAttempt.finalStatus) {
      const message = describeClosedPaymentAttempt(resumableAttempt.finalStatus, {
        successMessage: t('web.app.toasts.topupPreviousSucceeded'),
        retryMessage: t('web.app.toasts.topupRetry'),
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
          success_url: getPaymentReturnUrl({ preferTelegramBot: hasTelegramContext }),
          description: t('web.app.paymentDescription.topup', {
            amount: formatRubles(amount),
          }),
          idempotency_key: createClientIdempotencyKey('topup'),
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const { detail, errorCode } = parseApiErrorPayload(
          errorData,
          t('web.app.toasts.topupCreateRequestFailed')
        );
        throw new Error(getPaymentErrorMessage(errorCode, detail));
      }

      const paymentIntent = (await response.json()) as BackendPaymentIntent;
      if (!paymentIntent.confirmation_url) {
        throw new Error(t('web.app.toasts.paymentMissingConfirmation'));
      }

      persistCheckoutAttempt(paymentIntent, { kind: 'topup' });
      setIsTopUpModalOpen(false);
      toast.success(t('web.app.toasts.topupOpenYookassa'));
      openCheckoutConfirmation(paymentIntent.confirmation_url, {
        provider: paymentIntent.provider,
      });
    } catch (err) {
      console.error('Top-up payment error:', err);
      toast.error(getFallbackErrorMessage(err, 'web.app.toasts.topupCreateFailed'));
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
        const { detail, errorCode } = parseApiErrorPayload(
          errorData,
          t('web.app.toasts.trialActivateFailed')
        );
        throw new Error(getTrialErrorMessage(errorCode, detail));
      }

      const reloaded = await loadUserData(accessToken, user?.avatar);
      if (!reloaded) {
        throw new Error(t('web.app.toasts.trialProfileRefreshFailed'));
      }

      toast.success(t('web.app.toasts.trialActivated'));
    } catch (err) {
      console.error('Trial activation error:', err);
      toast.error(getFallbackErrorMessage(err, 'web.app.toasts.trialActivateFailed'));
    }
  };

  const handlePlanPromoCodeChange = (value: string) => {
    setPlanPromoCode(value);
    setPlanPromoRubQuote(null);
    setPlanPromoStarsQuote(null);
    setPlanPromoMessage(null);
  };

  const handleApplyPlanPromo = async () => {
    if (!accessToken || paymentMethodSelection?.kind !== 'plan') {
      return;
    }

    const selectedPlan = plans.find((plan) => plan.id === paymentMethodSelection.planId);
    if (!selectedPlan) {
      setPlanPromoMessage({
        tone: 'error',
        text: t('web.app.toasts.planNotFound'),
      });
      return;
    }

    const normalizedPromoCode = normalizePromoCodeInput(planPromoCode);
    if (!normalizedPromoCode) {
      setPlanPromoMessage({
        tone: 'error',
        text: t('web.app.toasts.planPromoEnterCode'),
      });
      return;
    }

    setIsApplyingPlanPromo(true);

    let rubQuote: BackendPromoPlanQuoteResponse | null = null;
    let starsQuote: BackendPromoPlanQuoteResponse | null = null;
    let rubError: string | null = null;
    let starsError: string | null = null;

    try {
      try {
        rubQuote = await loadPlanPromoQuoteSnapshot(accessToken, selectedPlan.id, normalizedPromoCode, 'RUB');
      } catch (err) {
        rubError = getFallbackErrorMessage(err, 'web.app.toasts.planPromoRubCheckFailed');
      }

      if (selectedPlan.priceStars) {
        try {
          starsQuote = await loadPlanPromoQuoteSnapshot(accessToken, selectedPlan.id, normalizedPromoCode, 'XTR');
        } catch (err) {
          starsError = getFallbackErrorMessage(err, 'web.app.toasts.planPromoStarsCheckFailed');
        }
      }

      if (!rubQuote && !starsQuote) {
        const message = rubError ?? starsError ?? t('web.app.toasts.planPromoApplyFailed');
        setPlanPromoPlanId(selectedPlan.id);
        setPlanPromoRubQuote(null);
        setPlanPromoStarsQuote(null);
        setPlanPromoMessage({
          tone: 'error',
          text: message,
        });
        toast.error(message);
        return;
      }

      const appliedCode = rubQuote?.promo_code ?? starsQuote?.promo_code ?? normalizedPromoCode;
      const summary = rubQuote
        ? t('web.app.promoMessages.summaryApplied', {
            code: appliedCode,
            description: describePromoQuote(rubQuote),
            extra:
              selectedPlan.priceStars && !starsQuote
                ? t('web.app.promoMessages.starsUnavailableSuffix')
                : '',
          })
        : t('web.app.promoMessages.summaryStarsOnly', {
            code: appliedCode,
            description: describePromoQuote(starsQuote as BackendPromoPlanQuoteResponse),
          });

      setPlanPromoPlanId(selectedPlan.id);
      setPlanPromoCode(appliedCode);
      setPlanPromoRubQuote(rubQuote);
      setPlanPromoStarsQuote(starsQuote);
      setPlanPromoMessage({
        tone: 'success',
        text: summary,
      });
      toast.success(t('web.app.toasts.planPromoApplied'));
    } finally {
      setIsApplyingPlanPromo(false);
    }
  };

  const handleSettingsPromoCodeChange = (value: string) => {
    settingsPromoIdempotencyKeyRef.current = null;
    setSettingsPromoCode(value);
    setSettingsPromoMessage(null);
  };

  const handleRedeemSettingsPromo = async () => {
    if (!accessToken) {
      toast.error(t('web.app.toasts.settingsAuthRequired'));
      return;
    }

    const normalizedPromoCode = normalizePromoCodeInput(settingsPromoCode);
    if (!normalizedPromoCode) {
      setSettingsPromoMessage({
        tone: 'error',
        text: t('web.app.toasts.settingsPromoEnterCode'),
      });
      return;
    }

    const idempotencyKey =
      settingsPromoIdempotencyKeyRef.current ??
      createClientIdempotencyKey(`promo-redeem-${normalizedPromoCode.toLowerCase()}`);
    settingsPromoIdempotencyKeyRef.current = idempotencyKey;

    setIsRedeemingSettingsPromo(true);

    try {
      const result = await redeemPromoCodeSnapshot(accessToken, normalizedPromoCode, idempotencyKey);
      const message =
        typeof result.balance_credit_amount === 'number' && result.balance_credit_amount > 0
          ? t('web.app.promoMessages.activateBalance', {
              code: result.promo_code,
              amount: formatRubles(result.balance_credit_amount),
            })
          : typeof result.granted_duration_days === 'number' && result.granted_duration_days > 0
            ? t('web.app.promoMessages.activateDuration', {
                code: result.promo_code,
                days: result.granted_duration_days,
              })
            : t('web.app.promoMessages.activateGeneric', {
                code: result.promo_code,
              });

      setSettingsPromoCode(result.promo_code);
      setSettingsPromoMessage({
        tone: 'success',
        text: message,
      });

      const reloaded = await loadUserData(accessToken, user?.avatar);
      if (!reloaded) {
        setUser((currentUser) =>
          currentUser ? { ...currentUser, balance: result.balance } : currentUser
        );
      }

      toast.success(message);
    } catch (err) {
      const message = getFallbackErrorMessage(err, 'web.app.toasts.settingsPromoActivateFailed');
      setSettingsPromoMessage({
        tone: 'error',
        text: message,
      });
      toast.error(message);
    } finally {
      setIsRedeemingSettingsPromo(false);
    }
  };

  const createPlanPayment = async (planId: string, provider: PaymentMethodProvider) => {
    if (!accessToken || !user) return;

    const selectedPlan = plans.find((plan) => plan.id === planId);
    if (!selectedPlan) {
      throw new Error(t('web.app.toasts.planNotFound'));
    }

    const promoCodeForProvider =
      provider === 'telegram_stars'
        ? paymentMethodSelection?.kind === 'plan' && planPromoPlanId === planId
          ? planPromoStarsQuote?.promo_code ?? null
          : null
        : paymentMethodSelection?.kind === 'plan' && planPromoPlanId === planId
          ? planPromoRubQuote?.promo_code ?? null
          : null;
    const hasTypedPromoCode =
      paymentMethodSelection?.kind === 'plan' &&
      planPromoPlanId === planId &&
      normalizePromoCodeInput(planPromoCode).length > 0;

    setCheckoutPlanId(planId);

    try {
      if (hasTypedPromoCode && !promoCodeForProvider) {
        toast.error(
          provider === 'telegram_stars'
            ? t('web.app.promoMessages.typedPromoIgnoredStars')
            : t('web.app.promoMessages.typedPromoIgnoredProvider')
        );
      }

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
              promo_code: promoCodeForProvider,
            }),
          }
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => null);
          const { detail, errorCode } = parseApiErrorPayload(
            errorData,
            t('web.app.toasts.walletPurchaseFailed')
          );
          const message = getPaymentErrorMessage(errorCode, detail);
          throw new Error(message);
        }

        const reloaded = await loadUserData(accessToken, user?.avatar);
        if (!reloaded) {
          throw new Error(t('web.app.toasts.walletProfileRefreshFailed'));
        }

        toast.success(t('web.app.toasts.walletActivated'));
        return;
      }

      if (provider === 'telegram_stars' && !selectedPlan.priceStars) {
        throw new Error(t('web.app.toasts.starsPriceMissing'));
      }

      if (provider === 'yookassa' || provider === 'telegram_stars') {
        const resumableAttempt = await resolveStoredCheckoutAttempt(accessToken, {
          accountId: user.id,
          kind: 'plan',
          provider,
          planId,
          promoCode: promoCodeForProvider ?? undefined,
        });

        const activeAttempt = resumableAttempt.activeAttempt;
        if (activeAttempt) {
          toast.success(t('web.app.toasts.planResume'));
          openCheckoutConfirmation(activeAttempt.confirmationUrl, {
            provider: activeAttempt.provider,
            onPaid: () => toast.success(t('web.app.toasts.planPaymentConfirmed')),
            onStatusChange: (status) => {
              if (status === 'paid') {
                markCheckoutAttemptStatus(activeAttempt, 'succeeded');
                return;
              }
              if (status === 'cancelled' || status === 'failed') {
                markCheckoutAttemptStatus(activeAttempt, status as StoredPaymentAttemptStatus);
                toast.error(
                  status === 'cancelled'
                    ? t('web.app.toasts.planCancelled')
                    : t('web.app.toasts.planFailed')
                );
              }
            },
          });
          return;
        }

        if (resumableAttempt.finalStatus) {
          const message = describeClosedPaymentAttempt(resumableAttempt.finalStatus, {
            successMessage: t('web.app.toasts.planPreviousSucceeded'),
            retryMessage: t('web.app.toasts.planRetry'),
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
          description: t('web.app.paymentDescription.plan', {
            planName: selectedPlan ? selectedPlan.name : planId,
          }),
          idempotency_key: createClientIdempotencyKey(`plan-${planId}`),
          promo_code: promoCodeForProvider,
          ...(useTelegramStars
            ? {}
            : { success_url: getPaymentReturnUrl({ preferTelegramBot: hasTelegramContext }) }),
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const { detail, errorCode } = parseApiErrorPayload(
          errorData,
          t('web.app.toasts.planCreateRequestFailed')
        );
        throw new Error(getPaymentErrorMessage(errorCode, detail));
      }

      const paymentIntent = (await response.json()) as BackendPaymentIntent;
      if (!paymentIntent.confirmation_url) {
        throw new Error(t('web.app.toasts.paymentMissingConfirmation'));
      }

      persistCheckoutAttempt(paymentIntent, {
        kind: 'plan',
        planId,
        planName: selectedPlan.name,
        promoCode: promoCodeForProvider ?? undefined,
      });
      toast.success(
        useTelegramStars ? t('web.app.toasts.openStars') : t('web.app.toasts.openPlanYookassa')
      );
      openCheckoutConfirmation(paymentIntent.confirmation_url, {
        provider: paymentIntent.provider,
        onPaid: () => toast.success(t('web.app.toasts.planPaymentConfirmed')),
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
            status === 'cancelled'
              ? t('web.app.toasts.planCancelled')
              : t('web.app.toasts.planFailed')
          );
        },
      });
    } catch (err) {
      console.error('Plan payment error:', err);
      toast.error(getFallbackErrorMessage(err, 'web.app.toasts.topupCreateFailed'));
    } finally {
      setCheckoutPlanId(null);
    }
  };

  const handleBuyPlan = async (planId: string) => {
    const selectedPlan = plans.find((plan) => plan.id === planId);
    if (!selectedPlan) {
      toast.error(t('web.app.toasts.planNotFound'));
      return;
    }

    const methods = attachPaymentAttemptNotes(
      { kind: 'plan', planId },
      getAvailablePlanPaymentMethods(selectedPlan, isTelegramWebApp, user?.balance ?? 0)
    );

    if (!methods.length) {
      toast.error(t('web.app.toasts.planNoMethods'));
      return;
    }

    if (planPromoPlanId !== planId) {
      setPlanPromoPlanId(planId);
      setPlanPromoRubQuote(null);
      setPlanPromoStarsQuote(null);
      setPlanPromoMessage(
        planPromoCode.trim()
          ? {
              tone: 'neutral',
              text: t('web.app.promoMessages.applyHint'),
            }
          : null
      );
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
    if (currentReferralCode) {
      const referralLink = buildBrowserReferralLink(currentReferralCode);
      if (!referralLink) {
        toast.error(t('web.app.toasts.referralPrepareFailed'));
        return;
      }

      void navigator.clipboard
        .writeText(referralLink)
        .then(() => {
          setReferralCopied(true);
          toast.success(t('web.app.toasts.referralCopied'));
          window.setTimeout(() => setReferralCopied(false), 2000);
        })
        .catch((err) => {
          console.error('Referral copy error:', err);
          toast.error(t('web.app.toasts.referralCopyFailed'));
        });
    }
  };

  const handleChangeReferralFeedFilter = (filter: ReferralFeedFilter) => {
    if (filter === referralFeedFilter) {
      return;
    }

    referralFeedRequestIdRef.current += 1;
    attemptedReferralFeedKeyRef.current = null;
    setReferralFeed(null);
    setIsLoadingReferralFeed(false);
    setIsLoadingMoreReferralFeed(false);
    setReferralFeedFilter(filter);
  };

  const handleLoadMoreReferralFeed = () => {
    if (!accessToken || !referralFeed || isLoadingMoreReferralFeed) {
      return;
    }

    void loadMoreReferralFeed(accessToken);
  };

  const handleShareReferralToTelegram = () => {
    if (!currentReferralCode) {
      return;
    }

    const shareUrl = buildTelegramShareReferralUrl(currentReferralCode);
    if (!shareUrl) {
      toast.error(t('web.app.toasts.botLinkUnavailable'));
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
    if (!accessToken) {
      toast.error(t('web.app.toasts.settingsAuthRequired'));
      return;
    }

    if (currentAvailableForWithdraw <= 0) {
      toast.error(t('web.app.toasts.withdrawNoFunds'));
      return;
    }

    const snapshot = await loadWithdrawals(accessToken, { silent: true });
    if (!snapshot) {
      toast.error(t('web.app.toasts.withdrawFormLoadFailed'));
      return;
    }
    setIsWithdrawalModalOpen(true);
  };

  const handleCreateWithdrawal = async (payload: {
    amount: number;
    cardNumber: string;
    comment: string;
  }) => {
    if (!accessToken) {
      toast.error(t('web.app.toasts.settingsAuthRequired'));
      return;
    }

    setIsWithdrawalSubmitting(true);
    try {
      const response = await fetch(`${BACKEND_API}/api/v1/withdrawals`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          amount: payload.amount,
          destination_type: 'card',
          destination_value: payload.cardNumber,
          user_comment: payload.comment.trim() || null,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const { detail, errorCode, errorParams } = parseApiErrorPayload(
          errorData,
          t('web.app.toasts.withdrawCreateFailed')
        );
        throw new Error(getWithdrawalErrorMessage(errorCode, detail, errorParams));
      }

      setIsWithdrawalModalOpen(false);
      toast.success(t('web.app.toasts.withdrawCreated'));

      await Promise.all([
        refreshUserData(),
        loadReferralSummary(accessToken),
        loadWithdrawals(accessToken, { silent: true }),
        activeTab === 'notifications' || isDesktopBrowser
          ? loadNotifications(accessToken, { silent: true })
          : loadNotificationsUnreadCount(accessToken),
      ]);
    } catch (err) {
      console.error('Withdrawal create error:', err);
      toast.error(getFallbackErrorMessage(err, 'web.app.toasts.withdrawCreateFailed'));
    } finally {
      setIsWithdrawalSubmitting(false);
    }
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
      toast.error(t('web.app.toasts.settingsAuthRequired'));
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
        const errorData = await response.json().catch(() => null);
        const { detail, errorCode } = parseApiErrorPayload(
          errorData,
          t('web.app.toasts.linkCreateFailed')
        );
        throw new Error(getLinkingErrorMessage(errorCode, detail));
      }

      const data = await response.json();
      pendingTelegramLinkRefreshRef.current = true;
      window.open(data.link_url, '_blank');
      toast.success(t('web.app.toasts.linkTelegramOpened'));
    } catch (err) {
      console.error('Link Telegram error:', err);
      toast.error(getFallbackErrorMessage(err, 'web.app.toasts.linkTelegramFailed'));
    }
  };

  const handleLinkBrowser = async () => {
    if (!accessToken) {
      toast.error(t('web.app.toasts.settingsAuthRequired'));
      return;
    }

    try {
      const linkUrl = await ensureBrowserLinkUrl(accessToken);

      if (hasTelegramContext) {
        if (
          openTelegramExternalLink(linkUrl, {
            tryBrowser: getTelegramPreferredBrowser(),
          }) ||
          openExternalBrowserWindow(linkUrl)
        ) {
          resetPrefetchedBrowserLink();
          toast.success(t('web.app.toasts.linkBrowserOpened'));
          return;
        }

        throw new Error(t('web.app.toasts.linkBrowserFailed'));
      }

      window.location.href = linkUrl;
      toast.success(t('web.app.toasts.linkBrowserOpened'));
    } catch (err) {
      console.error('Link Browser error:', err);
      toast.error(getFallbackErrorMessage(err, 'web.app.toasts.linkBrowserFailed'));
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
        const errorData = await response.json().catch(() => null);
        const { detail, errorCode } = parseApiErrorPayload(
          errorData,
          t('web.app.toasts.linkBrowserCompleteFailed')
        );
        throw new Error(getLinkingErrorMessage(errorCode, detail));
      }

      clearBrowserLinkCallbackState();
      await loadUserData(token);
      toast.success(t('web.app.toasts.linkBrowserCompleted'));
    } catch (err) {
      console.error('Complete browser link error:', err);
      toast.error(getFallbackErrorMessage(err, 'web.app.toasts.linkBrowserCompleteFailed'));
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
          toast.success(t('web.app.toasts.passwordUpdated'));
        }
      } else {
        toast.success(t('web.app.toasts.passwordUpdated'));
      }
    } catch (err) {
      console.error('Password recovery completion error:', err);
      toast.success(t('web.app.toasts.passwordUpdated'));
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
          <div className="text-[var(--tg-theme-text-color,#000000)]">{t('web.app.loadingProfile')}</div>
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
  const selectedPlanForPaymentSheet =
    paymentMethodSelection?.kind === 'plan'
      ? plans.find((plan) => plan.id === paymentMethodSelection.planId) ?? null
      : null;
  const isPlanPromoResolvedForCurrentSelection =
    paymentMethodSelection?.kind === 'plan' &&
    planPromoPlanId === paymentMethodSelection.planId &&
    Boolean(planPromoRubQuote || planPromoStarsQuote || planPromoMessage?.tone === 'error');
  const currentPlanPromoContext: PlanPromoContext | null =
    paymentMethodSelection?.kind === 'plan'
      ? {
          code: isPlanPromoResolvedForCurrentSelection ? normalizePromoCodeInput(planPromoCode) || null : null,
          rubQuote: planPromoPlanId === paymentMethodSelection.planId ? planPromoRubQuote : null,
          starsQuote: planPromoPlanId === paymentMethodSelection.planId ? planPromoStarsQuote : null,
        }
      : null;
  const paymentMethodSheetMethods =
    paymentMethodSelection?.kind === 'plan' && selectedPlanForPaymentSheet
      ? attachPaymentAttemptNotes(
          {
            kind: 'plan',
            planId: paymentMethodSelection.planId,
            promoCodeByProvider: {
              yookassa: currentPlanPromoContext?.rubQuote?.promo_code,
              telegram_stars: currentPlanPromoContext?.starsQuote?.promo_code,
            },
          },
          getAvailablePlanPaymentMethods(
            selectedPlanForPaymentSheet,
            isTelegramWebApp,
            user.balance,
            currentPlanPromoContext ?? undefined
          )
        )
      : (paymentMethodSelection?.methods ?? []);
  const bottomNavActiveTab: PrimaryAppTab =
    activeTab === 'home' || activeTab === 'plans' || activeTab === 'referral' || activeTab === 'settings'
      ? activeTab
      : lastPrimaryTabRef.current;
  const currentReferralCode = (referralSummary?.referral_code ?? user?.referralCode ?? '') || '';
  const currentReferralsCount =
    referralSummary?.referrals_count ?? (user?.referralsCount || 0);
  const currentReferralEarnings =
    referralSummary?.referral_earnings ?? (user?.referralEarnings || 0);
  const currentAvailableForWithdraw = resolveReferralAmount(
    referralAvailableForWithdrawValue,
    referralSummary?.available_for_withdraw
  );
  const showBrowserSupportEmail = !hasTelegramContext;

  const topUpModalNode = isTopUpModalOpen ? (
    <Suspense fallback={<ModalChunkFallback />}>
      <LazyTopUpModal
        isOpen={isTopUpModalOpen}
        onClose={() => setIsTopUpModalOpen(false)}
        onTopUp={handleTopUpAmount}
        isSubmitting={isTopUpSubmitting}
        activeAttemptAmount={activeTopUpAttempt?.amount ?? null}
      />
    </Suspense>
  ) : null;

  const withdrawalRequestModalNode = isWithdrawalModalOpen ? (
    <Suspense fallback={<ModalChunkFallback />}>
      <LazyWithdrawalRequestModal
        isOpen={isWithdrawalModalOpen}
        onClose={() => setIsWithdrawalModalOpen(false)}
        onSubmit={handleCreateWithdrawal}
        isSubmitting={isWithdrawalSubmitting}
        availableForWithdraw={currentAvailableForWithdraw}
        minimumAmount={withdrawalMinimumAmount}
      />
    </Suspense>
  ) : null;

  const paymentMethodSheetNode = paymentMethodSelection ? (
    <Suspense fallback={<ModalChunkFallback />}>
      <LazyPaymentMethodSheet
        isOpen={Boolean(paymentMethodSelection)}
        title={getPaymentSheetTitle(paymentMethodSelection)}
        subtitle={getPaymentSheetSubtitle(paymentMethodSelection)}
        methods={paymentMethodSheetMethods}
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
        promoCode={paymentMethodSelection?.kind === 'plan' ? planPromoCode : undefined}
        onPromoCodeChange={paymentMethodSelection?.kind === 'plan' ? handlePlanPromoCodeChange : undefined}
        onApplyPromo={paymentMethodSelection?.kind === 'plan' ? handleApplyPlanPromo : undefined}
        isApplyingPromo={isApplyingPlanPromo}
        promoMessage={paymentMethodSelection?.kind === 'plan' ? planPromoMessage : null}
      />
    </Suspense>
  ) : null;

  const renderContent = () => {
    switch (activeTab) {
      case 'home':
        return (
          <LazyHomePage
            subscription={subscriptionData}
            referralData={{
              referralCode: currentReferralCode,
              referralsCount: currentReferralsCount,
              referralEarnings: currentReferralEarnings,
              availableForWithdraw: currentAvailableForWithdraw,
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
          <LazyPlansPage
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
          <LazyNotificationsPage
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
          <LazyPendingPaymentsPage
            items={pendingPayments}
            isLoading={isLoadingActivePayments}
            onBack={handleBackToSettings}
            onResume={handleResumePendingPayment}
          />
        );
      case 'balance-history':
        return (
          <LazyBalanceHistoryPage
            items={ledgerEntries}
            total={ledgerEntriesTotal}
            isLoading={isLoadingLedgerEntries}
            isLoadingMore={isLoadingMoreLedgerEntries}
            onBack={handleBackToSettings}
            onLoadMore={handleLoadMoreLedgerEntries}
          />
        );
      case 'faq':
        return <LazyFaqPage onBack={handleBackToSettings} />;
      case 'privacy':
        return <LazyLegalDocumentPage kind="privacy" onBack={handleBackToSettings} />;
      case 'terms':
        return <LazyLegalDocumentPage kind="terms" onBack={handleBackToSettings} />;
      case 'referral':
        return (
          <LazyReferralPage
            referralCode={currentReferralCode}
            referrals={(referralFeed?.items || []).map((item) => ({
              id: item.referred_account_id,
              name: item.display_name,
              date: item.created_at,
              earned: item.reward_amount,
              status: item.status,
            }))}
            referralsTotal={currentReferralsCount}
            filteredTotal={referralFeed?.total ?? 0}
            activeFilter={referralFeed?.status_filter ?? referralFeedFilter}
            totalEarnings={currentReferralEarnings}
            availableForWithdraw={currentAvailableForWithdraw}
            minimumWithdrawalAmount={withdrawalMinimumAmount}
            rewardRate={referralSummary?.effective_reward_rate ?? 20}
            isLoading={isLoadingReferralFeed || (!referralFeed && isLoadingReferralSummary)}
            isLoadingMore={isLoadingMoreReferralFeed}
            hasMore={(referralFeed?.items.length ?? 0) < (referralFeed?.total ?? 0)}
            withdrawals={withdrawals}
            withdrawalsTotal={withdrawalsTotal}
            isLoadingWithdrawals={isLoadingWithdrawals}
            copied={referralCopied}
            onFilterChange={handleChangeReferralFeedFilter}
            onLoadMore={handleLoadMoreReferralFeed}
            onCopyLink={handleCopyReferral}
            onShareTelegram={handleShareReferralToTelegram}
            onWithdraw={handleWithdraw}
          />
        );
      case 'settings':
        return (
          <LazySettingsPage
            theme={theme}
            onThemeChange={setTheme}
            onLogout={handleLogout}
            showLogout={!isTelegramWebApp}
            user={user}
            onLinkTelegram={handleLinkTelegram}
            onLinkBrowser={handleLinkBrowser}
            isTelegramWebApp={hasTelegramContext}
            notificationUnreadCount={notificationsUnreadCount}
            activePaymentsCount={pendingPayments.length}
            onOpenNotificationsCenter={handleOpenNotificationsTab}
            onOpenPendingPayments={handleOpenPendingPayments}
            onOpenBalanceHistory={handleOpenBalanceHistory}
            onOpenFaq={handleOpenFaq}
            onOpenPrivacy={handleOpenPrivacy}
            onOpenTerms={handleOpenTerms}
            onOpenSupport={handleOpenSupport}
            supportEmail={showBrowserSupportEmail ? SUPPORT_EMAIL : ''}
            onOpenSupportEmail={showBrowserSupportEmail ? handleOpenSupportEmail : undefined}
            onCopySupportEmail={showBrowserSupportEmail ? handleCopySupportEmail : undefined}
            supportEmailCopied={supportEmailCopied}
            promoCode={settingsPromoCode}
            onPromoCodeChange={handleSettingsPromoCodeChange}
            onRedeemPromo={handleRedeemSettingsPromo}
            isRedeemingPromo={isRedeemingSettingsPromo}
            promoMessage={settingsPromoMessage}
          />
        );
      default:
        return null;
    }
  };

  const renderContentWithSuspense = (className: string) => (
    <Suspense fallback={<ChunkFallback className={className} />}>{renderContent()}</Suspense>
  );

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

  const desktopChanges = getTranslationValue<string[]>('web.app.desktop.changes') ?? [];
  const desktopSections = [
    { id: 'overview', label: t('web.app.desktop.sections.overview'), icon: LayoutDashboard },
    { id: 'plans', label: t('web.app.desktop.sections.plans'), icon: CreditCard },
    { id: 'notifications', label: t('web.app.desktop.sections.notifications'), icon: Bell },
    { id: 'referrals', label: t('web.app.desktop.sections.referrals'), icon: Gift },
    { id: 'settings', label: t('web.app.desktop.sections.settings'), icon: SettingsIcon },
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
                {t('web.app.desktop.plansLoadingTitle')}
              </h3>
              <p className="mt-2 max-w-xl text-sm leading-6 text-slate-500 dark:text-slate-300">
                {t('web.app.desktop.plansLoadingBody')}
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
                  {t('web.app.desktop.plansEmptyTitle')}
                </h3>
                <p className="mt-2 max-w-xl text-sm leading-6 text-slate-500 dark:text-slate-300">
                  {t('web.app.desktop.plansEmptyBody')}
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={handleTopUp}
                  className="rounded-2xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
                >
                  {t('web.app.desktop.overviewTopUp')}
                </button>
                <button
                  onClick={() => scrollToSection('overview')}
                  className="rounded-2xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900"
                >
                  {t('web.app.desktop.plansBackToOverview')}
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
            role="button"
            tabIndex={0}
            onClick={() => setDesktopSelectedPlanId(plan.id)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                setDesktopSelectedPlanId(plan.id);
              }
            }}
            className={`relative rounded-[28px] border p-6 transition-all duration-300 ease-out hover:-translate-y-1.5 hover:border-sky-300 hover:bg-white hover:shadow-[0_24px_52px_rgba(15,23,42,0.12)] dark:hover:border-sky-500/50 dark:hover:bg-slate-900 ${
              plan.popular ? 'ring-2 ring-sky-400/60' : ''
            } ${
              (checkoutPlanId ?? desktopSelectedPlanId) === plan.id
                ? 'border-sky-300 bg-white shadow-[0_26px_56px_rgba(37,99,235,0.16)] dark:border-sky-500/60 dark:bg-slate-950'
                : 'border-slate-200 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-900/80'
            }`}
            aria-pressed={(checkoutPlanId ?? desktopSelectedPlanId) === plan.id}
          >
            {plan.popular && (
              <div className="absolute -top-3 left-6 rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-white dark:bg-sky-500 dark:text-slate-950">
                {t('web.app.desktop.planPopularBadge')}
              </div>
            )}
            <div className="space-y-4">
              <div>
                <div className="text-sm font-medium uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                  {t('web.app.desktop.planDuration', { days: plan.duration })}
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
                  setDesktopSelectedPlanId(plan.id);
                  void handleBuyPlan(plan.id);
                }}
                disabled={checkoutPlanId === plan.id}
                className="w-full rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
              >
                {checkoutPlanId === plan.id
                  ? t('web.plans.buttonOpening')
                  : resumablePlanIds.includes(plan.id)
                    ? t('web.plans.buttonResume')
                    : t('web.plans.buttonBuy')}
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
      {topUpModalNode}
      {withdrawalRequestModalNode}
      {paymentMethodSheetNode}

      <div className="mx-auto flex max-w-[1520px] gap-6">
        <aside className="sticky top-8 h-[calc(100vh-4rem)] w-[310px] shrink-0 overflow-y-auto rounded-[32px] border border-white/70 bg-white/82 p-6 shadow-[0_32px_80px_rgba(15,23,42,0.14)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_32px_80px_rgba(2,6,23,0.55)]">
          <div className="flex min-h-0 h-full flex-col">
            <div className="space-y-6">
              <div className="space-y-3">
                <span className="inline-flex items-center rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-sky-700 dark:bg-sky-500/15 dark:text-sky-200">
                  {t('web.app.desktop.workspaceBadge')}
                </span>
                <div>
                  <h1 className="text-2xl font-semibold text-slate-950 dark:text-slate-50">
                    {t('web.app.desktop.workspaceTitle')}
                  </h1>
                  <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                    {t('web.app.desktop.workspaceSubtitle')}
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
                      {user.email || t('web.app.desktop.browserAccount')}
                    </div>
                  </div>
                </div>
                <div className="mt-5 rounded-2xl bg-white/8 p-4 dark:bg-white/5">
                  <div className="text-xs uppercase tracking-[0.16em] text-slate-300">
                    {t('web.app.desktop.balanceLabel')}
                  </div>
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
                <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">
                  {t('web.app.desktop.quickNoteTitle')}
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  {t('web.app.desktop.quickNoteBody')}
                </p>
              </div>
            </div>

            <button
              onClick={handleLogout}
              className="mt-auto flex items-center justify-center gap-2 rounded-2xl bg-[var(--app-danger-bg,#ef4444)] px-4 py-3 text-sm font-semibold text-[var(--app-danger-text,#ffffff)] transition hover:bg-[var(--app-danger-bg-hover,#dc2626)]"
            >
              <LogOut className="h-4 w-4" />
              {t('web.settings.actions.logout')}
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
                  {t('web.app.desktop.overviewBadge')}
                </span>
                <h2 className="text-4xl font-semibold tracking-tight text-slate-950 dark:text-slate-50">
                  {t('web.app.desktop.overviewTitle')}
                </h2>
                <p className="text-base leading-7 text-slate-500 dark:text-slate-300">
                  {t('web.app.desktop.overviewBody')}
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={() => scrollToSection('plans')}
                  className="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900"
                >
                  {t('web.app.desktop.overviewOpenPlans')}
                </button>
                <button
                  onClick={handleTopUp}
                  className="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
                >
                  {t('web.app.desktop.overviewTopUp')}
                </button>
              </div>
            </div>

            <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-[26px] bg-slate-950 p-5 text-white dark:border dark:border-slate-800 dark:bg-slate-900/90">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-300">
                    {t('web.app.desktop.metrics.balanceTitle')}
                  </span>
                  <Wallet className="h-5 w-5 text-slate-300" />
                </div>
                <div className="mt-4 text-3xl font-semibold">{formatRubles(user.balance)} ₽</div>
                <div className="mt-2 text-sm text-slate-300">{t('web.app.desktop.metrics.balanceBody')}</div>
              </div>

              <div className="rounded-[26px] bg-white p-5 shadow-[0_20px_40px_rgba(15,23,42,0.06)] dark:bg-slate-900 dark:shadow-[0_20px_40px_rgba(2,6,23,0.35)]">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                    {t('web.app.desktop.metrics.statusTitle')}
                  </span>
                  <LayoutDashboard className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                </div>
                <div className="mt-4 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                  {subscriptionData.isActive
                    ? t('web.app.desktop.metrics.statusActive', {
                        count: subscriptionData.daysLeft ?? 0,
                        unit: formatDayCount(subscriptionData.daysLeft ?? 0),
                      })
                    : subscriptionData.hasTrial && !subscriptionData.hasUsedTrial
                      ? t('web.app.desktop.metrics.statusTrialAvailable')
                      : t('web.app.desktop.metrics.statusInactive')}
                </div>
                <div className="mt-2 text-sm text-slate-500 dark:text-slate-300">
                  {subscriptionData.isActive
                    ? t('web.app.desktop.metrics.statusBodyActive')
                    : t('web.app.desktop.metrics.statusBodyInactive')}
                </div>
              </div>

              <div className="rounded-[26px] bg-white p-5 shadow-[0_20px_40px_rgba(15,23,42,0.06)] dark:bg-slate-900 dark:shadow-[0_20px_40px_rgba(2,6,23,0.35)]">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                    {t('web.app.desktop.metrics.referralsTitle')}
                  </span>
                  <Gift className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                </div>
                <div className="mt-4 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                  {currentReferralsCount}
                </div>
                <div className="mt-2 text-sm text-slate-500 dark:text-slate-300">
                  {t('web.app.desktop.metrics.referralsBody')}
                </div>
              </div>

              <div className="rounded-[26px] bg-white p-5 shadow-[0_20px_40px_rgba(15,23,42,0.06)] dark:bg-slate-900 dark:shadow-[0_20px_40px_rgba(2,6,23,0.35)]">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                    {t('web.app.desktop.metrics.revenueTitle')}
                  </span>
                  <Sparkles className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                </div>
                <div className="mt-4 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                  {formatRubles(currentReferralEarnings)} ₽
                </div>
                <div className="mt-2 text-sm text-slate-500 dark:text-slate-300">
                  {t('web.app.desktop.metrics.revenueBody')}
                </div>
              </div>
            </div>
          </section>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
            <section
              className="rounded-[32px] border border-white/70 bg-white/82 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
            >
              <div className="border-b border-slate-200/80 px-6 py-5 dark:border-slate-800/80">
                <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">
                  {t('web.app.desktop.subscriptionPanelTitle')}
                </h3>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  {t('web.app.desktop.subscriptionPanelBody')}
                </p>
              </div>
              <div className="space-y-4 p-6 pt-4">
                <div className="min-w-0">
                  <SubscriptionCard
                    subscription={subscriptionData}
                    onActivateTrial={handleActivateTrial}
                    onRenew={() => scrollToSection('plans')}
                    onBuy={() => scrollToSection('plans')}
                    onOpenAccess={handleOpenSubscriptionAccess}
                  />
                </div>
                <div className="rounded-[28px] bg-slate-50 p-5 dark:bg-slate-900">
                  <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">
                    {t('web.app.desktop.changesTitle')}
                  </div>
                  <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-500 dark:text-slate-300">
                    {desktopChanges.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>

            <section
              id="plans"
              className="rounded-[32px] border border-white/70 bg-white/82 p-6 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
            >
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">
                    {t('web.app.desktop.plansPanelTitle')}
                  </h3>
                  <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                    {t('web.app.desktop.plansPanelBody')}
                  </p>
                </div>
                <button
                  onClick={handleTopUp}
                  className="rounded-2xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900"
                >
                  {t('web.header.topUpAction')}
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
                <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">
                  {t('web.app.desktop.referralsPanelTitle')}
                </h3>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  {t('web.app.desktop.referralsPanelBody')}
                </p>
              </div>
              <div className="space-y-4 p-6 pt-4">
                <div className="min-w-0">
                  <ReferralCard
                    referralCode={currentReferralCode}
                    referralsCount={currentReferralsCount}
                    referralEarnings={currentReferralEarnings}
                    availableForWithdraw={currentAvailableForWithdraw}
                    onCopy={handleCopyReferral}
                    onShareTelegram={handleShareReferralToTelegram}
                    onWithdraw={handleWithdraw}
                    copied={referralCopied}
                  />
                </div>
                <div className="grid gap-4 xl:grid-cols-2">
                  <div className="rounded-[24px] bg-slate-50 p-4 dark:bg-slate-900">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                      {t('web.app.desktop.invitedTitle')}
                    </div>
                    <div className="mt-3 text-3xl font-semibold text-slate-950 dark:text-slate-50">
                      {currentReferralsCount}
                    </div>
                  </div>
                  <div className="rounded-[24px] bg-slate-950 p-4 text-white dark:border dark:border-slate-800 dark:bg-slate-900">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-300">
                      {t('web.app.desktop.availableToWithdrawTitle')}
                    </div>
                    <div className="mt-3 text-3xl font-semibold">
                      {formatRubles(currentAvailableForWithdraw)} ₽
                    </div>
                  </div>
                </div>
                <div>
                  <WithdrawalRequestsCard
                    items={withdrawals}
                    total={withdrawalsTotal}
                    isLoading={isLoadingWithdrawals}
                    availableForWithdraw={currentAvailableForWithdraw}
                    minimumAmount={withdrawalMinimumAmount}
                    onCreate={handleWithdraw}
                  />
                </div>
              </div>
            </section>

            <section
              id="settings"
              className="rounded-[32px] border border-white/70 bg-white/82 p-6 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
            >
              <div className="mb-6">
                <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">
                  {t('web.app.desktop.settingsPanelTitle')}
                </h3>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  {t('web.app.desktop.settingsPanelBody')}
                </p>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between rounded-[24px] bg-slate-50 px-4 py-4 dark:bg-slate-900">
                  <div className="flex items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100">
                      {theme === 'dark' ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">
                        {t('web.settings.themeTitle')}
                      </div>
                      <div className="text-sm text-slate-500 dark:text-slate-300">
                        {t('web.app.desktop.themeHint')}
                      </div>
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
                      <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">
                        {t('web.settings.labels.language')}
                      </div>
                      <div className="text-sm text-slate-500 dark:text-slate-300">
                        {t('web.app.desktop.languageHint')}
                      </div>
                    </div>
                  </div>
                  <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                    {t('web.settings.labels.russian')}
                  </div>
                </div>

                <PromoRedeemCard
                  code={settingsPromoCode}
                  onCodeChange={handleSettingsPromoCodeChange}
                  onRedeem={handleRedeemSettingsPromo}
                  isSubmitting={isRedeemingSettingsPromo}
                  message={settingsPromoMessage}
                  className="bg-slate-50 dark:bg-slate-900"
                />

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
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">
                          {t('web.app.desktop.pendingPaymentsTitle')}
                        </div>
                        <div className="text-sm text-slate-500 dark:text-slate-300">
                          {t('web.app.desktop.pendingPaymentsBody')}
                        </div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                      {pendingPayments.length > 0 ? pendingPayments.length : t('web.settings.actions.open')}
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
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">
                          {t('web.app.desktop.balanceHistoryTitle')}
                        </div>
                        <div className="text-sm text-slate-500 dark:text-slate-300">
                          {t('web.app.desktop.balanceHistoryBody')}
                        </div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                      {t('web.settings.actions.open')}
                    </div>
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
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">
                          {t('web.app.desktop.supportTitle')}
                        </div>
                        <div className="text-sm text-slate-500 dark:text-slate-300">
                          {t('web.app.desktop.supportBody')}
                        </div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                      {t('web.settings.actions.go')}
                    </div>
                  </button>

                  {showBrowserSupportEmail ? (
                    <div className="rounded-[24px] border border-slate-200 bg-white px-4 py-4 dark:border-slate-800 dark:bg-slate-950">
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                        <div className="flex items-start gap-3">
                          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-slate-900 shadow-sm dark:bg-slate-900 dark:text-slate-100">
                            <Mail className="h-5 w-5" />
                          </div>
                          <div>
                            <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">
                              {t('web.settings.labels.supportEmail')}
                            </div>
                            <div className="text-sm text-slate-500 dark:text-slate-300">
                              {t('web.settings.supportEmailDescription')}
                            </div>
                          </div>
                        </div>

                        <button
                          onClick={handleOpenSupportEmail}
                          className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:opacity-90 dark:border dark:border-slate-800 dark:bg-slate-900"
                        >
                          {t('web.settings.actions.write')}
                        </button>
                      </div>

                      <div className="mt-4 flex flex-col gap-3 rounded-[20px] bg-slate-50 px-4 py-3 dark:bg-slate-900/80 sm:flex-row sm:items-center sm:justify-between">
                        <div className="min-w-0">
                          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                            {t('web.settings.labels.supportEmailAddress')}
                          </div>
                          <div className="mt-1 break-all text-sm font-medium text-slate-900 dark:text-slate-100">
                            {SUPPORT_EMAIL || t('web.settings.unavailable')}
                          </div>
                        </div>

                        <button
                          onClick={handleCopySupportEmail}
                          disabled={!SUPPORT_EMAIL}
                          className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-900 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:hover:bg-slate-900"
                        >
                          {supportEmailCopied ? (
                            <Check className="h-4 w-4" />
                          ) : (
                            <Copy className="h-4 w-4" />
                          )}
                          {supportEmailCopied
                            ? t('web.settings.actions.copied')
                            : t('web.settings.actions.copy')}
                        </button>
                      </div>
                    </div>
                  ) : null}

                  <button
                    onClick={handleOpenFaq}
                    className="flex items-center justify-between rounded-[24px] border border-slate-200 bg-white px-4 py-4 text-left transition hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-900"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100">
                        <HelpCircle className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">
                          {t('web.app.desktop.faqTitle')}
                        </div>
                        <div className="text-sm text-slate-500 dark:text-slate-300">
                          {t('web.app.desktop.faqBody')}
                        </div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                      {t('web.settings.actions.open')}
                    </div>
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
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">
                          {t('web.app.desktop.privacyTitle')}
                        </div>
                        <div className="text-sm text-slate-500 dark:text-slate-300">
                          {t('web.app.desktop.privacyBody')}
                        </div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                      {t('web.settings.actions.open')}
                    </div>
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
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">
                          {t('web.app.desktop.termsTitle')}
                        </div>
                        <div className="text-sm text-slate-500 dark:text-slate-300">
                          {t('web.app.desktop.termsBody')}
                        </div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                      {t('web.settings.actions.open')}
                    </div>
                  </button>
                </div>

                <button
                  onClick={handleLogout}
                  className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[var(--app-danger-bg,#ef4444)] px-4 py-3 text-sm font-semibold text-[var(--app-danger-text,#ffffff)] transition hover:bg-[var(--app-danger-bg-hover,#dc2626)]"
                >
                  <LogOut className="h-4 w-4" />
                  {t('web.settings.actions.logout')}
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
                <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">
                  {t('web.app.desktop.notificationsPanelTitle')}
                </h3>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  {t('web.app.desktop.notificationsPanelBody')}
                </p>
              </div>
              <div className="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white dark:border dark:border-slate-800 dark:bg-slate-900">
                {notificationsUnreadCount > 0
                  ? t('web.app.statusSummary.unread', { count: notificationsUnreadCount })
                  : t('web.app.statusSummary.allRead')}
              </div>
            </div>

            <Suspense
              fallback={
                <ChunkFallback
                  className="rounded-[24px] bg-slate-50 dark:bg-slate-900"
                  minHeightClassName="min-h-[280px]"
                />
              }
            >
              <LazyNotificationsPage
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
            </Suspense>
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
          {renderContentWithSuspense('p-6')}
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
      {topUpModalNode}
      {withdrawalRequestModalNode}
      {paymentMethodSheetNode}

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
          {renderContentWithSuspense(isCompactBrowserLayout ? 'px-4 py-6' : 'p-6')}
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
