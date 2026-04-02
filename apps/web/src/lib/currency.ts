function getSafeNumber(amount: number | null | undefined): number {
  return typeof amount === 'number' && Number.isFinite(amount) ? amount : 0;
}

export function formatRubles(amount: number | null | undefined): string {
  return Math.trunc(getSafeNumber(amount)).toLocaleString('ru-RU');
}

export function formatAmount(
  amount: number | null | undefined,
  maximumFractionDigits = 2
): string {
  return getSafeNumber(amount).toLocaleString('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits,
  });
}
