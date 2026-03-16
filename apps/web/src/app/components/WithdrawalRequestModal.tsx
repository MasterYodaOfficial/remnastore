import React, { useEffect, useMemo, useState } from 'react';
import { CreditCard, LoaderCircle, Wallet, X } from 'lucide-react';
import { formatRubles } from '../../lib/currency';

interface WithdrawalRequestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (payload: { amount: number; cardNumber: string; comment: string }) => Promise<void> | void;
  isSubmitting?: boolean;
  availableForWithdraw: number;
  minimumAmount: number;
}

function normalizeCardDigits(value: string): string {
  return value.replace(/\D+/g, '').slice(0, 19);
}

function formatCardNumber(value: string): string {
  const digits = normalizeCardDigits(value);
  return digits.replace(/(\d{4})(?=\d)/g, '$1 ').trim();
}

function isLuhnValid(value: string): boolean {
  const digits = normalizeCardDigits(value);
  if (digits.length < 16) {
    return false;
  }

  let checksum = 0;
  const reversedDigits = digits.split('').reverse();
  for (let index = 0; index < reversedDigits.length; index += 1) {
    let digit = Number.parseInt(reversedDigits[index], 10);
    if (index % 2 === 1) {
      digit *= 2;
      if (digit > 9) {
        digit -= 9;
      }
    }
    checksum += digit;
  }

  return checksum % 10 === 0;
}

