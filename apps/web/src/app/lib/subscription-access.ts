export type SubscriptionAccessSource = 'remote' | 'cache' | 'local_fallback' | 'none';

export interface SubscriptionAccessSnapshot {
  available: boolean;
  source: SubscriptionAccessSource;
  remnawave_user_uuid?: string | null;
  short_uuid?: string | null;
  username?: string | null;
  status?: string | null;
  expires_at?: string | null;
  is_active: boolean;
  days_left?: number | null;
  subscription_url?: string | null;
  links: string[];
  ssconf_links: Record<string, string>;
  traffic_used_bytes?: number | null;
  traffic_limit_bytes?: number | null;
  lifetime_traffic_used_bytes?: number | null;
  refreshed_at: string;
}

export function formatBytes(value?: number | null): string {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    return '0 Б';
  }

  const units = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ'];
  let size = value;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  const digits = size >= 10 || unitIndex === 0 ? 0 : 1;
  return `${size.toFixed(digits)} ${units[unitIndex]}`;
}

export function decodeAccessLinkLabel(link: string): string {
  const hashIndex = link.lastIndexOf('#');
  if (hashIndex >= 0) {
    const encodedLabel = link.slice(hashIndex + 1).trim();
    if (encodedLabel) {
      try {
        return decodeURIComponent(encodedLabel);
      } catch {
        return encodedLabel;
      }
    }
  }

  try {
    const url = new URL(link);
    return url.host || 'Подключение';
  } catch {
    return 'Подключение';
  }
}

export function formatSubscriptionStatus(status?: string | null, isActive?: boolean): string {
  if (isActive) {
    return 'Активна';
  }

  switch ((status || '').toUpperCase()) {
    case 'EXPIRED':
      return 'Истекла';
    case 'DISABLED':
    case 'BLOCKED':
      return 'Отключена';
    case 'LIMITED':
      return 'Ограничена';
    default:
      return 'Не активна';
  }
}
