import React from 'react';
import { t } from '../../lib/i18n';
import { deviceDate, type DeviceRenewalQuote } from '../lib/devices';

export function DeviceRenewalOptions({ quote, error, onCountChange }: {
  quote: DeviceRenewalQuote | null;
  error: string | null;
  onCountChange: (count: number) => void;
}) {
  return <section aria-label={t('web.devices.checkoutTitle')} className="space-y-2 rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] p-4 text-sm">
    <h3 className="font-semibold">{t('web.devices.checkoutTitle')}</h3>
    {error ? <p role="alert" className="text-red-600 dark:text-red-400">{error}</p> : !quote ? <p role="status">{t('web.devices.loading')}</p> : <>
      <p>{quote.limit === 0 ? t('web.devices.unlimited') : t('web.devices.checkoutLimit', { limit: quote.limit, base: quote.base_limit })}</p>
      {quote.extra_device_price_rub !== null && quote.base_limit > 0 ? <>
        <label className="flex items-center justify-between gap-3">{t('web.devices.quantity')}
          <input aria-label={t('web.devices.quantity')} type="number" min={0} max={100} value={quote.extra_devices}
            onChange={(event) => { const count = Number(event.target.value); if (Number.isInteger(count) && count >= 0 && count <= 100) onCountChange(count); }}
            className="w-20 rounded-xl bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] p-2" />
        </label>
        <p className="text-[var(--tg-theme-hint-color,#999)]">{t('web.devices.checkoutHint')}</p>
      </> : <p className="text-[var(--tg-theme-hint-color,#999)]">{t('web.devices.checkoutUnavailable')}</p>}
      <p>{t('web.devices.checkoutBase', { amount: quote.base_amount_rub })}</p>
      {quote.extra_amount_rub > 0 && <p>{t('web.devices.checkoutExtra', { amount: quote.extra_amount_rub })}</p>}
      <p className="font-semibold">{t('web.devices.checkoutTotal', { amount: quote.total_amount_rub })}</p>
      <p>{t('web.devices.expires', { date: deviceDate(quote.expires_at) })}</p>
      {quote.refund_rub > 0 && <p>{t('web.devices.checkoutRefund', { amount: quote.refund_rub })}</p>}
      {quote.extra_devices > 0 && <p className="text-[var(--tg-theme-hint-color,#999)]">{t('web.devices.checkoutRubOnly')}</p>}
    </>}
  </section>;
}
