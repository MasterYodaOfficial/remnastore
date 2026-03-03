import React, { useState } from 'react';
import { X } from 'lucide-react';

interface TopUpModalProps {
  isOpen: boolean;
  onClose: () => void;
  onTopUp: (amount: number) => void;
}

export function TopUpModal({ isOpen, onClose, onTopUp }: TopUpModalProps) {
  const [customAmount, setCustomAmount] = useState('');
  const presetAmounts = [500, 1000, 2000, 5000];

  if (!isOpen) return null;

  const handleTopUp = (amount: number) => {
    onTopUp(amount);
    onClose();
  };

  const handleCustomTopUp = () => {
    const amount = parseFloat(customAmount);
    if (amount && amount > 0) {
      handleTopUp(amount);
      setCustomAmount('');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div className="w-full max-w-md bg-[var(--tg-theme-bg-color,#ffffff)] rounded-2xl shadow-xl">
        <div className="flex items-center justify-between p-4 border-b border-[var(--tg-theme-hint-color,#e5e5e5)] border-opacity-30">
          <h2 className="text-xl font-bold text-[var(--tg-theme-text-color,#000000)]">
            Пополнение баланса
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-[var(--tg-theme-hint-color,#999999)]" />
          </button>
        </div>

        <div className="p-4 space-y-4">
          <div>
            <p className="text-sm text-[var(--tg-theme-hint-color,#999999)] mb-3">
              Выберите сумму пополнения
            </p>
            <div className="grid grid-cols-2 gap-3">
              {presetAmounts.map((amount) => (
                <button
                  key={amount}
                  onClick={() => handleTopUp(amount)}
                  className="py-3 bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] hover:bg-[var(--tg-theme-button-color,#3390ec)] hover:text-white rounded-xl font-semibold transition-colors text-[var(--tg-theme-text-color,#000000)]"
                >
                  {amount} ₽
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="text-sm text-[var(--tg-theme-hint-color,#999999)] mb-2">
              Или введите свою сумму
            </p>
            <div className="flex gap-2">
              <input
                type="number"
                value={customAmount}
                onChange={(e) => setCustomAmount(e.target.value)}
                placeholder="Введите сумму"
                className="flex-1 px-4 py-3 bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] rounded-xl text-[var(--tg-theme-text-color,#000000)] placeholder:text-[var(--tg-theme-hint-color,#999999)] focus:outline-none focus:ring-2 focus:ring-[var(--tg-theme-button-color,#3390ec)]"
                min="1"
              />
              <button
                onClick={handleCustomTopUp}
                disabled={!customAmount || parseFloat(customAmount) <= 0}
                className="px-6 py-3 bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] rounded-xl font-medium hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
              >
                ОК
              </button>
            </div>
          </div>

          <p className="text-xs text-[var(--tg-theme-hint-color,#999999)] text-center">
            Это демо-версия. Оплата не требуется.
          </p>
        </div>
      </div>
    </div>
  );
}
