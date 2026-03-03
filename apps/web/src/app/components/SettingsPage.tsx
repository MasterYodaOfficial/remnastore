import React from 'react';
import { Moon, Sun, LogOut, Globe, Bell, Shield, HelpCircle } from 'lucide-react';

interface SettingsPageProps {
  theme: 'light' | 'dark';
  onThemeChange: (theme: 'light' | 'dark') => void;
  onLogout: () => void;
}

export function SettingsPage({ theme, onThemeChange, onLogout }: SettingsPageProps) {
  const settingsSections = [
    {
      title: 'Внешний вид',
      items: [
        {
          icon: theme === 'dark' ? Moon : Sun,
          label: 'Тема',
          action: (
            <button
              onClick={() => onThemeChange(theme === 'dark' ? 'light' : 'dark')}
              className="px-4 py-1.5 rounded-lg bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] text-sm font-medium"
            >
              {theme === 'dark' ? 'Темная' : 'Светлая'}
            </button>
          ),
        },
      ],
    },
    {
      title: 'Основное',
      items: [
        {
          icon: Globe,
          label: 'Язык',
          action: <span className="text-sm text-[var(--tg-theme-hint-color,#999999)]">Русский</span>,
        },
        {
          icon: Bell,
          label: 'Уведомления',
          action: (
            <label className="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" className="sr-only peer" defaultChecked />
              <div className="w-11 h-6 bg-gray-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--tg-theme-button-color,#3390ec)]"></div>
            </label>
          ),
        },
      ],
    },
    {
      title: 'Поддержка',
      items: [
        {
          icon: Shield,
          label: 'Политика конфиденциальности',
          action: <span className="text-[var(--tg-theme-hint-color,#999999)]">›</span>,
        },
        {
          icon: HelpCircle,
          label: 'Помощь и поддержка',
          action: <span className="text-[var(--tg-theme-hint-color,#999999)]">›</span>,
        },
      ],
    },
  ];

  return (
    <div className="pb-20 px-4 pt-4 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)]">
          Настройки
        </h1>
      </div>
      <div className="flex items-center gap-2 px-2">
        <span className="text-sm text-[var(--tg-theme-hint-color,#999999)]">Тема</span>
        <button
          onClick={() => onThemeChange(theme === 'dark' ? 'light' : 'dark')}
          className="px-3 py-1.5 rounded-lg border border-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-color,#3390ec)] text-sm font-medium"
        >
          {theme === 'dark' ? 'Светлая' : 'Тёмная'}
        </button>
      </div>

      {settingsSections.map((section, sectionIndex) => (
        <div key={sectionIndex} className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--tg-theme-hint-color,#999999)] px-2">
            {section.title}
          </h2>
          <div className="bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] rounded-2xl overflow-hidden">
            {section.items.map((item, itemIndex) => {
              const Icon = item.icon;
              return (
                <div
                  key={itemIndex}
                  className={`flex items-center justify-between p-4 ${
                    itemIndex !== section.items.length - 1
                      ? 'border-b border-[var(--tg-theme-hint-color,#e5e5e5)] border-opacity-30'
                      : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon className="w-5 h-5 text-[var(--tg-theme-button-color,#3390ec)]" />
                    <span className="text-[var(--tg-theme-text-color,#000000)] font-medium">
                      {item.label}
                    </span>
                  </div>
                  {item.action}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <button
        onClick={onLogout}
        className="w-full flex items-center justify-center gap-2 py-3 bg-red-500 text-white rounded-xl font-medium hover:bg-red-600 transition-colors"
      >
        <LogOut className="w-5 h-5" />
        Выйти из аккаунта
      </button>
    </div>
  );
}
