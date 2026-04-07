import { describe, expect, it } from 'vitest';

import { normalizeReferralMetric, resolveReferralAmount } from './referral-metrics';

describe('referral-metrics', () => {
  it('normalizes finite referral values', () => {
    expect(normalizeReferralMetric(125.9)).toBe(125);
  });

  it('returns null for invalid referral values', () => {
    expect(normalizeReferralMetric(undefined)).toBeNull();
    expect(normalizeReferralMetric(Number.NaN)).toBeNull();
  });

  it('prefers the latest known referral amount over fallback', () => {
    expect(resolveReferralAmount(120, 450)).toBe(120);
  });

  it('falls back to the summary amount when the latest value is missing', () => {
    expect(resolveReferralAmount(null, 450)).toBe(450);
  });

  it('returns zero when both referral amounts are missing', () => {
    expect(resolveReferralAmount(null, null)).toBe(0);
  });
});
