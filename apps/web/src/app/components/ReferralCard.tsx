import React from 'react';
import { Users, Copy, Check, DollarSign } from 'lucide-react';

interface ReferralCardProps {
  referralCode: string;
  referralsCount: number;
  earnings: number;
  onCopy: () => void;
  onWithdraw: () => void;
  copied: boolean;
}

export function ReferralCard({ 
  referralCode, 
  referralsCount, 
  earnings,
  onCopy, 
  onWithdraw,
  copied 
}: ReferralCardProps) {
  return (
    <div className="rounded-2xl p-4 m-4"
         style={{
           background: "var(--referral-bg)",
           border: "1px solid var(--referral-border)"
         }}>
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-full bg-gradient-to-r from-purple-500 to-pink-500 flex items-center justify-center">
          <Users className="w-6 h-6 text-white" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-[var(--tg-theme-text-color,#000000)]">
            Реферальная программа
          </h2>
          <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
            Приглашайте друзей и зарабатывайте
          </p>
        </div>
      </div>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl p-3" style={{background:"var(--referral-tile)"}}>
            <div className="text-xs text-[var(--tg-theme-hint-color,#999999)] mb-1">
              Приглашено
            </div>
            <div className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)]">
              {referralsCount}
            </div>
          </div>
          <div className="rounded-xl p-3" style={{background:"var(--referral-tile)"}}>
            <div className="text-xs text-[var(--tg-theme-hint-color,#999999)] mb-1">
              Заработано
            </div>
            <div className="text-2xl font-bold text-[var(--tg-theme-button-color,#3390ec)]">
              {earnings} ₽
            </div>
          </div>
        </div>

        <div className="rounded-xl p-3" style={{background:"var(--referral-tile)"}}>
          <div className="text-xs text-[var(--tg-theme-hint-color,#999999)] mb-2">
            Ваша реферальная ссылка
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-sm font-mono rounded-lg px-3 py-2 text-[var(--tg-theme-text-color,#000000)] overflow-x-auto"
                  style={{background:"var(--referral-code-bg)"}}>
              {referralCode}
            </code>
            <button
              onClick={onCopy}
              className="p-2 bg-[var(--tg-theme-button-color,#3390ec)] text-white rounded-lg hover:opacity-90 transition-opacity"
            >
              {copied ? <Check className="w-5 h-5" /> : <Copy className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {earnings > 0 && (
          <button
            onClick={onWithdraw}
            className="w-full py-3 bg-gradient-to-r from-green-500 to-emerald-500 text-white rounded-xl font-medium hover:opacity-90 transition-opacity flex items-center justify-center gap-2"
          >
            <DollarSign className="w-5 h-5" />
            Вывести средства
          </button>
        )}
      </div>
    </div>
  );
}
