import React, { useState } from 'react';
import { LoaderCircle, Wallet, X } from 'lucide-react';
import { formatRubles } from '../../lib/currency';

interface TopUpModalProps {
  isOpen: boolean;
  onClose: () => void;
  onTopUp: (amount: number) => Promise<void> | void;
  isSubmitting?: boolean;
}

export function TopUpModal({ isOpen, onClose, onTopUp, isSubmitting = false }: TopUpModalProps) {
  const [customAmount, setCustomAmount] = useState('');
  const presetAmounts = [500, 1000, 2000, 5000];
  const parsedCustomAmount = Number.parseInt(customAmount, 10);

  if (!isOpen) return null;

  const handleTopUp = async (amount: number) => {
    await onTopUp(amount);
  };

  const handleCustomTopUp = async () => {
    const amount = parseInt(customAmount, 10);
    if (amount && amount > 0) {
      await handleTopUp(amount);
      setCustomAmount('');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/55 p-4 sm:items-center">
      <div className="w-full max-w-md overflow-hidden rounded-[28px] bg-[var(--tg-theme-bg-color,#ffffff)] shadow-[0_24px_64px_rgba(15,23,42,0.24)]">
        <div className="flex items-start justify-between gap-4 border-b border-[var(--tg-theme-hint-color,#e5e5e5)] border-opacity-30 px-5 py-4">
          <div className="space-y-1">
            <div className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)]">
              <Wallet className="h-5 w-5 text-[var(--tg-theme-button-color,#3390ec)]" />
            </div>
            <h2 className="text-xl font-bold text-[var(--tg-theme-text-color,#000000)]">
              Пополнение баланса
            </h2>
            <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
              Выбери сумму и откроем YooKassa для оплаты.
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="rounded-lg p-2 transition-colors hover:bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)]"
          >
            <X className="w-5 h-5 text-[var(--tg-theme-hint-color,#999999)]" />
          </button>
        </div>

        <div className="space-y-5 px-5 py-5">
          <div>
            <p className="mb-3 text-sm text-[var(--tg-theme-hint-color,#999999)]">
              Выберите сумму пополнения
            </p>
            <div className="grid grid-cols-2 gap-3">
              {presetAmounts.map((amount) => (
                <button
                  key={amount}
                  onClick={() => void handleTopUp(amount)}
                  disabled={isSubmitting}
                  className="rounded-2xl border border-transparent bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-3 text-left transition hover:border-[var(--tg-theme-button-color,#3390ec)] hover:bg-[var(--tg-theme-bg-color,#ffffff)] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <span className="block text-lg font-semibold text-[var(--tg-theme-text-color,#000000)]">
                    {formatRubles(amount)} ₽
                  </span>
                  <span className="block text-xs text-[var(--tg-theme-hint-color,#999999)]">
                    Быстрый выбор
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-sm text-[var(--tg-theme-hint-color,#999999)]">
              Или введите свою сумму
            </p>
            <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_144px]">
              <label className="flex items-center gap-3 rounded-2xl bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-3 focus-within:ring-2 focus-within:ring-[var(--tg-theme-button-color,#3390ec)]">
                <span className="text-lg font-semibold text-[var(--tg-theme-text-color,#000000)]">₽</span>
                <input
                  type="number"
                  value={customAmount}
                  onChange={(e) => setCustomAmount(e.target.value)}
                  placeholder="Введите сумму"
                  disabled={isSubmitting}
                  className="w-full bg-transparent text-[var(--tg-theme-text-color,#000000)] placeholder:text-[var(--tg-theme-hint-color,#999999)] focus:outline-none"
                  min="1"
                  step="1"
                />
              </label>
              <button
                onClick={() => void handleCustomTopUp()}
                disabled={
                  isSubmitting ||
                  !customAmount ||
                  Number.isNaN(parsedCustomAmount) ||
                  parsedCustomAmount <= 0
                }
                className="inline-flex min-h-[52px] min-w-[144px] items-center justify-center gap-2 rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] px-5 py-3 font-medium text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSubmitting ? (
                  <>
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                    <span className="whitespace-nowrap">Создаем...</span>
                  </>
                ) : (
                  <span className="whitespace-nowrap">Продолжить</span>
                )}
              </button>
            </div>
            <p className="mt-2 text-xs text-[var(--tg-theme-hint-color,#999999)]">
              Минимальная сумма пополнения: 1 ₽
            </p>
          </div>

          <div className="rounded-2xl bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-3 text-xs text-[var(--tg-theme-hint-color,#999999)]">
            После подтверждения откроем YooKassa. В Telegram Mini App переход откроется во внешнем браузере.
          </div>
        </div>
      </div>
    </div>
  );
}
