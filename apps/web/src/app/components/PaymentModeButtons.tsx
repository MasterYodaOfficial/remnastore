import React from 'react';
import { Check, ChevronRight, CreditCard, QrCode } from 'lucide-react';

export type PaymentMode = 'all' | 'sbp';

interface PaymentModeButtonsProps {
  activeMode?: PaymentMode;
  onSelect: (mode: PaymentMode) => void;
}

export function PaymentModeButtons({ activeMode, onSelect }: PaymentModeButtonsProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {([
        { mode: 'all', label: 'Картой и другими способами', description: 'Доступные способы в ЮKassa', Icon: CreditCard },
        { mode: 'sbp', label: 'СБП', description: 'Через приложение вашего банка', Icon: QrCode },
      ] as const).map(({ mode, label, description, Icon }) => {
        const selected = activeMode === mode;
        return (
          <button
            key={mode}
            type="button"
            aria-label={label}
            aria-pressed={activeMode === undefined ? undefined : selected}
            onClick={() => onSelect(mode)}
            className={`flex min-w-0 items-center gap-3 rounded-2xl border p-4 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--tg-theme-button-color,#3390ec)] ${selected
              ? 'border-[var(--tg-theme-button-color,#3390ec)] bg-[var(--tg-theme-secondary-bg-color,#f1f5f9)]'
              : 'border-[var(--app-border-color,rgba(15,23,42,0.16))] bg-[var(--tg-theme-bg-color,#ffffff)] hover:bg-[var(--tg-theme-secondary-bg-color,#f1f5f9)]'}`}
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)]">
              <Icon className="h-5 w-5" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold text-[var(--tg-theme-text-color,#0f172a)]">{label}</span>
              <span className="mt-1 block text-xs leading-5 text-[var(--app-muted-contrast,#475569)]">{description}</span>
            </span>
            {selected
              ? <Check className="h-4 w-4 shrink-0 text-[var(--tg-theme-button-color,#3390ec)]" aria-hidden="true" />
              : <ChevronRight className="h-4 w-4 shrink-0 text-[var(--tg-theme-hint-color,#64748b)]" aria-hidden="true" />}
          </button>
        );
      })}
    </div>
  );
}
