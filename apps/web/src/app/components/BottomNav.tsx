import React from 'react';
import { CreditCard, Gift, Home, Settings } from 'lucide-react';
import { t } from '../../lib/i18n';

interface BottomNavProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  compact?: boolean;
}

export function BottomNav({
  activeTab,
  onTabChange,
  compact = false,
}: BottomNavProps) {
  const tabs = [
    { id: 'home', label: t('web.bottomNav.home'), icon: Home },
    { id: 'plans', label: t('web.bottomNav.plans'), icon: CreditCard },
    { id: 'referral', label: t('web.bottomNav.referral'), icon: Gift },
    { id: 'settings', label: t('web.bottomNav.settings'), icon: Settings },
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
              <span className="text-xs font-medium">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
