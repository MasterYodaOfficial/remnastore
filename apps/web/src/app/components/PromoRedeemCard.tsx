import React from 'react';
import { Gift, Sparkles } from 'lucide-react';
import { t } from '../../lib/i18n';

export interface PromoRedeemMessage {
  tone: 'neutral' | 'success' | 'error';
  text: string;
}

interface PromoRedeemCardProps {
  code: string;
  onCodeChange: (value: string) => void;
  onRedeem: () => void;
  isSubmitting?: boolean;
  message?: PromoRedeemMessage | null;
  className?: string;
}

export function PromoRedeemCard({
  code,
  onCodeChange,
  onRedeem,
  isSubmitting = false,
  message = null,
  className = '',
}: PromoRedeemCardProps) {
  const messageClassName =
    message?.tone === 'success'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/70 dark:bg-emerald-950/40 dark:text-emerald-300'
      : message?.tone === 'error'
        ? 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/70 dark:bg-rose-950/40 dark:text-rose-300'
        : 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-300';

  return (
    <div
      className={`rounded-[24px] border border-slate-200 bg-white/80 p-5 dark:border-slate-800 dark:bg-slate-950/80 ${className}`.trim()}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-white dark:border dark:border-slate-800 dark:bg-slate-900">
          <Gift className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">
            {t('web.promoRedeem.title')}
          </div>
          <div className="mt-1 text-sm leading-6 text-slate-500 dark:text-slate-300">
            {t('web.promoRedeem.subtitle')}
          </div>
        </div>
      </div>

      <div className="mt-4 flex min-w-0 flex-col gap-3 sm:flex-row sm:items-stretch">
        <input
          type="text"
          value={code}
          onChange={(event) => onCodeChange(event.target.value)}
          placeholder={t('web.promoRedeem.placeholder')}
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
          className="h-12 min-w-0 flex-1 rounded-2xl border border-slate-200 bg-white px-4 text-sm font-medium uppercase tracking-[0.08em] text-slate-900 outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-50 dark:focus:border-sky-500 dark:focus:ring-sky-500/10"
        />
        <button
          type="button"
          onClick={onRedeem}
          disabled={isSubmitting || !code.trim()}
          className="inline-flex h-12 w-full shrink-0 items-center justify-center gap-2 rounded-2xl bg-slate-950 px-5 text-sm font-semibold text-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-slate-800 sm:w-auto disabled:cursor-not-allowed disabled:opacity-60 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
        >
          <Sparkles className="h-4 w-4 shrink-0" />
          {isSubmitting ? t('web.promoRedeem.submitting') : t('web.promoRedeem.submit')}
        </button>
      </div>

      <div className={`mt-4 rounded-2xl border px-4 py-3 text-sm leading-6 ${messageClassName}`}>
        {message?.text ?? t('web.promoRedeem.hint')}
      </div>
    </div>
  );
}
