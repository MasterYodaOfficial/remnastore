import React from 'react';
import { Shield, Clock } from 'lucide-react';
import { Progress } from './ui/progress';

interface SubscriptionCardProps {
  subscription: {
    isActive: boolean;
    daysLeft?: number;
    totalDays?: number;
    hasTrial: boolean;
    hasUsedTrial: boolean;
  };
  onActivateTrial: () => void;
  onRenew: () => void;
  onBuy: () => void;
}

export function SubscriptionCard({ 
  subscription, 
  onActivateTrial, 
  onRenew, 
  onBuy 
}: SubscriptionCardProps) {
  const progressValue = subscription.isActive && subscription.daysLeft && subscription.totalDays
    ? (subscription.daysLeft / subscription.totalDays) * 100
    : 0;

  return (
    <div className="bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] rounded-2xl p-4 m-4">
      <div className="flex items-center gap-3 mb-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--tg-theme-button-color,#3390ec)]">
          <Shield className="h-6 w-6 text-[var(--tg-theme-button-text-color,#ffffff)]" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-[var(--tg-theme-text-color,#000000)]">
            VPN Подписка
          </h2>
          <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
            {subscription.isActive ? 'Активна' : 'Не активна'}
          </p>
        </div>
      </div>

      {subscription.isActive && subscription.daysLeft !== undefined ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-[var(--tg-theme-hint-color,#999999)]" />
              <span className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
                Осталось дней
              </span>
            </div>
            <span className="text-lg font-bold text-[var(--tg-theme-button-color,#3390ec)]">
              {subscription.daysLeft}
            </span>
          </div>
          
          <Progress value={progressValue} className="h-2" />
          
          <button
            onClick={onRenew}
            className="w-full py-3 bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] rounded-xl font-medium hover:opacity-90 transition-opacity"
          >
            Продлить подписку
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {subscription.hasTrial && !subscription.hasUsedTrial && (
            <button
              onClick={onActivateTrial}
              className="w-full rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--app-surface-color,#dbe4f2)] py-3 font-medium text-[var(--tg-theme-text-color,#000000)] transition-colors hover:opacity-90"
            >
              Активировать пробный период (7 дней)
            </button>
          )}
          
          <button
            onClick={onBuy}
            className="w-full py-3 bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] rounded-xl font-medium hover:opacity-90 transition-opacity"
          >
            Купить подписку
          </button>
        </div>
      )}
    </div>
  );
}
