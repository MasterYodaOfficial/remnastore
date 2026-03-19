export type StoredPaymentAttemptStatus =
  | 'created'
  | 'pending'
  | 'requires_action'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'expired';

export type StoredPaymentAttemptKind = 'plan' | 'topup';
export type StoredPaymentAttemptProvider = 'yookassa' | 'telegram_stars';

export interface StoredPaymentAttempt {
  accountId: string;
  kind: StoredPaymentAttemptKind;
  provider: StoredPaymentAttemptProvider;
  amount: number;
  currency: string;
  providerPaymentId: string;
  confirmationUrl: string;
  status: StoredPaymentAttemptStatus;
  expiresAt: string | null;
  planId?: string;
  planName?: string;
  promoCode?: string;
  createdAt: string;
  updatedAt: string;
}

interface PaymentAttemptMatch {
  accountId: string;
  kind: StoredPaymentAttemptKind;
  provider: StoredPaymentAttemptProvider;
  amount?: number;
  planId?: string;
  promoCode?: string;
}

const PAYMENT_ATTEMPTS_STORAGE_KEY = 'remnastore.payment_attempts';
const ACTIVE_ATTEMPT_STATUSES = new Set<StoredPaymentAttemptStatus>([
  'created',
  'pending',
  'requires_action',
]);
const KNOWN_ATTEMPT_STATUSES = new Set<StoredPaymentAttemptStatus>([
  'created',
  'pending',
  'requires_action',
  'succeeded',
  'failed',
  'cancelled',
  'expired',
]);
const MAX_STORED_ATTEMPTS = 24;

function isIsoDateString(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value));
}

function normalizePromoCode(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }

  const normalized = value.trim().toUpperCase();
  return normalized || undefined;
}

function normalizeAttempt(rawValue: unknown): StoredPaymentAttempt | null {
  if (!rawValue || typeof rawValue !== 'object') {
    return null;
  }

  const rawAttempt = rawValue as Partial<StoredPaymentAttempt>;
  if (
    typeof rawAttempt.accountId !== 'string' ||
    !rawAttempt.accountId ||
    (rawAttempt.kind !== 'plan' && rawAttempt.kind !== 'topup') ||
    (rawAttempt.provider !== 'yookassa' && rawAttempt.provider !== 'telegram_stars') ||
    typeof rawAttempt.amount !== 'number' ||
    !Number.isFinite(rawAttempt.amount) ||
    rawAttempt.amount <= 0 ||
    typeof rawAttempt.currency !== 'string' ||
    !rawAttempt.currency ||
    typeof rawAttempt.providerPaymentId !== 'string' ||
    !rawAttempt.providerPaymentId ||
    typeof rawAttempt.confirmationUrl !== 'string' ||
    !rawAttempt.confirmationUrl ||
    !KNOWN_ATTEMPT_STATUSES.has(rawAttempt.status as StoredPaymentAttemptStatus) ||
    !isIsoDateString(rawAttempt.createdAt) ||
    !isIsoDateString(rawAttempt.updatedAt)
  ) {
    return null;
  }

  if (rawAttempt.kind === 'plan' && (typeof rawAttempt.planId !== 'string' || !rawAttempt.planId)) {
    return null;
  }

  return {
    accountId: rawAttempt.accountId,
    kind: rawAttempt.kind,
    provider: rawAttempt.provider,
    amount: rawAttempt.amount,
    currency: rawAttempt.currency,
    providerPaymentId: rawAttempt.providerPaymentId,
    confirmationUrl: rawAttempt.confirmationUrl,
    status: rawAttempt.status as StoredPaymentAttemptStatus,
    expiresAt: isIsoDateString(rawAttempt.expiresAt) ? rawAttempt.expiresAt : null,
    planId: rawAttempt.planId || undefined,
    planName: rawAttempt.planName || undefined,
    promoCode: normalizePromoCode(rawAttempt.promoCode),
    createdAt: rawAttempt.createdAt,
    updatedAt: rawAttempt.updatedAt,
  };
}

