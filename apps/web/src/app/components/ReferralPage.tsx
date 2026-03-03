import React from 'react';
import { Users, TrendingUp, DollarSign } from 'lucide-react';

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
  onWithdraw: () => void;
}

export function ReferralPage({
  referrals,
  totalEarnings,
  availableForWithdraw,
  onWithdraw,
}: ReferralPageProps) {
  return (
    <div className="pb-20 px-4 pt-4 space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)] mb-2">
          Реферальная программа
        </h1>
        <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
          Зарабатывайте 20% с каждой покупки ваших рефералов
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="bg-gradient-to-br from-purple-500 to-blue-500 rounded-2xl p-4 text-white">
          <TrendingUp className="w-6 h-6 mb-2 opacity-80" />
          <div className="text-xs opacity-80 mb-1">Всего заработано</div>
          <div className="text-2xl font-bold">{totalEarnings} ₽</div>
        </div>
        
        <div className="bg-gradient-to-br from-green-500 to-emerald-500 rounded-2xl p-4 text-white">
          <DollarSign className="w-6 h-6 mb-2 opacity-80" />
          <div className="text-xs opacity-80 mb-1">Доступно</div>
          <div className="text-2xl font-bold">{availableForWithdraw} ₽</div>
        </div>
      </div>

      {availableForWithdraw > 0 && (
        <button
          onClick={onWithdraw}
          className="w-full py-3 bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] rounded-xl font-medium hover:opacity-90 transition-opacity"
        >
          Вывести на баланс {availableForWithdraw} ₽
        </button>
      )}

      <div className="space-y-3">
        <h2 className="text-lg font-semibold text-[var(--tg-theme-text-color,#000000)]">
          Ваши рефералы ({referrals.length})
        </h2>
        
        {referrals.length > 0 ? (
          <div className="space-y-2">
            {referrals.map((referral) => (
              <div
                key={referral.id}
                className="bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] rounded-xl p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-[var(--tg-theme-button-color,#3390ec)] flex items-center justify-center text-white font-semibold">
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
                    <div className="font-semibold text-green-600">
                      +{referral.earned} ₽
                    </div>
                    <div
                      className={`text-xs ${
                        referral.status === 'active'
                          ? 'text-green-600'
                          : 'text-yellow-600'
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
