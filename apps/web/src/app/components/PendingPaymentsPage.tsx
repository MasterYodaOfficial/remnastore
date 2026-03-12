import React from 'react';
import { ArrowUpRight, Clock3, CreditCard, RefreshCw, Wallet } from 'lucide-react';

import { formatRubles } from '../../lib/currency';
import { InfoPageLayout } from './InfoPageLayout';

export interface PendingPaymentView {
  provider: 'yookassa' | 'telegram_stars';
  kind: 'plan' | 'topup';
  amount: number;
  currency: string;
  providerPaymentId: string;
  confirmationUrl: string | null;
  status: 'created' | 'pending' | 'requires_action';
  expiresAt: string | null;
  createdAt: string;
  planCode?: string | null;
  planName?: string | null;
  description?: string | null;
}

interface PendingPaymentsPageProps {
  items: PendingPaymentView[];
  isLoading: boolean;
  onBack: () => void;
  onResume: (item: PendingPaymentView) => void;
}

function getProviderLabel(provider: PendingPaymentView['provider']): string {
  return provider === 'telegram_stars' ? 'Telegram Stars' : 'YooKassa';
}

function getPaymentTitle(item: PendingPaymentView): string {
  if (item.kind === 'plan') {
    return item.planName || item.description || 'Оплата тарифа';
  }
  return item.description || `Пополнение на ${formatRubles(item.amount)} ₽`;
}

function formatDeadline(value: string | null): string {
  if (!value) {
    return 'Срок не указан';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return 'Срок не указан';
  }

  const diffMs = date.getTime() - Date.now();
  const diffMinutes = Math.round(diffMs / 60000);
  if (diffMinutes > 0 && diffMinutes < 60) {
    return `Истекает через ${diffMinutes} мин`;
  }

  return `Доступно до ${new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)}`;
}

export function PendingPaymentsPage({
  items,
  isLoading,
  onBack,
  onResume,
}: PendingPaymentsPageProps) {
  return (
    <InfoPageLayout
      title="Незавершенные оплаты"
      subtitle="Текущие попытки оплаты, которые еще можно продолжить без создания новой ссылки."
      onBack={onBack}
    >
      <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[linear-gradient(135deg,var(--tg-theme-secondary-bg-color,#f4f4f5)_0%,var(--app-surface-color,#dbe4f2)_100%)] p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--tg-theme-hint-color,#999999)]">
              Активные попытки
            </div>
            <div className="mt-3 text-3xl font-semibold text-[var(--tg-theme-text-color,#000000)]">
              {items.length}
            </div>
            <p className="mt-2 text-sm leading-6 text-[var(--app-muted-contrast,#475569)]">
              Если ссылка оплаты еще жива, ее можно открыть повторно и завершить без создания новой операции.
            </p>
          </div>
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)]">
            <RefreshCw className="h-5 w-5" />
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-5 py-6 text-sm text-[var(--tg-theme-hint-color,#999999)]">
          Проверяем активные оплаты...
        </div>
      ) : items.length > 0 ? (
        <div className="space-y-3">
          {items.map((item) => (
            <article
              key={`${item.provider}:${item.providerPaymentId}`}
              className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] p-4"
            >
              <div className="flex items-start gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)]">
                  {item.kind === 'topup' ? <Wallet className="h-5 w-5" /> : <CreditCard className="h-5 w-5" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
                        {getPaymentTitle(item)}
                      </div>
                      <div className="mt-1 text-xs uppercase tracking-[0.14em] text-[var(--tg-theme-hint-color,#999999)]">
                        {item.kind === 'plan' ? 'Покупка тарифа' : 'Пополнение баланса'} • {getProviderLabel(item.provider)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-lg font-semibold text-[var(--tg-theme-text-color,#000000)]">
                        {item.currency === 'RUB' ? `${formatRubles(item.amount)} ₽` : `${item.amount} ${item.currency}`}
                      </div>
                      <div className="mt-1 text-xs text-[var(--tg-theme-hint-color,#999999)]">
                        {item.status === 'requires_action' ? 'Нужно действие' : 'Ожидает оплату'}
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-[var(--app-muted-contrast,#475569)]">
                    <div className="inline-flex items-center gap-2">
                      <Clock3 className="h-4 w-4 text-[var(--tg-theme-hint-color,#999999)]" />
                      {formatDeadline(item.expiresAt)}
                    </div>
                    <div className="text-xs text-[var(--tg-theme-hint-color,#999999)]">
                      ID: {item.providerPaymentId}
                    </div>
                  </div>

                  <button
                    onClick={() => onResume(item)}
                    disabled={!item.confirmationUrl}
                    className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[var(--tg-theme-button-color,#3390ec)] px-4 py-2.5 text-sm font-semibold text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Продолжить оплату
                    <ArrowUpRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-5 py-10 text-center">
          <CreditCard className="mx-auto mb-4 h-14 w-14 text-[var(--tg-theme-hint-color,#999999)] opacity-60" />
          <div className="text-base font-semibold text-[var(--tg-theme-text-color,#000000)]">
            Активных оплат нет
          </div>
          <p className="mt-2 text-sm leading-6 text-[var(--tg-theme-hint-color,#999999)]">
            Когда появится незавершенная оплата, ее можно будет продолжить отсюда без лишних действий.
          </p>
        </div>
      )}
    </InfoPageLayout>
  );
}
