import React from 'react';
import { Bell, CreditCard, Gift, Home, Settings } from 'lucide-react';

interface BottomNavProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  compact?: boolean;
  unreadNotificationsCount?: number;
}

export function BottomNav({
  activeTab,
  onTabChange,
  compact = false,
  unreadNotificationsCount = 0,
}: BottomNavProps) {
  const tabs = [
    { id: 'home', label: 'Главная', icon: Home },
    { id: 'plans', label: 'Тарифы', icon: CreditCard },
    { id: 'notifications', label: 'Уведомления', icon: Bell },
    { id: 'referral', label: 'Рефералы', icon: Gift },
    { id: 'settings', label: 'Настройки', icon: Settings },
  ];

  return (
    <div
      className={`z-20 border-t border-[var(--tg-theme-hint-color,#e5e5e5)] bg-[var(--tg-theme-bg-color,#ffffff)] safe-area-inset-bottom ${
        compact ? 'absolute bottom-0 left-0 right-0' : 'fixed bottom-0 left-0 right-0'
      }`}
    >
      <div className="flex items-center justify-around px-2 py-2">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className="relative flex flex-1 flex-col items-center justify-center gap-1 rounded-xl px-2 py-2 transition-all"
              style={{
                color: isActive 
                  ? 'var(--tg-theme-button-color, #3390ec)' 
                  : 'var(--tg-theme-hint-color, #999999)',
              }}
            >
              <Icon className="w-6 h-6" />
              {tab.id === 'notifications' && unreadNotificationsCount > 0 && (
                <span className="absolute right-4 top-1 inline-flex min-h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[var(--tg-theme-button-color,#3390ec)] px-1 text-[10px] font-semibold text-[var(--tg-theme-button-text-color,#ffffff)]">
                  {unreadNotificationsCount > 99 ? '99+' : unreadNotificationsCount}
                </span>
              )}
              <span className="text-xs font-medium">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
