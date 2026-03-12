import React from 'react';
import { Bell, User, Wallet } from 'lucide-react';
import { formatRubles } from '../../lib/currency';

interface HeaderProps {
  user: {
    name: string;
    avatar?: string;
  };
  balance: number;
  onTopUp: () => void;
  onOpenNotifications?: () => void;
  unreadNotificationsCount?: number;
}

export function Header({
  user,
  balance,
  onTopUp,
  onOpenNotifications,
  unreadNotificationsCount = 0,
}: HeaderProps) {
  return (
    <div className="border-b border-[var(--tg-theme-hint-color,#e5e5e5)] bg-[var(--tg-theme-bg-color,#ffffff)] p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--tg-theme-button-color,#3390ec)] font-semibold text-[var(--tg-theme-button-text-color,#ffffff)]">
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
                {formatRubles(balance)} ₽
              </span>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          {onOpenNotifications && (
            <button
              onClick={onOpenNotifications}
              className="relative flex h-11 w-11 items-center justify-center rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90"
              aria-label="Открыть уведомления"
            >
              <Bell className="h-5 w-5" />
              {unreadNotificationsCount > 0 && (
                <span className="absolute -right-1 -top-1 inline-flex min-h-[20px] min-w-[20px] items-center justify-center rounded-full bg-[var(--tg-theme-button-color,#3390ec)] px-1 text-[10px] font-semibold text-[var(--tg-theme-button-text-color,#ffffff)]">
                  {unreadNotificationsCount > 99 ? '99+' : unreadNotificationsCount}
                </span>
              )}
            </button>
          )}

          <button
            onClick={onTopUp}
            className="px-4 py-2 bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] rounded-lg font-medium hover:opacity-90 transition-opacity"
          >
            Пополнить
          </button>
        </div>
      </div>
    </div>
  );
}
