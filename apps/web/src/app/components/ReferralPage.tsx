import React from 'react';
import { Users, TrendingUp, DollarSign } from 'lucide-react';
import { formatRubles } from '../../lib/currency';

interface Referral {
  id: string;
  name: string;
  date: string;
  earned: number;
  status: 'active' | 'pending';
}

interface ReferralPageProps {
  referrals: Referral[];
  totalEarnings: number;
  availableForWithdraw: number;
  rewardRate: number;
  isLoading?: boolean;
  onWithdraw: () => void;
}

export function ReferralPage({
  referrals,
  totalEarnings,
  availableForWithdraw,
  rewardRate,
  isLoading = false,
  onWithdraw,
}: ReferralPageProps) {
  return (
    <div className="pb-20 px-4 pt-4 space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)] mb-2">
          Реферальная программа
        </h1>
        <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
          Зарабатывайте {rewardRate}% с первой успешной покупки ваших рефералов
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--app-surface-color,#dbe4f2)] p-4">
          <TrendingUp className="mb-2 h-6 w-6 text-[var(--tg-theme-button-color,#3390ec)]" />
          <div className="mb-1 text-xs text-[var(--tg-theme-hint-color,#999999)]">Всего заработано</div>
          <div className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)]">
            {formatRubles(totalEarnings)} ₽
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--app-surface-color,#dbe4f2)] p-4">
          <DollarSign className="mb-2 h-6 w-6 text-[var(--app-success-color,#16a34a)]" />
          <div className="mb-1 text-xs text-[var(--tg-theme-hint-color,#999999)]">Доступно</div>
          <div className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)]">
            {formatRubles(availableForWithdraw)} ₽
          </div>
        </div>
      </div>

      {availableForWithdraw > 0 && (
        <button
          onClick={onWithdraw}
          className="w-full py-3 bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] rounded-xl font-medium hover:opacity-90 transition-opacity"
        >
          Вывести на баланс {formatRubles(availableForWithdraw)} ₽
        </button>
      )}

      <div className="space-y-3">
        <h2 className="text-lg font-semibold text-[var(--tg-theme-text-color,#000000)]">
          Ваши рефералы ({referrals.length})
        </h2>

        {isLoading ? (
          <div className="rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] p-4 text-sm text-[var(--tg-theme-hint-color,#999999)]">
            Загружаем реферальную статистику...
          </div>
        ) : referrals.length > 0 ? (
          <div className="space-y-2">
            {referrals.map((referral) => (
              <div
                key={referral.id}
                className="rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--tg-theme-button-color,#3390ec)] font-semibold text-[var(--tg-theme-button-text-color,#ffffff)]">
                      {referral.name.charAt(0)}
                    </div>
                    <div>
                      <div className="font-medium text-[var(--tg-theme-text-color,#000000)]">
                        {referral.name}
                      </div>
                      <div className="text-xs text-[var(--tg-theme-hint-color,#999999)]">
                        {referral.date}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold text-[var(--app-success-color,#16a34a)]">
                      +{formatRubles(referral.earned)} ₽
                    </div>
                    <div
                      className={`text-xs ${
                        referral.status === 'active'
                          ? 'text-[var(--app-success-color,#16a34a)]'
                          : 'text-[var(--app-warning-color,#ca8a04)]'
                      }`}
                    >
                      {referral.status === 'active' ? 'Активен' : 'Ожидание'}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <Users className="w-16 h-16 mx-auto text-[var(--tg-theme-hint-color,#999999)] opacity-50 mb-4" />
            <p className="text-[var(--tg-theme-hint-color,#999999)]">
              У вас пока нет рефералов
            </p>
            <p className="text-sm text-[var(--tg-theme-hint-color,#999999)] mt-2">
              Поделитесь своей ссылкой, чтобы начать зарабатывать
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