function readAllStoredPaymentAttempts(): StoredPaymentAttempt[] {
  if (typeof window === 'undefined') {
    return [];
  }

  const rawValue = window.localStorage.getItem(PAYMENT_ATTEMPTS_STORAGE_KEY);
  if (!rawValue) {
    return [];
  }

  try {
    const parsed = JSON.parse(rawValue) as unknown;
    if (!Array.isArray(parsed)) {
      throw new Error('Expected payment attempts array');
    }

    const attempts = parsed
      .map(normalizeAttempt)
      .filter((attempt): attempt is StoredPaymentAttempt => attempt !== null)
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
      .slice(0, MAX_STORED_ATTEMPTS);

    if (attempts.length !== parsed.length) {
      writeAllStoredPaymentAttempts(attempts);
    }

    return attempts;
  } catch {
    window.localStorage.removeItem(PAYMENT_ATTEMPTS_STORAGE_KEY);
    return [];
  }
}

function writeAllStoredPaymentAttempts(attempts: StoredPaymentAttempt[]) {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.setItem(
    PAYMENT_ATTEMPTS_STORAGE_KEY,
    JSON.stringify(
      attempts
        .slice()
        .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
        .slice(0, MAX_STORED_ATTEMPTS)
    )
  );
}

function matchesAttemptContext(attempt: StoredPaymentAttempt, match: PaymentAttemptMatch): boolean {
  if (
    attempt.accountId !== match.accountId ||
    attempt.kind !== match.kind ||
    attempt.provider !== match.provider
  ) {
    return false;
  }

  if (match.kind === 'plan') {
    return attempt.planId === match.planId && attempt.promoCode === normalizePromoCode(match.promoCode);
  }

  return attempt.amount === match.amount;
}

export function listStoredPaymentAttemptsForAccount(accountId: string): StoredPaymentAttempt[] {
  return readAllStoredPaymentAttempts().filter((attempt) => attempt.accountId === accountId);
}

export function replaceStoredPaymentAttemptsForAccount(
  accountId: string,
  attempts: StoredPaymentAttempt[]
) {
  const allAttempts = readAllStoredPaymentAttempts();
  const otherAttempts = allAttempts.filter((attempt) => attempt.accountId !== accountId);
  writeAllStoredPaymentAttempts([...otherAttempts, ...attempts]);
}

export function getStoredPaymentAttempt(match: PaymentAttemptMatch): StoredPaymentAttempt | null {
  return readAllStoredPaymentAttempts().find((attempt) => matchesAttemptContext(attempt, match)) ?? null;
}

export function upsertStoredPaymentAttempt(nextAttempt: StoredPaymentAttempt) {
  const attempts = readAllStoredPaymentAttempts().filter(
    (attempt) => !matchesAttemptContext(attempt, nextAttempt)
  );
  attempts.push(nextAttempt);
  writeAllStoredPaymentAttempts(attempts);
}

export function removeStoredPaymentAttempt(match: PaymentAttemptMatch) {
  const attempts = readAllStoredPaymentAttempts().filter(
    (attempt) => !matchesAttemptContext(attempt, match)
  );
  writeAllStoredPaymentAttempts(attempts);
}

export function getEffectiveStoredPaymentAttemptStatus(
  attempt: StoredPaymentAttempt,
  now = new Date()
): StoredPaymentAttemptStatus {
  if (!ACTIVE_ATTEMPT_STATUSES.has(attempt.status)) {
    return attempt.status;
  }

  if (!attempt.expiresAt) {
    return attempt.status;
  }

  return Date.parse(attempt.expiresAt) <= now.getTime() ? 'expired' : attempt.status;
}

export function isStoredPaymentAttemptActive(
  attempt: StoredPaymentAttempt,
  now = new Date()
): boolean {
  return ACTIVE_ATTEMPT_STATUSES.has(getEffectiveStoredPaymentAttemptStatus(attempt, now));
}
