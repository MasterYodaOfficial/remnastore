export function normalizeReferralMetric(value: number | null | undefined): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return null;
  }

  return Math.trunc(value);
}

export function resolveReferralAmount(
  primaryValue: number | null | undefined,
  fallbackValue: number | null | undefined = null
): number {
  return normalizeReferralMetric(primaryValue) ?? normalizeReferralMetric(fallbackValue) ?? 0;
}
