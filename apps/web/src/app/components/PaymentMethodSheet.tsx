import React from 'react';
import { CreditCard, ExternalLink, Sparkles, Wallet, X } from 'lucide-react';

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
}: PaymentMethodSheetProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-4 sm:items-center">
      <div className="w-full max-w-lg rounded-[28px] bg-[var(--tg-theme-bg-color,#ffffff)] shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-[var(--tg-theme-hint-color,#e5e5e5)] border-opacity-30 p-5">
          <div className="space-y-1">
            <h2 className="text-xl font-bold text-[var(--tg-theme-text-color,#000000)]">{title}</h2>
            {subtitle ? (
              <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">{subtitle}</p>
            ) : null}
          </div>
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="rounded-lg p-2 transition-colors hover:bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)]"
          >
            <X className="h-5 w-5 text-[var(--tg-theme-hint-color,#999999)]" />
          </button>
        </div>

        <div className="space-y-3 p-5">
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
                    Открываем...
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
