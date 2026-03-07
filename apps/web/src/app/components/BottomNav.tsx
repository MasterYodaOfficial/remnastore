import React from 'react';
import { Home, CreditCard, Settings, Gift } from 'lucide-react';

interface BottomNavProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  compact?: boolean;
}

export function BottomNav({ activeTab, onTabChange, compact = false }: BottomNavProps) {
  const tabs = [
    { id: 'home', label: 'Главная', icon: Home },
    { id: 'plans', label: 'Тарифы', icon: CreditCard },
    { id: 'referral', label: 'Рефералы', icon: Gift },
    { id: 'settings', label: 'Настройки', icon: Settings },
  ];

  return (
    <div
      className={`bg-[var(--tg-theme-bg-color,#ffffff)] border-t border-[var(--tg-theme-hint-color,#e5e5e5)] safe-area-inset-bottom ${
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
              className="flex flex-col items-center justify-center gap-1 py-2 px-4 rounded-xl transition-all min-w-[70px]"
              style={{
                color: isActive 
                  ? 'var(--tg-theme-button-color, #3390ec)' 
                  : 'var(--tg-theme-hint-color, #999999)',
              }}
            >
              <Icon className="w-6 h-6" />
              <span className="text-xs font-medium">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
