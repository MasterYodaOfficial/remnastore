import React from 'react';
import { User, Wallet } from 'lucide-react';

interface HeaderProps {
  user: {
    name: string;
    avatar?: string;
  };
  balance: number;
  onTopUp: () => void;
}

export function Header({ user, balance, onTopUp }: HeaderProps) {
  return (
    <div className="bg-[var(--tg-theme-bg-color,#ffffff)] border-b border-[var(--tg-theme-hint-color,#e5e5e5)] p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-full bg-[var(--tg-theme-button-color,#3390ec)] flex items-center justify-center text-white font-semibold">
            {user.avatar ? (
              <img src={user.avatar} alt={user.name} className="w-full h-full rounded-full object-cover" />
            ) : (
              <User className="w-6 h-6" />
            )}
          </div>
          <div>
            <div className="text-sm font-medium text-[var(--tg-theme-text-color,#000000)]">
              {user.name}
            </div>
            <div className="flex items-center gap-2 mt-1">
              <Wallet className="w-4 h-4 text-[var(--tg-theme-hint-color,#999999)]" />
              <span className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
                {balance.toFixed(2)} ₽
              </span>
            </div>
          </div>
        </div>
        
        <button
          onClick={onTopUp}
          className="px-4 py-2 bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] rounded-lg font-medium hover:opacity-90 transition-opacity"
        >
          Пополнить
        </button>
      </div>
    </div>
  );
}
