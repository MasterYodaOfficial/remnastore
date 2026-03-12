import React from 'react';
import { ArrowDownLeft, ArrowUpRight, ChevronRight, History, Wallet } from 'lucide-react';

import { formatRubles } from '../../lib/currency';
import { InfoPageLayout } from './InfoPageLayout';

export interface BalanceHistoryItemView {
  id: number;
  entryType: string;
  amount: number;
  balanceAfter: number;
  createdAt: string;
}

interface BalanceHistoryPageProps {
  items: BalanceHistoryItemView[];
  total: number;
  isLoading: boolean;
  isLoadingMore?: boolean;
  onBack: () => void;
  onLoadMore?: () => void;
}

function formatHistoryDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }

  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function getEntryLabel(entryType: string): string {
  switch (entryType) {
    case 'topup_manual':
    case 'topup_payment':
    case 'admin_credit':
    case 'promo_credit':
    case 'refund':
      return 'Пополнение';
    case 'subscription_debit':
      return 'Оплата подписки';
    case 'referral_reward':
      return 'Реферальное начисление';
    case 'withdrawal_reserve':
      return 'Заявка на вывод';
    case 'withdrawal_release':
      return 'Отмена вывода';
    case 'withdrawal_payout':
      return 'Вывод выполнен';
    case 'admin_debit':
      return 'Списание';
    case 'merge_credit':
    case 'merge_debit':
      return 'Корректировка баланса';
    default:
      return 'Операция по балансу';
  }
}

function getEntryAccent(amount: number) {
  if (amount > 0) {
    return {
      badge: 'bg-[var(--app-success-color,#16a34a)] text-white',
      text: 'text-[var(--app-success-color,#16a34a)]',
      icon: ArrowDownLeft,
    };
  }

  return {
    badge: 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900',
    text: 'text-[var(--tg-theme-text-color,#000000)]',
    icon: ArrowUpRight,
  };
}

export function BalanceHistoryPage({
  items,
  total,
  isLoading,
  isLoadingMore = false,
  onBack,
  onLoadMore,
}: BalanceHistoryPageProps) {
  const hasMore = typeof onLoadMore === 'function' && items.length < total;

  return (
    <InfoPageLayout
      title="История баланса"
      subtitle="Пополнения, оплата подписки и другие движения по внутреннему балансу."
      onBack={onBack}
    >
      {isLoading ? (
        <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-5 py-6 text-sm text-[var(--tg-theme-hint-color,#999999)]">
          Загружаем историю операций...
        </div>
      ) : items.length > 0 ? (
        <div className="space-y-3">
          {items.map((item) => {
            const accent = getEntryAccent(item.amount);
            const Icon = accent.icon;
            return (
              <article
                key={item.id}
                className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-3.5"
              >
                <div className="flex items-start gap-3">
                  <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${accent.badge}`}>
                    <Icon className="h-4.5 w-4.5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
                          {getEntryLabel(item.entryType)}
                        </div>
                        <div className="mt-1 inline-flex items-center gap-2 text-xs text-[var(--tg-theme-hint-color,#999999)]">
                          <History className="h-3.5 w-3.5" />
                          {formatHistoryDate(item.createdAt)}
                        </div>
                      </div>
                      <div className={`text-right text-base font-semibold ${accent.text}`}>
                        {item.amount > 0 ? '+' : ''}
                        {formatRubles(item.amount)} ₽
                        <div className="mt-1 text-xs font-medium text-[var(--tg-theme-hint-color,#999999)]">
                          После: {formatRubles(item.balanceAfter)} ₽
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </article>
            );
          })}

          {hasMore ? (
            <button
              onClick={onLoadMore}
              disabled={isLoadingMore}
              className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoadingMore ? 'Загружаем...' : 'Показать еще'}
              {!isLoadingMore ? <ChevronRight className="h-4 w-4" /> : null}
            </button>
          ) : null}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-5 py-10 text-center">
          <Wallet className="mx-auto mb-4 h-14 w-14 text-[var(--tg-theme-hint-color,#999999)] opacity-60" />
          <div className="text-base font-semibold text-[var(--tg-theme-text-color,#000000)]">
            История пока пустая
          </div>
          <p className="mt-2 text-sm leading-6 text-[var(--tg-theme-hint-color,#999999)]">
            Здесь появятся пополнения, покупки подписки, реферальные начисления и другие движения по
            балансу.
          </p>
        </div>
      )}
    </InfoPageLayout>
  );
}
