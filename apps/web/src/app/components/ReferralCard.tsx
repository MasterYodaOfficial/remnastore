import React from 'react';
import { Users, Copy, Check, DollarSign } from 'lucide-react';
import { formatRubles } from '../../lib/currency';

interface ReferralCardProps {
  referralCode: string;
  referralsCount: number;
  referralEarnings: number;
  onCopy: () => void;
  onWithdraw: () => void;
  copied: boolean;
}

export function ReferralCard({ 
  referralCode, 
  referralsCount, 
  referralEarnings,
  onCopy, 
  onWithdraw,
  copied 
}: ReferralCardProps) {
  return (
    <div
      className="m-4 rounded-2xl p-4"
      style={{
        background: 'var(--referral-bg)',
        border: '1px solid var(--referral-border)',
      }}
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)]">
          <Users className="w-6 h-6" />
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
              {formatRubles(referralEarnings)} ₽
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
              className="rounded-lg bg-[var(--tg-theme-button-color,#3390ec)] p-2 text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90"
            >
              {copied ? <Check className="w-5 h-5" /> : <Copy className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {referralEarnings > 0 && (
          <button
            onClick={onWithdraw}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--app-success-bg,#16a34a)] py-3 font-medium text-[var(--app-success-text,#ffffff)] transition-colors hover:bg-[var(--app-success-bg-hover,#15803d)]"
          >
            <DollarSign className="w-5 h-5" />
            Вывести средства
          </button>
        )}
      </div>
    </div>
  );
}
