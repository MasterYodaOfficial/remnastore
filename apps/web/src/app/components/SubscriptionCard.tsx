import React, { useEffect, useState } from 'react';
import { ExternalLink, Sparkles } from 'lucide-react';
import { t } from '../../lib/i18n';
import { AppLogo } from './AppLogo';

interface SubscriptionCardProps {
  subscription: {
    isActive: boolean;
    daysLeft?: number;
    totalDays?: number;
    expiresAt?: string | null;
    periodStartedAt?: string | null;
    hasTrial: boolean;
    hasUsedTrial: boolean;
    isTrial?: boolean;
    subscriptionUrl?: string | null;
  };
  onActivateTrial: () => void;
  onRenew: () => void;
  onBuy: () => void;
  onOpenAccess: () => void;
}

function getStatusTone(daysLeft?: number) {
  if (daysLeft === undefined || daysLeft > 7) {
    return {
      accent: 'var(--tg-theme-button-color,#3390ec)',
      label: null,
    };
  }

  if (daysLeft > 3) {
    return {
      accent: 'var(--app-warning-color,#ca8a04)',
      label: t('web.subscriptionCard.toneWarning'),
    };
  }

  return {
    accent: 'var(--app-danger-bg,#ef4444)',
    label: t('web.subscriptionCard.toneUrgent'),
  };
}

