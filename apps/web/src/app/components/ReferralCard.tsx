import React from 'react';
import { Users, Copy, Check, DollarSign, Send } from 'lucide-react';
import { formatRubles } from '../../lib/currency';
import { t } from '../../lib/i18n';

interface ReferralCardProps {
  referralCode: string;
  referralsCount: number;
  referralEarnings: number;
  availableForWithdraw: number;
  onCopy: () => void;
  onShareTelegram: () => void;
  onWithdraw: () => void;
  copied: boolean;
}

export function ReferralCard({
  referralCode,
  referralsCount,
  referralEarnings,
  availableForWithdraw,
  onCopy,
  onShareTelegram,
  onWithdraw,
  copied,
}: ReferralCardProps) {
  return (
    <div
      className="w-full rounded-2xl p-4"
      style={{
        background: 'var(--referral-bg)',
        border: '1px solid var(--referral-border)',
      }}
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)]">
          <Users className="h-5 w-5 shrink-0" />
        </div>
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-[var(--tg-theme-text-color,#000000)]">
            {t('web.referralCard.title')}
          </h2>
          <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
            {t('web.referralCard.subtitle')}
          </p>
        </div>
      </div>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl p-3" style={{background:"var(--referral-tile)"}}>
            <div className="text-xs text-[var(--tg-theme-hint-color,#999999)] mb-1">
              {t('web.referralCard.invitedLabel')}
            </div>
            <div className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)]">
              {referralsCount}
            </div>
          </div>
          <div className="rounded-xl p-3" style={{background:"var(--referral-tile)"}}>
            <div className="text-xs text-[var(--tg-theme-hint-color,#999999)] mb-1">
              {t('web.referralCard.earnedLabel')}
            </div>
            <div className="text-2xl font-bold text-[var(--tg-theme-button-color,#3390ec)]">
              {formatRubles(referralEarnings)} ₽
            </div>
          </div>
        </div>

        <div className="rounded-xl p-3" style={{ background: "var(--referral-tile)" }}>
          <div className="mb-2 text-xs text-[var(--tg-theme-hint-color,#999999)]">
            {t('web.referralCard.codeLabel')}
          </div>
          <div
            className="rounded-lg px-3 py-2 text-sm font-mono text-[var(--tg-theme-text-color,#000000)]"
            style={{ background: "var(--referral-code-bg)" }}
          >
            <code className="block overflow-x-auto">
              {referralCode}
            </code>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <button
              onClick={onCopy}
              className="flex items-center justify-center gap-2 rounded-lg bg-[var(--tg-theme-button-color,#3390ec)] px-3 py-2 text-sm font-medium text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90"
            >
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              {copied ? t('web.referralCard.copied') : t('web.referralCard.copy')}
            </button>
            <button
              onClick={onShareTelegram}
              className="flex items-center justify-center gap-2 rounded-lg border border-[var(--tg-theme-button-color,#3390ec)] bg-transparent px-3 py-2 text-sm font-medium text-[var(--tg-theme-button-color,#3390ec)] transition-opacity hover:opacity-90"
            >
              <Send className="h-4 w-4" />
              {t('web.referralCard.shareTelegram')}
            </button>
          </div>
        </div>

        <div className="rounded-xl p-3 text-sm" style={{ background: "var(--referral-tile)" }}>
          <div className="font-semibold text-[var(--tg-theme-text-color,#000000)]">
            {t('web.referralCard.rewardTitle')}
          </div>
          <p className="mt-1 leading-6 text-[var(--tg-theme-hint-color,#999999)]">
            {t('web.referralCard.rewardBody')}
          </p>
          <p className="mt-3 text-xs text-[var(--tg-theme-hint-color,#999999)]">
            {availableForWithdraw > 0
              ? t('web.referralCard.withdrawHintAvailable', {
                  amount: formatRubles(availableForWithdraw),
                })
              : t('web.referralCard.withdrawHintEmpty')}
          </p>
        </div>

        {availableForWithdraw > 0 && (
          <button
            onClick={onWithdraw}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--app-success-bg,#16a34a)] py-3 font-medium text-[var(--app-success-text,#ffffff)] transition-colors hover:bg-[var(--app-success-bg-hover,#15803d)]"
          >
            <DollarSign className="w-5 h-5" />
            {t('web.referralCard.withdrawAction', {
              amount: formatRubles(availableForWithdraw),
            })}
          </button>
        )}
      </div>
    </div>
  );
}
