// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../utils/runtime-config', () => ({ telegramBotUrl: 'https://t.me/test_bot' }));
import {
  PENDING_REFERRAL_CODE_STORAGE_KEY,
  capturePendingReferralCodeFromUrl,
  clearPendingReferralCode,
  readPendingReferralCode,
  rememberSelfReferralRejection,
} from './referrals';

describe('consuming referral links', () => {
  beforeEach(() => {
    localStorage.clear();
    window.history.replaceState({}, '', '/');
  });

  it('consumes a rejected own link once and keeps warnings separate for each account', () => {
    window.history.replaceState({}, '', '/?ref=OWN-CODE');
    capturePendingReferralCodeFromUrl();
    expect(window.location.search).toBe('');
    expect(rememberSelfReferralRejection('owner', readPendingReferralCode()!)).toBe(true);
    clearPendingReferralCode('OWN-CODE');
    expect(readPendingReferralCode()).toBeNull();

    window.history.replaceState({}, '', '/?ref=OWN-CODE');
    capturePendingReferralCodeFromUrl();
    expect(rememberSelfReferralRejection('owner', readPendingReferralCode()!)).toBe(false);
    expect(rememberSelfReferralRejection('another-account', 'OWN-CODE')).toBe(true);
    expect(rememberSelfReferralRejection('owner', 'NEW-OWN-CODE')).toBe(true);
  });

  it('does not erase a newer referral when an earlier request finishes', () => {
    localStorage.setItem(PENDING_REFERRAL_CODE_STORAGE_KEY, 'NEW-REFERRER');
    clearPendingReferralCode('OLD-REFERRER');
    expect(readPendingReferralCode()).toBe('NEW-REFERRER');
    clearPendingReferralCode('NEW-REFERRER');
    expect(readPendingReferralCode()).toBeNull();
  });
});