export function SubscriptionCard({
  subscription,
  onActivateTrial,
  onRenew,
  onBuy,
  onOpenAccess,
}: SubscriptionCardProps) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!subscription.isActive) return;
    const refresh = () => setNow(Date.now());
    const timer = window.setInterval(refresh, 60_000);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [subscription.isActive]);
  const endsAt = Date.parse(subscription.expiresAt ?? '');
  const startsAt = Date.parse(subscription.periodStartedAt ?? '');
  const hasEndDate = Number.isFinite(endsAt);
  const remainingMs = hasEndDate ? Math.max(0, endsAt - now) : null;
  const daysLeft = remainingMs !== null
    ? Math.ceil(remainingMs / 86_400_000)
    : Math.max(0, subscription.daysLeft ?? 0);
  const durationMs = Number.isFinite(startsAt) && hasEndDate && startsAt < endsAt
    ? endsAt - startsAt
    : null;
  const totalDays = durationMs !== null
    ? Math.ceil(durationMs / 86_400_000)
    : subscription.totalDays;
  const progressValue = totalDays !== undefined && totalDays > 0
    ? Math.max(0, Math.min(100, durationMs !== null && remainingMs !== null
      ? (remainingMs / durationMs) * 100
      : (daysLeft / totalDays) * 100))
    : null;
  const statusTone = getStatusTone(daysLeft);
  const configReady = Boolean(subscription.subscriptionUrl);

  return (
    <section className="w-full overflow-hidden rounded-[24px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[linear-gradient(145deg,var(--tg-theme-secondary-bg-color,#f4f4f5)_0%,var(--app-surface-color,#dbe4f2)_100%)]">
      <div className="px-4 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <AppLogo className="h-10 w-10 shrink-0 shadow-[0_10px_24px_rgba(37,99,235,0.18)]" />
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-[var(--tg-theme-text-color,#000000)]">
                {t('web.subscriptionCard.title')}
              </h2>
            </div>
          </div>
          <div
            className="shrink-0 rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-white"
            style={{
              backgroundColor: subscription.isActive
                ? statusTone.accent
                : 'var(--tg-theme-hint-color,#94a3b8)',
            }}
          >
            {subscription.isActive
              ? subscription.isTrial
                ? t('web.subscriptionCard.badgeTrial')
                : t('web.subscriptionCard.badgeActive')
              : subscription.hasTrial && !subscription.hasUsedTrial
                ? t('web.subscriptionCard.badgeCanStart')
                : t('web.subscriptionCard.badgeInactive')}
          </div>
        </div>
      </div>

      {subscription.isActive ? (
        <div className="space-y-4 px-4 pb-4">
          <div className="rounded-[20px] bg-[var(--tg-theme-bg-color,#ffffff)] p-4 shadow-[inset_0_0_0_1px_rgba(15,23,42,0.06)]">
            <div className="flex items-end justify-between gap-4">
              <div>
                <div className="text-3xl font-semibold leading-none text-[var(--tg-theme-text-color,#000000)]">
                  {daysLeft}{' '}
                  <span className="text-base font-medium text-[var(--tg-theme-hint-color,#999999)]">
                    {t('web.subscriptionCard.daysShort')}
                  </span>
                </div>
                <div className="mt-1 text-sm text-[var(--tg-theme-hint-color,#999999)]">
                  {t('web.subscriptionCard.daysLeftLabel')}
                </div>
              </div>
              <div className="flex flex-col items-end gap-2">
                <div
                  className="rounded-full px-3 py-1 text-xs font-semibold"
                  style={{
                    backgroundColor: configReady
                      ? 'rgba(22,163,74,0.12)'
                      : 'rgba(202,138,4,0.12)',
                    color: configReady
                      ? 'var(--app-success-color,#16a34a)'
                      : 'var(--app-warning-color,#ca8a04)',
                  }}
                >
                  {configReady
                    ? t('web.subscriptionCard.configReady')
                    : t('web.subscriptionCard.configSync')}
                </div>
                <div className="text-xs font-medium text-[var(--tg-theme-hint-color,#999999)]">
                  {subscription.isTrial
                    ? t('web.subscriptionCard.trialPeriod')
                    : t('web.subscriptionCard.paidPeriod')}
                </div>
              </div>
            </div>

            {hasEndDate && (
              <div className="mt-4 text-sm text-[var(--tg-theme-hint-color,#999999)]">
                {t('web.subscriptionCard.validUntil', {
                  date: new Intl.DateTimeFormat('ru-RU', {
                    day: 'numeric', month: 'long', year: 'numeric',
                  }).format(endsAt),
                })}
              </div>
            )}

            {statusTone.label && (
              <div className="mt-3 text-sm font-medium" style={{ color: statusTone.accent }}>
                {statusTone.label}
              </div>
            )}

            {progressValue !== null && (
              <div className="mt-4">
                <div className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
                  {t('web.subscriptionCard.periodProgress', { progress: Math.round(progressValue) })}
                </div>
                <div
                  role="progressbar"
                  aria-label={t('web.subscriptionCard.progressLabel')}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(progressValue)}
                  className="mt-2 h-2.5 overflow-hidden rounded-full bg-[rgba(148,163,184,0.18)]"
                >
                  <div
                    className="h-full rounded-full transition-[width]"
                    style={{ width: `${progressValue}%`, backgroundColor: statusTone.accent }}
                  />
                </div>
                <div className="mt-2 text-xs text-[var(--tg-theme-hint-color,#999999)]">
                  {t('web.subscriptionCard.stockValue', { daysLeft, totalDays })}
                </div>
              </div>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <button
              onClick={onOpenAccess}
              disabled={!configReady}
              className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition-all duration-200 hover:-translate-y-0.5 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {t('web.subscriptionCard.openAccess')}
              <ExternalLink className="h-4 w-4 shrink-0" />
            </button>
            <button
              onClick={onRenew}
              className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-button-text-color,#ffffff)] transition-all duration-200 hover:-translate-y-0.5 hover:opacity-90"
            >
              {t('web.subscriptionCard.renew')}
              <Sparkles className="h-4 w-4 shrink-0" />
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3 px-4 pb-4">
          <div className="rounded-[20px] bg-[var(--tg-theme-bg-color,#ffffff)] p-4 shadow-[inset_0_0_0_1px_rgba(15,23,42,0.06)]">
            <div className="text-sm text-[var(--tg-theme-text-color,#000000)]">
              {t('web.subscriptionCard.inactiveHint')}
            </div>
          </div>

          {subscription.hasTrial && !subscription.hasUsedTrial ? (
            <button
              onClick={onActivateTrial}
              className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition-all duration-200 hover:-translate-y-0.5 hover:opacity-90"
            >
              {t('web.subscriptionCard.activateTrial')}
              <Sparkles className="h-4 w-4 shrink-0" />
            </button>
          ) : null}

          <button
            onClick={onBuy}
            className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-button-text-color,#ffffff)] transition-all duration-200 hover:-translate-y-0.5 hover:opacity-90"
          >
            {t('web.subscriptionCard.buyPlan')}
            <ExternalLink className="h-4 w-4 shrink-0" />
          </button>
        </div>
      )}
    </section>
  );
}
