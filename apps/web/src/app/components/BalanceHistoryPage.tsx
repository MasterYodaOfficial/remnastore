import React from 'react';
import { ArrowDownLeft, ArrowUpRight, ChevronRight, History, Wallet } from 'lucide-react';

import { formatRubles } from '../../lib/currency';
import { t } from '../../lib/i18n';
import { InfoPageLayout } from './InfoPageLayout';

export interface BalanceHistoryItemView {
  id: number;
  entryType: string;
  amount: number;
  balanceAfter: number;
  comment?: string | null;
  referenceType?: string | null;
  referenceId?: string | null;
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
      return t('web.balanceHistory.entryLabels.topup');
    case 'subscription_debit':
      return t('web.balanceHistory.entryLabels.subscriptionDebit');
    case 'referral_reward':
      return t('web.balanceHistory.entryLabels.referralReward');
    case 'withdrawal_reserve':
      return t('web.balanceHistory.entryLabels.withdrawalReserve');
    case 'withdrawal_release':
      return t('web.balanceHistory.entryLabels.withdrawalRelease');
    case 'withdrawal_payout':
      return t('web.balanceHistory.entryLabels.withdrawalPayout');
    case 'admin_debit':
      return t('web.balanceHistory.entryLabels.debit');
    case 'merge_credit':
    case 'merge_debit':
      return t('web.balanceHistory.entryLabels.balanceAdjustment');
    default:
      return t('web.balanceHistory.entryLabels.default');
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
      title={t('web.balanceHistory.title')}
      subtitle={t('web.balanceHistory.subtitle')}
      onBack={onBack}
    >
      {isLoading ? (
        <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-5 py-6 text-sm text-[var(--tg-theme-hint-color,#999999)]">
          {t('web.balanceHistory.loading')}
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
                          {t('web.balanceHistory.balanceAfter', {
                            amount: formatRubles(item.balanceAfter),
                          })}
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
              {isLoadingMore ? t('web.balanceHistory.loadingMore') : t('web.balanceHistory.showMore')}
              {!isLoadingMore ? <ChevronRight className="h-4 w-4" /> : null}
            </button>
          ) : null}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-5 py-10 text-center">
          <Wallet className="mx-auto mb-4 h-14 w-14 text-[var(--tg-theme-hint-color,#999999)] opacity-60" />
          <div className="text-base font-semibold text-[var(--tg-theme-text-color,#000000)]">
            {t('web.balanceHistory.emptyTitle')}
          </div>
          <p className="mt-2 text-sm leading-6 text-[var(--tg-theme-hint-color,#999999)]">
            {t('web.balanceHistory.emptyDescription')}
          </p>
        </div>
      )}
    </InfoPageLayout>
  );
}
