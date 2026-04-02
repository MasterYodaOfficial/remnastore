import React from 'react';
import { ArrowRightLeft, CreditCard, Wallet } from 'lucide-react';
import { formatRubles } from '../../lib/currency';
import { t } from '../../lib/i18n';

export interface WithdrawalRequestItemView {
  id: number;
  amount: number;
  destinationType: 'card' | 'sbp';
  destinationLabel: string;
  status: 'new' | 'in_progress' | 'paid' | 'rejected' | 'cancelled';
  userComment?: string | null;
  adminComment?: string | null;
  processedAt?: string | null;
  createdAt: string;
}

interface WithdrawalRequestsCardProps {
  items: WithdrawalRequestItemView[];
  total: number;
  isLoading?: boolean;
  availableForWithdraw: number;
  minimumAmount: number;
  onCreate: () => void;
}

function formatWithdrawalDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function getWithdrawalStatusMeta(status: WithdrawalRequestItemView['status']) {
  switch (status) {
    case 'new':
      return {
        label: t('web.withdrawals.statusNew'),
        className:
          'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-200',
      };
    case 'in_progress':
      return {
        label: t('web.withdrawals.statusInProgress'),
        className:
          'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200',
      };
    case 'paid':
      return {
        label: t('web.withdrawals.statusPaid'),
        className:
          'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-200',
      };
    case 'rejected':
      return {
        label: t('web.withdrawals.statusRejected'),
        className:
          'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-200',
      };
    case 'cancelled':
      return {
        label: t('web.withdrawals.statusCancelled'),
        className:
          'border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200',
      };
    default:
      return {
        label: status,
        className:
          'border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200',
      };
  }
}

export function WithdrawalRequestsCard({
  items,
  total,
  isLoading = false,
  availableForWithdraw,
  minimumAmount,
  onCreate,
}: WithdrawalRequestsCardProps) {
  return (
    <div className="rounded-[24px] border border-slate-200 bg-white p-4 shadow-[0_16px_40px_rgba(15,23,42,0.05)] dark:border-slate-800 dark:bg-slate-950">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-50">
            <ArrowRightLeft className="h-4 w-4 text-[var(--tg-theme-button-color,#3390ec)]" />
            {t('web.withdrawals.title')}
          </div>
          <p className="text-sm leading-6 text-slate-500 dark:text-slate-300">
            {t('web.withdrawals.subtitle')}
          </p>
        </div>
        {availableForWithdraw > 0 ? (
          <button
            onClick={onCreate}
            className="inline-flex items-center gap-2 rounded-xl bg-[var(--tg-theme-button-color,#3390ec)] px-3 py-2 text-sm font-medium text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90"
          >
            <Wallet className="h-4 w-4" />
            {t('web.withdrawals.newRequest')}
          </button>
        ) : null}
      </div>

      <div className="mt-4 rounded-2xl bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-500 dark:bg-slate-900 dark:text-slate-300">
        {availableForWithdraw > 0
          ? t('web.withdrawals.availableAndMinimum', {
              available: formatRubles(availableForWithdraw),
              minimum: formatRubles(minimumAmount),
            })
          : t('web.withdrawals.noAvailable')}
      </div>

      <div className="mt-4 space-y-3">
        {isLoading ? (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
            {t('web.withdrawals.loading')}
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
            {t('web.withdrawals.empty')}
          </div>
        ) : (
          items.map((item) => {
            const statusMeta = getWithdrawalStatusMeta(item.status);

            return (
              <div
                key={item.id}
                className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-900/80"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-lg font-semibold text-slate-950 dark:text-slate-50">
                      {formatRubles(item.amount)} ₽
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-sm text-slate-500 dark:text-slate-300">
                      <CreditCard className="h-4 w-4" />
                      <span>{item.destinationLabel}</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <span
                      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${statusMeta.className}`}
                    >
                      {statusMeta.label}
                    </span>
                    <div className="mt-2 text-xs text-slate-400 dark:text-slate-500">
                      {formatWithdrawalDate(item.createdAt)}
                    </div>
                  </div>
                </div>

                {item.userComment ? (
                  <div className="mt-3 rounded-xl bg-white px-3 py-2 text-sm text-slate-600 dark:bg-slate-950 dark:text-slate-300">
                    {t('web.withdrawals.userCommentPrefix')}: {item.userComment}
                  </div>
                ) : null}

                {item.adminComment ? (
                  <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-100">
                    {t('web.withdrawals.adminCommentPrefix')}: {item.adminComment}
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>

      {total > items.length ? (
        <div className="mt-4 text-xs text-slate-400 dark:text-slate-500">
          {t('web.withdrawals.shownPartial', { shown: items.length, total })}
        </div>
      ) : null}
    </div>
  );
}
