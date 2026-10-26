import { t } from '../../lib/i18n';

export interface RegisteredDevice {
  hwid: string;
  platform?: string | null;
  os_version?: string | null;
  device_model?: string | null;
  created_at?: string | null;
}

export interface DevicesState {
  base_limit: number;
  extra_count: number;
  renewal_extra_count: number;
  limit: number;
  devices: RegisteredDevice[] | null;
  expires_at: string | null;
  can_purchase: boolean;
  sync_pending: boolean;
  is_active: boolean;
  limit_sync_status?: 'synced' | 'pending' | 'unavailable' | 'conflict';
  panel_limit?: number | null;
}

export interface DevicePurchaseQuote {
  quantity: number;
  amount_rub: number;
  limit: number;
  expires_at: string;
  quote_token: string;
}

export interface DeviceRenewalQuote {
  extra_devices: number;
  extra_device_price_rub: number | null;
  extra_amount_rub: number;
  base_amount_rub: number;
  total_amount_rub: number;
  refund_rub: number;
  expires_at: string;
  base_limit: number;
  limit: number;
}

export class DeviceRequestError extends Error {
  constructor(message: string, public code?: string) { super(message); }
}

export async function deviceRequest<T>(apiBase: string, accessToken: string, path = '',
  options: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const response = await fetch(`${apiBase}/api/v1/devices${path}`, {
    method: options.method ?? 'GET',
    headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
    ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
    signal: options.signal,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null) as { detail?: string; error_code?: string } | null;
    throw new DeviceRequestError(typeof error?.detail === 'string' ? error.detail : t('web.devices.error'), error?.error_code);
  }
  return response.status === 204 ? undefined as T : await response.json() as T;
}

export function deviceDate(value: string | null): string {
  return value ? new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(value)) : '—';
}
