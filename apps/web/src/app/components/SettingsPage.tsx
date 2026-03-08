import React from 'react';
import { Moon, Sun, LogOut, Globe, Bell, Shield, HelpCircle, Mail, CheckCircle, XCircle, Link as LinkIcon } from 'lucide-react';
import { ThemeToggle } from './ThemeToggle';

interface SettingsPageProps {
  theme: 'light' | 'dark';
  onThemeChange: (theme: 'light' | 'dark') => void;
  onLogout: () => void;
  showLogout?: boolean;
  user?: {
    email?: string;
    telegram_id?: number | null;
  };
  onLinkTelegram?: () => void;
  onLinkBrowser?: () => void;
  isTelegramWebApp?: boolean;
}

export function SettingsPage({
  theme,
  onThemeChange,
  onLogout,
  showLogout = true,
  user,
  onLinkTelegram,
  onLinkBrowser,
  isTelegramWebApp = false,
}: SettingsPageProps) {
  const toggleTheme = () => onThemeChange(theme === 'dark' ? 'light' : 'dark');

  const hasEmail = Boolean(user?.email);
  const hasTelegram = Boolean(user?.telegram_id);

  const accountItems = [];

  // Email account status
  if (hasEmail) {
    accountItems.push({
      icon: Mail,
      label: 'Email аккаунт',
      status: 'linked' as const,
      action: <CheckCircle className="h-5 w-5 text-[var(--app-success-color,#16a34a)]" />,
    });
  }

  // Telegram account status
  if (hasTelegram) {
    accountItems.push({
      icon: () => (
        <svg className="h-5 w-5" viewBox="0 0 24 24" aria-hidden="true">
          <path
            fill="#229ED9"
            d="M21.9 4.6c.3-.9-.6-1.7-1.5-1.4L3.5 9.3c-1 .3-1 1.7 0 2l4 1.2 1.5 4.8c.3 1 .1 1.1.5 1.1.4 0 .6-.2.9-.5l2.3-2.2 4.4 3.2c.8.6 1.9.2 2.1-.8L21.9 4.6zm-3 1.8-7.7 6.9a.9.9 0 0 0-.3.5l-.6 2.8-1-3.1a.9.9 0 0 0-.6-.6l-3.1-.9 13.3-5.6z"
          />
        </svg>
      ),
      label: 'Telegram аккаунт',
      status: 'linked' as const,
      action: <CheckCircle className="h-5 w-5 text-[var(--app-success-color,#16a34a)]" />,
    });
  }

  // Link Telegram button (for browser users)
  if (!isTelegramWebApp && !hasTelegram && onLinkTelegram) {
    accountItems.push({
      icon: () => (
        <svg className="h-5 w-5" viewBox="0 0 24 24" aria-hidden="true">
          <path
            fill="#229ED9"
            d="M21.9 4.6c.3-.9-.6-1.7-1.5-1.4L3.5 9.3c-1 .3-1 1.7 0 2l4 1.2 1.5 4.8c.3 1 .1 1.1.5 1.1.4 0 .6-.2.9-.5l2.3-2.2 4.4 3.2c.8.6 1.9.2 2.1-.8L21.9 4.6zm-3 1.8-7.7 6.9a.9.9 0 0 0-.3.5l-.6 2.8-1-3.1a.9.9 0 0 0-.6-.6l-3.1-.9 13.3-5.6z"
          />
        </svg>
      ),
      label: 'Привязать Telegram',
      status: 'action' as const,
      action: (
        <button
          onClick={onLinkTelegram}
          className="px-3 py-1 bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Привязать
        </button>
      ),
    });
  }

  // Link Browser button (for Telegram users)
  if (isTelegramWebApp && !hasEmail && onLinkBrowser) {
    accountItems.push({
      icon: LinkIcon,
      label: 'Привязать браузерный аккаунт',
      status: 'action' as const,
      action: (
        <button
          onClick={onLinkBrowser}
          className="px-3 py-1 bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Привязать
        </button>
      ),
    });
  }

  const settingsSections = [
    {
      title: 'Аккаунты',
      items: accountItems,
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
              <div className="relative h-6 w-11 rounded-full bg-[var(--app-toggle-track,#dbe7ff)] transition-colors peer-checked:bg-[var(--tg-theme-button-color,#3390ec)] after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:bg-[var(--app-toggle-thumb,#ffffff)] after:transition-transform after:content-[''] peer-checked:after:translate-x-full"></div>
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
      <div className="flex items-center justify-between gap-4 rounded-2xl bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-4">
        <div>
          <div className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
            Тема интерфейса
          </div>
          <div className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
            Переключение между светлой и темной схемой
          </div>
        </div>
        <ThemeToggle theme={theme} onToggle={toggleTheme} />
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
                    {typeof Icon === 'function' ? <Icon /> : <Icon className="w-5 h-5 text-[var(--tg-theme-button-color,#3390ec)]" />}
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

      {showLogout && (
        <button
          onClick={onLogout}
          className="w-full flex items-center justify-center gap-2 rounded-xl bg-[var(--app-danger-bg,#ef4444)] py-3 font-medium text-[var(--app-danger-text,#ffffff)] transition-colors hover:bg-[var(--app-danger-bg-hover,#dc2626)]"
        >
          <LogOut className="w-5 h-5" />
          Выйти из аккаунта
        </button>
      )}
    </div>
  );
}
