import React from 'react';
import { Users, TrendingUp, DollarSign, Copy, Check, Send, ChevronRight } from 'lucide-react';
import { formatRubles } from '../../lib/currency';
import { t } from '../../lib/i18n';
import { WithdrawalRequestsCard, type WithdrawalRequestItemView } from './WithdrawalRequestsCard';

export type ReferralFeedFilter = 'all' | 'active' | 'pending';

interface Referral {
  id: string;
  name: string;
  date: string;
  earned: number;
  status: 'active' | 'pending';
}

interface ReferralPageProps {
  referralCode: string;
  referrals: Referral[];
  referralsTotal: number;
  filteredTotal?: number;
  activeFilter: ReferralFeedFilter;
  totalEarnings: number;
  availableForWithdraw: number;
  minimumWithdrawalAmount: number;
  rewardRate: number;
  isLoading?: boolean;
  isLoadingMore?: boolean;
  hasMore?: boolean;
  withdrawals: WithdrawalRequestItemView[];
  withdrawalsTotal: number;
  isLoadingWithdrawals?: boolean;
  copied: boolean;
  onFilterChange: (filter: ReferralFeedFilter) => void;
  onLoadMore?: () => void;
  onCopyLink: () => void;
  onShareTelegram: () => void;
  onWithdraw: () => void;
}

function maskWord(value: string): string {
  const trimmed = value.trim();
  if (trimmed.length <= 1) {
    return '•';
  }
  if (trimmed.length <= 3) {
    return `${trimmed.charAt(0)}••`;
  }
  return `${trimmed.charAt(0)}${'•'.repeat(Math.max(2, trimmed.length - 2))}${trimmed.charAt(trimmed.length - 1)}`;
}

function maskReferralIdentity(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) {
    return '•••';
  }

  if (trimmed.includes('@')) {
    const [localPart, domain] = trimmed.split('@');
    if (!domain) {
      return maskWord(trimmed);
    }
    return `${maskWord(localPart)}@${domain}`;
  }

  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (!parts.length) {
    return '•••';
  }

  return parts.slice(0, 2).map(maskWord).join(' ');
}

function formatReferralDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'long',
  }).format(date);
}

