import React from 'react';
import { CreditCard, ExternalLink, Sparkles, Wallet, X } from 'lucide-react';
import { t } from '../../lib/i18n';

export type PaymentMethodProvider = 'yookassa' | 'telegram_stars' | 'wallet';

export interface PaymentMethodOption {
  provider: PaymentMethodProvider;
  label: string;
  description: string;
  note?: string;
}

interface PaymentMethodSheetProps {
  isOpen: boolean;
  title: string;
  subtitle?: string;
  methods: PaymentMethodOption[];
  isSubmitting?: boolean;
  selectedProvider?: PaymentMethodProvider | null;
  onClose: () => void;
  onSelect: (provider: PaymentMethodProvider) => void;
  promoCode?: string;
  onPromoCodeChange?: (value: string) => void;
  onApplyPromo?: () => void;
  isApplyingPromo?: boolean;
  promoMessage?: {
    tone: 'neutral' | 'success' | 'error';
    text: string;
  } | null;
}

function PaymentMethodIcon({ provider }: { provider: PaymentMethodProvider }) {
  if (provider === 'telegram_stars') {
    return <Sparkles className="h-5 w-5 text-[var(--tg-theme-button-color,#3390ec)]" />;
  }
  if (provider === 'wallet') {
    return <Wallet className="h-5 w-5 text-[var(--app-success-color,#16a34a)]" />;
  }

  return <CreditCard className="h-5 w-5 text-[var(--tg-theme-button-color,#3390ec)]" />;
}

export function PaymentMethodSheet({
  isOpen,
  title,
  subtitle,
  methods,
  isSubmitting = false,
  selectedProvider = null,
  onClose,
  onSelect,
  promoCode,
  onPromoCodeChange,
  onApplyPromo,
  isApplyingPromo = false,
  promoMessage = null,
}: PaymentMethodSheetProps) {
  if (!isOpen) {
    return null;
  }

  const promoMessageClassName =
    promoMessage?.tone === 'success'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
      : promoMessage?.tone === 'error'
        ? 'border-rose-200 bg-rose-50 text-rose-700'
        : 'border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] text-[var(--tg-theme-hint-color,#999999)]';

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-3 sm:items-center sm:p-4">
      <div className="flex max-h-[min(calc(100dvh-1.5rem),calc(100svh-1.5rem))] w-full max-w-lg flex-col overflow-hidden rounded-[28px] bg-[var(--tg-theme-bg-color,#ffffff)] shadow-xl sm:max-h-[min(calc(100dvh-2rem),calc(100svh-2rem))]">
        <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[var(--tg-theme-hint-color,#e5e5e5)] border-opacity-30 bg-[var(--tg-theme-bg-color,#ffffff)] p-5">
          <div className="space-y-1">
            <h2 className="text-xl font-bold text-[var(--tg-theme-text-color,#000000)]">{title}</h2>
            {subtitle ? (
              <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">{subtitle}</p>
            ) : null}
          </div>
          <button
            onClick={onClose}
            disabled={isSubmitting}
            aria-label={t('web.paymentMethods.closeAriaLabel')}
            className="shrink-0 rounded-lg p-2 transition-colors hover:bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)]"
          >
            <X className="h-5 w-5 text-[var(--tg-theme-hint-color,#999999)]" />
          </button>
        </div>

        <div className="min-h-0 space-y-3 overflow-y-auto px-5 py-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))]">
          {onPromoCodeChange && onApplyPromo ? (
            <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] p-4">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[var(--tg-theme-bg-color,#ffffff)]">
                  <Sparkles className="h-5 w-5 text-[var(--tg-theme-button-color,#3390ec)]" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-[var(--tg-theme-text-color,#000000)]">
                    {t('web.paymentMethods.promoTitle')}
                  </div>
                  <p className="mt-1 text-sm text-[var(--tg-theme-hint-color,#999999)]">
                    {t('web.paymentMethods.promoSubtitle')}
                  </p>
                </div>
              </div>

              <div className="mt-4 flex flex-col gap-3 sm:flex-row">
                <input
                  type="text"
                  value={promoCode ?? ''}
                  onChange={(event) => onPromoCodeChange(event.target.value)}
                  placeholder={t('web.paymentMethods.promoPlaceholder')}
                  autoCapitalize="characters"
                  autoCorrect="off"
                  spellCheck={false}
                  className="h-12 flex-1 rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 text-sm font-medium uppercase tracking-[0.08em] text-[var(--tg-theme-text-color,#000000)] outline-none transition focus:border-[var(--tg-theme-button-color,#3390ec)]"
                />
                <button
                  type="button"
                  onClick={onApplyPromo}
                  disabled={isSubmitting || isApplyingPromo || !(promoCode ?? '').trim()}
                  className="inline-flex h-12 items-center justify-center rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] px-4 text-sm font-semibold text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isApplyingPromo
                    ? t('web.paymentMethods.promoChecking')
                    : t('web.paymentMethods.promoApply')}
                </button>
              </div>

              <div className={`mt-3 rounded-2xl border px-4 py-3 text-sm leading-6 ${promoMessageClassName}`}>
                {promoMessage?.text ?? t('web.paymentMethods.promoHint')}
              </div>
            </div>
          ) : null}

          {methods.map((method) => {
            const isSelected = selectedProvider === method.provider;

            return (
              <button
                key={method.provider}
                type="button"
                onClick={() => onSelect(method.provider)}
                disabled={isSubmitting}
                className="flex w-full items-start gap-4 rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] p-4 text-left transition hover:border-[var(--tg-theme-button-color,#3390ec)] hover:bg-[var(--tg-theme-bg-color,#ffffff)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[var(--tg-theme-bg-color,#ffffff)]">
                  <PaymentMethodIcon provider={method.provider} />
                </div>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-[var(--tg-theme-text-color,#000000)]">
                      {method.label}
                    </span>
                    {method.provider === 'yookassa' ? (
                      <ExternalLink className="h-4 w-4 text-[var(--tg-theme-hint-color,#999999)]" />
                    ) : null}
                  </div>
                  <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
                    {method.description}
                  </p>
                  {method.note ? (
                    <p className="text-xs text-[var(--app-muted-contrast,#475569)]">{method.note}</p>
                  ) : null}
                </div>
                {isSelected ? (
                  <span className="text-sm font-medium text-[var(--tg-theme-button-color,#3390ec)]">
                    {t('web.paymentMethods.opening')}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
