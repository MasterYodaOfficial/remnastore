import { t } from '../../lib/i18n';
import { telegramBotUrl as TELEGRAM_BOT_URL } from '../../../utils/runtime-config'

export const PENDING_REFERRAL_CODE_STORAGE_KEY = 'remnastore.pending_referral_code';
const SELF_REFERRAL_REJECTION_STORAGE_PREFIX = 'remnastore.self_referral_rejection.';

function normalizeReferralCode(referralCode: string | null | undefined): string | null {
  if (!referralCode) {
    return null;
  }

  const normalized = referralCode.trim();
  return normalized ? normalized : null;
}

function withUpdatedQueryParam(url: URL, key: string, value: string): URL {
  const nextUrl = new URL(url.toString());
  nextUrl.searchParams.set(key, value);
  return nextUrl;
}

export function capturePendingReferralCodeFromUrl() {
  if (typeof window === 'undefined') {
    return;
  }

  const url = new URL(window.location.href);
  const referralCode = normalizeReferralCode(url.searchParams.get('ref'));
  if (!referralCode) {
    return;
  }

  window.localStorage.setItem(PENDING_REFERRAL_CODE_STORAGE_KEY, referralCode);
  url.searchParams.delete('ref');
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
}

export function readPendingReferralCode(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  return normalizeReferralCode(window.localStorage.getItem(PENDING_REFERRAL_CODE_STORAGE_KEY));
}

export function clearPendingReferralCode(expectedCode?: string) {
  if (typeof window === 'undefined') {
    return;
  }

  if (expectedCode !== undefined && readPendingReferralCode() !== normalizeReferralCode(expectedCode)) {
    return;
  }

  window.localStorage.removeItem(PENDING_REFERRAL_CODE_STORAGE_KEY);
}

// Return true only for the first rejection of this account's current code.
export function rememberSelfReferralRejection(accountId: string, referralCode: string): boolean {
  const normalized = normalizeReferralCode(referralCode);
  if (typeof window === 'undefined' || !normalized) {
    return true;
  }
  const key = `${SELF_REFERRAL_REJECTION_STORAGE_PREFIX}${accountId}`;
  const previous = window.localStorage.getItem(key);
  window.localStorage.setItem(key, normalized);
  return previous !== normalized;
}

export function getActiveReferralCode(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const url = new URL(window.location.href);
  return normalizeReferralCode(url.searchParams.get('ref')) || readPendingReferralCode();
}

export function buildBrowserReferralLink(referralCode: string | null | undefined): string {
  const normalized = normalizeReferralCode(referralCode);
  if (typeof window === 'undefined' || !normalized) {
    return '';
  }

  const currentUrl = new URL(window.location.href);
  const referralUrl = new URL(`${currentUrl.origin}${currentUrl.pathname}`);
  referralUrl.searchParams.set('ref', normalized);
  return referralUrl.toString();
}

export function buildTelegramReferralBotUrl(referralCode: string | null | undefined): string {
  const normalized = normalizeReferralCode(referralCode);
  if (!TELEGRAM_BOT_URL) {
    return '';
  }

  const telegramUrl = new URL(TELEGRAM_BOT_URL);
  if (!normalized) {
    return telegramUrl.toString();
  }

  return withUpdatedQueryParam(telegramUrl, 'start', `ref_${normalized}`).toString();
}

export function buildTelegramShareReferralUrl(referralCode: string | null | undefined): string {
  const telegramReferralUrl = buildTelegramReferralBotUrl(referralCode);
  if (!telegramReferralUrl) {
    return '';
  }

  const shareUrl = new URL('https://t.me/share/url');
  shareUrl.searchParams.set('url', telegramReferralUrl);
  shareUrl.searchParams.set('text', t('web.share.referralText'));
  return shareUrl.toString();
}
