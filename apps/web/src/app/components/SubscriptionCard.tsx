import React from 'react';
import { ExternalLink, Shield, Sparkles } from 'lucide-react';

interface SubscriptionCardProps {
  subscription: {
    isActive: boolean;
    daysLeft?: number;
    totalDays?: number;
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

function getSafeTotalDays(daysLeft?: number, totalDays?: number): number {
  if (typeof totalDays === 'number' && totalDays > 0) {
    return totalDays;
  }

  if (typeof daysLeft === 'number' && daysLeft > 0) {
    return Math.max(daysLeft, 30);
  }

  return 30;
}

function getStatusTone(daysLeft?: number) {
  if (!daysLeft || daysLeft > 7) {
    return {
      accent: 'var(--tg-theme-button-color,#3390ec)',
      label: 'Спокойный запас',
    };
  }

  if (daysLeft > 3) {
    return {
      accent: 'var(--app-warning-color,#ca8a04)',
      label: 'Лучше продлить заранее',
    };
  }

  return {
    accent: 'var(--app-danger-bg,#ef4444)',
    label: 'Заканчивается скоро',
  };
}

export function SubscriptionCard({
  subscription,
  onActivateTrial,
  onRenew,
  onBuy,
  onOpenAccess,
}: SubscriptionCardProps) {
  const daysLeft = Math.max(0, subscription.daysLeft ?? 0);
  const totalDays = getSafeTotalDays(subscription.daysLeft, subscription.totalDays);
  const progressValue = subscription.isActive ? Math.min(100, (daysLeft / totalDays) * 100) : 0;
  const statusTone = getStatusTone(subscription.daysLeft);
  const configReady = Boolean(subscription.subscriptionUrl);

  return (
    <section className="m-4 overflow-hidden rounded-[24px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[linear-gradient(145deg,var(--tg-theme-secondary-bg-color,#f4f4f5)_0%,var(--app-surface-color,#dbe4f2)_100%)]">
      <div className="px-4 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] shadow-[0_10px_24px_rgba(37,99,235,0.18)]">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-[var(--tg-theme-text-color,#000000)]">
                Подписка
              </h2>
              <p className="mt-1 text-sm text-[var(--tg-theme-hint-color,#999999)]">
                {subscription.isActive ? 'Доступ активен' : 'Доступ не запущен'}
              </p>
            </div>
          </div>
          <div
            className="rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-white"
            style={{
              backgroundColor: subscription.isActive
                ? statusTone.accent
                : 'var(--tg-theme-hint-color,#94a3b8)',
            }}
          >
            {subscription.isActive
              ? subscription.isTrial
                ? 'Trial'
                : 'Активна'
              : subscription.hasTrial && !subscription.hasUsedTrial
                ? 'Можно стартовать'
                : 'Не активна'}
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
                    дн.
                  </span>
                </div>
                <div className="mt-1 text-sm text-[var(--tg-theme-hint-color,#999999)]">
                  До окончания доступа
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
                  {configReady ? 'Конфиг готов' : 'Синхронизация'}
                </div>
                <div className="text-xs font-medium text-[var(--tg-theme-hint-color,#999999)]">
                  {subscription.isTrial ? 'Пробный период' : 'Платный период'}
                </div>
              </div>
            </div>

            <div className="mt-4 flex items-center justify-between gap-3 text-sm">
              <div className="font-medium text-[var(--tg-theme-text-color,#000000)]">
                {statusTone.label}
              </div>
              <div className="text-[var(--tg-theme-hint-color,#999999)]">
                {Math.round(progressValue)}% периода
              </div>
            </div>

            <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-[rgba(148,163,184,0.18)]">
              <div
                className="h-full rounded-full transition-[width]"
                style={{
                  width: `${progressValue}%`,
                  backgroundColor: statusTone.accent,
                }}
              />
            </div>

            <div className="mt-2 flex items-center justify-between gap-3 text-xs text-[var(--tg-theme-hint-color,#999999)]">
              <span>Запас периода</span>
              <span>
                {daysLeft} из {totalDays} дн.
              </span>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <button
              onClick={onOpenAccess}
              disabled={!configReady}
              className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Получить конфиг
              <ExternalLink className="h-4 w-4" />
            </button>
            <button
              onClick={onRenew}
              className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90"
            >
              Продлить подписку
              <Sparkles className="h-4 w-4" />
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3 px-4 pb-4">
          <div className="rounded-[20px] bg-[var(--tg-theme-bg-color,#ffffff)] p-4 shadow-[inset_0_0_0_1px_rgba(15,23,42,0.06)]">
            <div className="text-sm text-[var(--tg-theme-text-color,#000000)]">
              Сначала активируйте пробный период или купите тариф. После этого появится ссылка на
              конфиг.
            </div>
          </div>

          {subscription.hasTrial && !subscription.hasUsedTrial ? (
            <button
              onClick={onActivateTrial}
              className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90"
            >
              Активировать пробный период
              <Sparkles className="h-4 w-4" />
            </button>
          ) : null}

          <button
            onClick={onBuy}
            className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90"
          >
            Купить подписку
            <ExternalLink className="h-4 w-4" />
          </button>
        </div>
      )}
    </section>
  );
}
