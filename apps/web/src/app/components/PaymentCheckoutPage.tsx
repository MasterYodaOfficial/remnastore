import React, { useEffect, useRef, useState } from 'react';
import { apiBaseUrl } from '../../../utils/runtime-config';

type Checkout = {
  provider_payment_id: string; amount: number; currency: string; status: string;
  finalized: boolean; confirmation_token: string | null; return_url: string;
};
type Widget = { render: (container: string) => Promise<unknown>; destroy: () => void };
type WidgetConstructor = new (options: {
  confirmation_token: string; return_url: string;
  customization?: { payment_methods: string[] };
  error_callback: () => void;
}) => Widget;

let scriptPromise: Promise<WidgetConstructor> | null = null;
function loadWidget(): Promise<WidgetConstructor> {
  const host = window as typeof window & { YooMoneyCheckoutWidget?: WidgetConstructor };
  if (host.YooMoneyCheckoutWidget) return Promise.resolve(host.YooMoneyCheckoutWidget);
  if (!scriptPromise) scriptPromise = new Promise<WidgetConstructor>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://yookassa.ru/checkout-widget/v1/checkout-widget.js';
    script.referrerPolicy = 'no-referrer';
    script.onload = () => host.YooMoneyCheckoutWidget ? resolve(host.YooMoneyCheckoutWidget) : reject(new Error());
    script.onerror = () => { script.remove(); reject(new Error()); };
    document.head.appendChild(script);
  }).catch(error => { scriptPromise = null; throw error; });
  return scriptPromise;
}

function readLink() {
  const url = new URL(window.location.href);
  const id = url.searchParams.get('payment_id') ?? '';
  const key = `remnastore.checkout.${id}`;
  let ticket = new URLSearchParams(url.hash.slice(1)).get('checkout_token') ?? '';
  try {
    if (ticket) window.sessionStorage.setItem(key, ticket);
    else ticket = window.sessionStorage.getItem(key) ?? '';
  } catch { /* The original link still works without persistent storage. */ }
  if (url.hash) window.history.replaceState({}, '', url.pathname + url.search);
  return { id, ticket, mode: url.searchParams.get('mode') === 'sbp' ? 'sbp' : 'all' };
}

export default function PaymentCheckoutPage() {
  const [link] = useState(readLink);
  const [mode, setMode] = useState(link.mode);
  const [data, setData] = useState<Checkout | null>(null);
  const [error, setError] = useState('');
  const [widgetError, setWidgetError] = useState('');
  const [retry, setRetry] = useState(0);
  const refresh = useRef<(() => void) | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let running = false;
    const poll = async () => {
      if (running || abort.signal.aborted) return;
      if (timer) clearTimeout(timer);
      if (!link.ticket) { setError('Ссылка оплаты недействительна. Откройте платёж из кабинета.'); return; }
      running = true;
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/payments/yookassa/checkout`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ticket: link.ticket }), signal: abort.signal, referrerPolicy: 'no-referrer',
        });
        if (!response.ok) {
          if ([401, 403, 404].includes(response.status)) setData(null);
          throw new Error(response.status === 401 ? 'Ссылка истекла. Откройте платёж из кабинета.' : 'Не удалось загрузить платёж. Попробуйте ещё раз.');
        }
        const next: Checkout = await response.json();
        if (next.provider_payment_id !== link.id) throw new Error('Платёж не соответствует ссылке.');
        if (!abort.signal.aborted) { setData(next); setError(''); }
      } catch (failure) {
        if (!abort.signal.aborted) setError(failure instanceof Error ? failure.message : 'Не удалось проверить оплату.');
      } finally {
        running = false;
        if (!abort.signal.aborted) timer = setTimeout(() => void poll(), 10000);
      }
    };
    refresh.current = () => void poll();
    void poll();
    return () => { abort.abort(); if (timer) clearTimeout(timer); refresh.current = null; };
  }, [link]);

  const token = data?.confirmation_token;
  const returnUrl = data?.return_url;
  useEffect(() => {
    if (!token || !returnUrl) { setWidgetError(''); return; }
    let disposed = false;
    let widget: Widget | undefined;
    setWidgetError('');
    void loadWidget().then(Constructor => {
      if (disposed) return;
      const bankReturnUrl = new URL(window.location.href);
      bankReturnUrl.hash = new URLSearchParams({ checkout_token: link.ticket }).toString();
      widget = new Constructor({
        confirmation_token: token, return_url: bankReturnUrl.href,
        ...(mode === 'sbp' ? { customization: { payment_methods: ['sbp'] } } : {}),
        error_callback: () => { if (!disposed) setWidgetError('Способ оплаты недоступен. Выберите другой способ или повторите попытку.'); },
      });
      return widget.render('yookassa-checkout');
    }).catch(() => { if (!disposed) setWidgetError('Не удалось открыть форму оплаты. Повторите попытку.'); });
    return () => { disposed = true; widget?.destroy(); };
  }, [token, returnUrl, mode, retry, link]);

  const selectMode = (next: string) => {
    setMode(next);
    const url = new URL(window.location.href);
    if (next === 'sbp') url.searchParams.set('mode', 'sbp'); else url.searchParams.delete('mode');
    window.history.replaceState({}, '', url);
  };
  const terminal = data && !['created', 'pending', 'requires_action'].includes(data.status);
  return <main className="mx-auto min-h-screen max-w-xl space-y-5 bg-white p-4 text-slate-900 sm:p-6">
    <h1 className="text-2xl font-semibold">Оплата</h1>
    {data && <p>{data.amount} {data.currency} · Платёж {data.provider_payment_id}</p>}
    {terminal ? <p role="status">{data.status === 'succeeded'
      ? data.finalized ? 'Оплата завершена.' : 'Оплата получена. Завершаем обработку.'
      : 'Платёж отменён или срок оплаты истёк. Создайте новый платёж в кабинете.'}</p>
      : <>
        {token && <nav className="flex gap-3" aria-label="Способы оплаты">
          <button className="rounded-xl border px-4 py-3" aria-pressed={mode === 'all'} onClick={() => selectMode('all')}>Все способы оплаты</button>
          <button className="rounded-xl border px-4 py-3" aria-pressed={mode === 'sbp'} onClick={() => selectMode('sbp')}>Оплатить через СБП</button>
        </nav>}
        {!data && !error && <p role="status">Загружаем платёж…</p>}
        <div id="yookassa-checkout" />
      </>}
    {(error || widgetError) && <p role="alert">{error || widgetError}</p>}
    <button className="rounded-xl border px-4 py-3" onClick={() => { if (widgetError) setRetry(value => value + 1); refresh.current?.(); }}>Проверить оплату</button>
    {returnUrl && <a className="block underline" href={returnUrl}>Вернуться в кабинет</a>}
  </main>;
}