export function ReferralPage({
  referralCode,
  referrals,
  referralsTotal,
  filteredTotal = referralsTotal,
  activeFilter,
  totalEarnings,
  availableForWithdraw,
  minimumWithdrawalAmount,
  rewardRate,
  isLoading = false,
  isLoadingMore = false,
  hasMore = false,
  withdrawals,
  withdrawalsTotal,
  isLoadingWithdrawals = false,
  copied,
  onFilterChange,
  onLoadMore,
  onCopyLink,
  onShareTelegram,
  onWithdraw,
}: ReferralPageProps) {
  return (
    <div className="space-y-4 px-4 pb-20 pt-4">
      <div>
        <h1 className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)] mb-2">
          {t('web.referralPage.title')}
        </h1>
        <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
          {t('web.referralPage.subtitle', { rewardRate })}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--app-surface-color,#dbe4f2)] p-4">
          <TrendingUp className="mb-2 h-6 w-6 text-[var(--tg-theme-button-color,#3390ec)]" />
          <div className="mb-1 text-xs text-[var(--tg-theme-hint-color,#999999)]">
            {t('web.referralPage.totalEarningsLabel')}
          </div>
          <div className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)]">
            {formatRubles(totalEarnings)} ₽
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--app-surface-color,#dbe4f2)] p-4">
          <DollarSign className="mb-2 h-6 w-6 text-[var(--app-success-color,#16a34a)]" />
          <div className="mb-1 text-xs text-[var(--tg-theme-hint-color,#999999)]">
            {t('web.referralPage.availableLabel')}
          </div>
          <div className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)]">
            {formatRubles(availableForWithdraw)} ₽
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--app-surface-color,#dbe4f2)] p-4">
        <div className="mb-2 text-xs text-[var(--tg-theme-hint-color,#999999)]">
          {t('web.referralPage.codeLabel')}
        </div>
        <div className="break-all rounded-xl bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-3 py-2 font-mono text-sm text-[var(--tg-theme-text-color,#000000)]">
          {referralCode}
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <button
            onClick={onCopyLink}
            className="flex items-center justify-center gap-2 rounded-xl bg-[var(--tg-theme-button-color,#3390ec)] px-4 py-3 text-sm font-medium text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90"
          >
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copied ? t('web.referralPage.copied') : t('web.referralPage.copy')}
          </button>
          <button
            onClick={onShareTelegram}
            className="flex items-center justify-center gap-2 rounded-xl border border-[var(--tg-theme-button-color,#3390ec)] bg-transparent px-4 py-3 text-sm font-medium text-[var(--tg-theme-button-color,#3390ec)] transition-opacity hover:opacity-90"
          >
            <Send className="h-4 w-4" />
            {t('web.referralPage.shareTelegram')}
          </button>
        </div>
      </div>

      {availableForWithdraw > 0 && (
        <button
          onClick={onWithdraw}
          className="w-full py-3 bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] rounded-xl font-medium hover:opacity-90 transition-opacity"
        >
          {t('web.referralPage.withdrawAction', {
            amount: formatRubles(availableForWithdraw),
          })}
        </button>
      )}

      <WithdrawalRequestsCard
        items={withdrawals}
        total={withdrawalsTotal}
        isLoading={isLoadingWithdrawals}
        availableForWithdraw={availableForWithdraw}
        minimumAmount={minimumWithdrawalAmount}
        onCreate={onWithdraw}
      />

      <div className="space-y-3">
        <h2 className="break-words text-lg font-semibold text-[var(--tg-theme-text-color,#000000)]">
          {t('web.referralPage.referralsTitle', { count: referralsTotal })}
        </h2>

        <div className="flex flex-wrap gap-2">
          {(
            [
              ['all', t('web.referralPage.filterAll')],
              ['active', t('web.referralPage.filterActive')],
              ['pending', t('web.referralPage.filterPending')],
            ] as Array<[ReferralFeedFilter, string]>
          ).map(([filter, label]) => {
            const isActive = activeFilter === filter;
            return (
              <button
                key={filter}
                type="button"
                onClick={() => onFilterChange(filter)}
                aria-pressed={isActive}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)]'
                    : 'border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] text-[var(--tg-theme-text-color,#000000)]'
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>

        {isLoading ? (
          <div className="rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] p-4 text-sm text-[var(--tg-theme-hint-color,#999999)]">
            {t('web.referralPage.loading')}
          </div>
        ) : referrals.length > 0 ? (
          <div className="space-y-3">
            <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] p-3">
              <div className="mb-3 text-xs text-[var(--tg-theme-hint-color,#999999)]">
                {t('web.referralPage.showingCount', {
                  shown: referrals.length,
                  total: filteredTotal,
                })}
              </div>

              <div
                className="max-h-[55vh] space-y-2 overflow-y-auto overscroll-contain pr-1 sm:max-h-[26rem]"
                data-testid="referral-feed-list"
              >
                {referrals.map((referral) => (
                  <div
                    key={referral.id}
                    data-testid="referral-feed-item"
                    className="overflow-hidden rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] p-4"
                  >
                    <div className="mb-2 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--tg-theme-button-color,#3390ec)] font-semibold text-[var(--tg-theme-button-text-color,#ffffff)]">
                          {maskReferralIdentity(referral.name).charAt(0)}
                        </div>
                        <div className="min-w-0">
                          <div className="break-words font-medium text-[var(--tg-theme-text-color,#000000)]">
                            {maskReferralIdentity(referral.name)}
                          </div>
                          <div className="text-xs text-[var(--tg-theme-hint-color,#999999)]">
                            {t('web.referralPage.connectedAt', {
                              date: formatReferralDate(referral.date),
                            })}
                          </div>
                        </div>
                      </div>
                      <div className="min-w-0 text-left sm:text-right">
                        {referral.earned > 0 ? (
                          <div className="break-words font-semibold text-[var(--app-success-color,#16a34a)]">
                            +{formatRubles(referral.earned)} ₽
                          </div>
                        ) : (
                          <div className="break-words font-semibold text-[var(--tg-theme-hint-color,#999999)]">
                            {t('web.referralPage.rewardPending')}
                          </div>
                        )}
                        <div
                          className={`text-xs ${
                            referral.status === 'active'
                              ? 'text-[var(--app-success-color,#16a34a)]'
                              : 'text-[var(--app-warning-color,#ca8a04)]'
                          }`}
                        >
                          {referral.status === 'active'
                            ? t('web.referralPage.rewardConfirmed')
                            : t('web.referralPage.rewardAwaiting')}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {hasMore && onLoadMore ? (
              <button
                type="button"
                data-testid="referral-feed-load-more"
                onClick={onLoadMore}
                disabled={isLoadingMore}
                className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLoadingMore ? t('web.referralPage.loadingMore') : t('web.referralPage.showMore')}
                {!isLoadingMore ? <ChevronRight className="h-4 w-4" /> : null}
              </button>
            ) : null}
          </div>
        ) : (
          <div className="text-center py-12">
            <Users className="w-16 h-16 mx-auto text-[var(--tg-theme-hint-color,#999999)] opacity-50 mb-4" />
            <p className="text-[var(--tg-theme-hint-color,#999999)]">
              {activeFilter === 'all'
                ? t('web.referralPage.emptyTitle')
                : t('web.referralPage.emptyFilteredTitle')}
            </p>
            <p className="text-sm text-[var(--tg-theme-hint-color,#999999)] mt-2">
              {activeFilter === 'all'
                ? t('web.referralPage.emptySubtitle')
                : t('web.referralPage.emptyFilteredSubtitle')}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
