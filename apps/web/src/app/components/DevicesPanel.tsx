import React from 'react';
import { ChevronDown, Monitor, Plus, RefreshCw, Smartphone, Trash2 } from 'lucide-react';
import { t } from '../../lib/i18n';
import { DeviceRequestError, deviceDate, deviceRequest, type DevicePurchaseQuote, type DevicesState } from '../lib/devices';

interface DevicesPanelProps {
  apiBase: string;
  accessToken: string;
  balance: number;
  onChanged: () => Promise<unknown>;
  onTopUp: () => void;
  onConnect: () => void;
}

const buttonClass = 'rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] px-4 py-2 text-sm font-medium disabled:opacity-50';
const primaryClass = `${buttonClass} bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#fff)]`;

export function DevicesPanel({ apiBase, accessToken, balance, onChanged, onTopUp, onConnect }: DevicesPanelProps) {
  const [open, setOpen] = React.useState(false);
  const [state, setState] = React.useState<DevicesState | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [quantity, setQuantity] = React.useState(1);
  const [renewalCount, setRenewalCount] = React.useState(0);
  const [quote, setQuote] = React.useState<DevicePurchaseQuote | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [confirmation, setConfirmation] = React.useState<{ hwid: string } | 'reset' | null>(null);
  const purchaseKey = React.useRef('');

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const result = await deviceRequest<DevicesState>(apiBase, accessToken);
      setState(result);
      setRenewalCount(result.renewal_extra_count);
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : t('web.devices.error'));
    } finally { setLoading(false); }
  }, [apiBase, accessToken]);

  React.useEffect(() => { if (open) void load(); }, [open, load]);
  React.useEffect(() => {
    if (!open || !state?.sync_pending) return;
    const timer = window.setInterval(() => { void load(); void onChanged(); }, 15000);
    return () => window.clearInterval(timer);
  }, [open, state?.sync_pending, load, onChanged]);

  const perform = async (action: () => Promise<void>) => {
    setBusy(true); setError(null); setNotice(null);
    try { await action(); }
    catch (failure) {
      if (failure instanceof DeviceRequestError && ['devices_quote_expired', 'devices_quote_changed'].includes(failure.code ?? '')) setQuote(null);
      setError(failure instanceof Error ? failure.message : t('web.devices.error'));
    }
    finally { setBusy(false); }
  };

  const calculate = () => perform(async () => {
    const result = await deviceRequest<DevicePurchaseQuote>(apiBase, accessToken, '/quote', { method: 'POST', body: { quantity } });
    purchaseKey.current = crypto.randomUUID();
    setQuote(result);
  });

  const purchase = () => perform(async () => {
    if (!quote) return;
    const result = await deviceRequest<{ applied: boolean; refunded: boolean }>(apiBase, accessToken, '/purchase', {
      method: 'POST', body: { quote_token: quote.quote_token, idempotency_key: purchaseKey.current },
    });
    setQuote(null);
    setNotice(t(result.refunded ? 'web.devices.refunded' : result.applied ? 'web.devices.success' : 'web.devices.pending'));
    await load(); await onChanged();
  });

  const remove = () => perform(async () => {
    if (!confirmation) return;
    await deviceRequest<void>(apiBase, accessToken, confirmation === 'reset' ? '/reset' : '/remove', {
      method: 'POST', ...(confirmation === 'reset' ? {} : { body: confirmation }),
    });
    setConfirmation(null); await load();
  });

  return (
    <section className="overflow-hidden rounded-2xl bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)]">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="flex w-full items-center justify-between gap-3 p-4 text-left">
        <span className="flex items-center gap-3"><Monitor className="h-5 w-5 text-[var(--tg-theme-button-color,#3390ec)]" />
          <span><span className="block font-semibold">{t('web.devices.title')}</span>
            <span className="block text-sm text-[var(--tg-theme-hint-color,#999)]">{state ? state.limit === 0 ? t('web.devices.unlimited') : t('web.devices.count', { used: state.devices.length, limit: state.limit }) : t('web.devices.summary')}</span>
          </span></span><ChevronDown className={`h-5 w-5 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="space-y-4 border-t border-[var(--app-border-color,rgba(15,23,42,0.12))] p-4">
        {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        {notice && <p role="status" className="text-sm">{notice}</p>}
        {loading && !state && <p>{t('web.devices.loading')}</p>}
        {state && <>
          {state.expires_at && <p className="text-sm text-[var(--tg-theme-hint-color,#999)]">{t('web.devices.expires', { date: deviceDate(state.expires_at) })}</p>}
          {state.sync_pending && <p role="status" className="rounded-xl bg-sky-500/10 p-3 text-sm">{t('web.devices.pending')}</p>}
          <ul className="divide-y divide-[var(--app-border-color,rgba(15,23,42,0.12))]">
            {state.devices.map((device) => <li key={device.hwid} className="flex items-center gap-3 py-3">
              <Smartphone className="h-5 w-5 shrink-0" /><div className="min-w-0 flex-1">
                <p className="break-words font-medium">{device.device_model || device.platform || t('web.devices.unknown')}</p>
                <p className="text-xs text-[var(--tg-theme-hint-color,#999)]">{[device.platform, device.os_version].filter(Boolean).join(' · ')}</p>
                {device.created_at && <p className="text-xs text-[var(--tg-theme-hint-color,#999)]">{t('web.devices.added', { date: deviceDate(device.created_at) })}</p>}
              </div><button type="button" disabled={busy} className={buttonClass} onClick={() => setConfirmation({ hwid: device.hwid })}>{t('web.devices.remove')}</button>
            </li>)}
          </ul>
          {!state.devices.length && <p className="text-sm text-[var(--tg-theme-hint-color,#999)]">{t('web.devices.empty')}</p>}
          <div className="flex flex-wrap gap-2">
            <button type="button" className={buttonClass} onClick={onConnect}>{t('web.devices.connect')}</button>
            <button type="button" aria-label={t('web.devices.refresh')} disabled={busy || loading} className={buttonClass} onClick={() => void load()}><RefreshCw className="h-4 w-4" /></button>
            {state.devices.length > 0 && <button type="button" disabled={busy} onClick={() => setConfirmation('reset')} className={`${buttonClass} text-red-600 dark:text-red-400`}><Trash2 className="mr-1 inline h-4 w-4" />{t('web.devices.reset')}</button>}
          </div>
          {state.can_purchase && <div className="space-y-3 rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] p-4">
            <h3 className="flex items-center gap-2 font-semibold"><Plus className="h-4 w-4" />{t('web.devices.increase')}</h3>
            <label className="flex flex-wrap items-center gap-3 text-sm">{t('web.devices.quantity')}
              <input aria-label={t('web.devices.quantity')} type="number" min={1} max={100 - state.extra_count} value={quantity} disabled={busy}
                onChange={(event) => { setQuantity(Number(event.target.value)); setQuote(null); }} className="w-20 rounded-lg bg-[var(--tg-theme-bg-color,#fff)] p-2" />
            </label>
            {!quote && <button type="button" className={primaryClass} disabled={busy || !Number.isInteger(quantity) || quantity < 1 || quantity > 100 - state.extra_count} onClick={() => void calculate()}>{t('web.devices.calculate')}</button>}
            {quote && <>
              <p className="text-sm">{t('web.devices.quote', { limit: quote.limit, amount: quote.amount_rub })}</p>
              <p className="text-sm text-[var(--tg-theme-hint-color,#999)]">{t('web.devices.balance', { amount: balance })}</p>
              <button type="button" disabled={busy} className={primaryClass} onClick={() => balance < quote.amount_rub ? onTopUp() : void purchase()}>{balance < quote.amount_rub ? t('web.devices.topup') : t('web.devices.pay', { amount: quote.amount_rub })}</button>
            </>}
          </div>}
          {!state.is_active && <p className="text-sm text-[var(--tg-theme-hint-color,#999)]">{t('web.devices.inactive')}</p>}
          {state.extra_count > 0 && <div className="space-y-2 border-t border-[var(--app-border-color,rgba(15,23,42,0.12))] pt-4">
            <label className="block text-sm font-medium">{t('web.devices.renewal')}
              <select value={renewalCount} disabled={busy || state.sync_pending} onChange={(event) => setRenewalCount(Number(event.target.value))} className="ml-3 rounded-lg bg-[var(--tg-theme-bg-color,#fff)] p-2">
                {Array.from({ length: state.extra_count + 1 }, (_, index) => <option key={index} value={index}>{index}</option>)}
              </select>
            </label>
            <p className="text-xs text-[var(--tg-theme-hint-color,#999)]">{t('web.devices.renewalHint')}</p>
            <button type="button" disabled={busy || state.sync_pending || renewalCount === state.renewal_extra_count} className={buttonClass} onClick={() => void perform(async () => {
              await deviceRequest<void>(apiBase, accessToken, '/renewal', { method: 'PUT', body: { extra_count: renewalCount } });
              await load(); setNotice(t('web.devices.renewalSaved'));
            })}>{t('web.devices.saveRenewal')}</button>
          </div>}
        </>}
        {!state && !loading && <button type="button" className={buttonClass} onClick={() => void load()}>{t('web.devices.refresh')}</button>}
      </div>}
      {confirmation && <div role="alertdialog" aria-modal="true" aria-label={t(confirmation === 'reset' ? 'web.devices.resetTitle' : 'web.devices.removeTitle')} className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
        <div className="max-w-md space-y-4 rounded-2xl bg-[var(--tg-theme-bg-color,#fff)] p-6">
          <h3 className="text-lg font-semibold">{t(confirmation === 'reset' ? 'web.devices.resetTitle' : 'web.devices.removeTitle')}</h3>
          <p className="text-sm">{t('web.devices.removeHint')}</p>
          <div className="flex justify-end gap-2"><button type="button" disabled={busy} className={buttonClass} onClick={() => setConfirmation(null)}>{t('web.devices.cancel')}</button><button type="button" disabled={busy} className={primaryClass} onClick={() => void remove()}>{t('web.devices.confirm')}</button></div>
        </div>
      </div>}
    </section>
  );
}