export function WithdrawalRequestModal({
  isOpen,
  onClose,
  onSubmit,
  isSubmitting = false,
  availableForWithdraw,
  minimumAmount,
}: WithdrawalRequestModalProps) {
  const [amountInput, setAmountInput] = useState('');
  const [cardInput, setCardInput] = useState('');
  const [commentInput, setCommentInput] = useState('');

  useEffect(() => {
    if (!isOpen) {
      setAmountInput('');
      setCardInput('');
      setCommentInput('');
    }
  }, [isOpen]);

  const parsedAmount = Number.parseInt(amountInput, 10);
  const normalizedCardDigits = useMemo(() => normalizeCardDigits(cardInput), [cardInput]);
  const hasEnoughDigits = normalizedCardDigits.length >= 16;
  const isCardValid = hasEnoughDigits && isLuhnValid(normalizedCardDigits);
  const isAmountValid =
    Number.isFinite(parsedAmount) &&
    parsedAmount >= minimumAmount &&
    parsedAmount <= availableForWithdraw;
  const canSubmit = isAmountValid && isCardValid && !isSubmitting;

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/55 p-3 sm:p-4 sm:items-center">
      <div className="flex max-h-[min(calc(100dvh-1.5rem),calc(100svh-1.5rem))] w-full max-w-lg flex-col overflow-hidden rounded-[28px] bg-[var(--tg-theme-bg-color,#ffffff)] shadow-[0_24px_64px_rgba(15,23,42,0.24)] sm:max-h-[min(calc(100dvh-2rem),calc(100svh-2rem))]">
        <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[var(--tg-theme-hint-color,#e5e5e5)] border-opacity-30 bg-[var(--tg-theme-bg-color,#ffffff)] px-5 py-4">
          <div className="space-y-1">
            <div className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)]">
              <Wallet className="h-5 w-5 text-[var(--tg-theme-button-color,#3390ec)]" />
            </div>
            <h2 className="text-xl font-bold text-[var(--tg-theme-text-color,#000000)]">
              Заявка на вывод
            </h2>
            <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
              Деньги будут зарезервированы, а заявка уйдет администратору на проверку.
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Закрыть окно вывода"
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] transition-colors hover:bg-[var(--tg-theme-hint-color,#e5e5e5)]/30"
          >
            <X className="h-5 w-5 text-[var(--tg-theme-text-color,#000000)]" />
          </button>
        </div>

        <div className="min-h-0 overflow-y-auto px-5 py-5">
          <div className="space-y-5 pb-1">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-3">
                <div className="text-xs uppercase tracking-[0.14em] text-[var(--tg-theme-hint-color,#999999)]">
                  Доступно
                </div>
                <div className="mt-2 text-2xl font-semibold text-[var(--tg-theme-text-color,#000000)]">
                  {formatRubles(availableForWithdraw)} ₽
                </div>
              </div>
              <div className="rounded-2xl bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-3">
                <div className="text-xs uppercase tracking-[0.14em] text-[var(--tg-theme-hint-color,#999999)]">
                  Минимум
                </div>
                <div className="mt-2 text-2xl font-semibold text-[var(--tg-theme-text-color,#000000)]">
                  {formatRubles(minimumAmount)} ₽
                </div>
              </div>
            </div>

            <div className="grid gap-4">
              <label className="grid gap-2">
                <span className="text-sm font-medium text-[var(--tg-theme-text-color,#000000)]">
                  Сумма вывода
                </span>
                <input
                  type="number"
                  value={amountInput}
                  onChange={(event) => setAmountInput(event.target.value)}
                  placeholder={`От ${formatRubles(minimumAmount)} ₽`}
                  min={minimumAmount}
                  max={availableForWithdraw}
                  step={1}
                  disabled={isSubmitting}
                  className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-3 text-[var(--tg-theme-text-color,#000000)] outline-none focus:border-[var(--tg-theme-button-color,#3390ec)]"
                />
                {!isAmountValid && amountInput ? (
                  <span className="text-xs text-amber-600 dark:text-amber-300">
                    Укажи сумму от {formatRubles(minimumAmount)} ₽ до {formatRubles(availableForWithdraw)} ₽.
                  </span>
                ) : null}
              </label>

              <label className="grid gap-2">
                <span className="flex items-center gap-2 text-sm font-medium text-[var(--tg-theme-text-color,#000000)]">
                  <CreditCard className="h-4 w-4 text-[var(--tg-theme-button-color,#3390ec)]" />
                  Номер карты
                </span>
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="cc-number"
                  value={cardInput}
                  onChange={(event) => setCardInput(formatCardNumber(event.target.value))}
                  placeholder="0000 0000 0000 0000"
                  disabled={isSubmitting}
                  className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-3 text-[var(--tg-theme-text-color,#000000)] outline-none focus:border-[var(--tg-theme-button-color,#3390ec)]"
                />
                {normalizedCardDigits && !isCardValid ? (
                  <span className="text-xs text-amber-600 dark:text-amber-300">
                    Проверь номер карты. Перед отправкой он проходит проверку контрольной суммы.
                  </span>
                ) : (
                  <span className="text-xs text-[var(--tg-theme-hint-color,#999999)]">
                    Поддерживаются только корректные номера карт. Сырые реквизиты не показываются обратно в приложении.
                  </span>
                )}
              </label>

              <label className="grid gap-2">
                <span className="text-sm font-medium text-[var(--tg-theme-text-color,#000000)]">
                  Комментарий для администратора
                </span>
                <textarea
                  value={commentInput}
                  onChange={(event) => setCommentInput(event.target.value)}
                  placeholder="Например: основная карта для выплат"
                  rows={3}
                  disabled={isSubmitting}
                  className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-3 text-[var(--tg-theme-text-color,#000000)] outline-none focus:border-[var(--tg-theme-button-color,#3390ec)]"
                />
              </label>
            </div>

            <div className="rounded-2xl bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-3 text-xs leading-5 text-[var(--tg-theme-hint-color,#999999)]">
              После отправки заявка появится в статусе «На рассмотрении». Обновления по ней придут через центр уведомлений.
            </div>
          </div>
        </div>

        <div className="sticky bottom-0 border-t border-[var(--tg-theme-hint-color,#e5e5e5)] border-opacity-30 bg-[var(--tg-theme-bg-color,#ffffff)] px-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] pt-4">
          <button
            onClick={() =>
              void onSubmit({
                amount: parsedAmount,
                cardNumber: normalizedCardDigits,
                comment: commentInput,
              })
            }
            disabled={!canSubmit}
            className="inline-flex min-h-[52px] w-full items-center justify-center gap-2 rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] px-5 py-3 font-medium text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <LoaderCircle className="h-4 w-4 animate-spin" />
                Отправляем заявку...
              </>
            ) : (
              'Отправить заявку'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
