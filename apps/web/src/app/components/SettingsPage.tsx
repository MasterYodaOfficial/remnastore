import React from 'react';
import {
  Bell,
  CheckCircle,
  History,
  FileText,
  Globe,
  HelpCircle,
  Link as LinkIcon,
  LogOut,
  Mail,
  MessageCircle,
  RefreshCw,
  Shield,
} from 'lucide-react';
import { PromoRedeemCard, type PromoRedeemMessage } from './PromoRedeemCard';
import { ThemeToggle } from './ThemeToggle';
import { t } from '../../lib/i18n';

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
  notificationUnreadCount?: number;
  activePaymentsCount?: number;
  onOpenNotificationsCenter?: () => void;
  onOpenPendingPayments?: () => void;
  onOpenBalanceHistory?: () => void;
  onOpenFaq?: () => void;
  onOpenPrivacy?: () => void;
  onOpenTerms?: () => void;
  onOpenSupport?: () => void;
  promoCode?: string;
  onPromoCodeChange?: (value: string) => void;
  onRedeemPromo?: () => void;
  isRedeemingPromo?: boolean;
  promoMessage?: PromoRedeemMessage | null;
}

type SettingsItem = {
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  label: string;
  action: React.ReactNode;
};

type SettingsSection = {
  title: string;
  items: SettingsItem[];
};

export function SettingsPage({
  theme,
  onThemeChange,
  onLogout,
  showLogout = true,
  user,
  onLinkTelegram,
  onLinkBrowser,
  isTelegramWebApp = false,
  notificationUnreadCount = 0,
  activePaymentsCount = 0,
  onOpenNotificationsCenter,
  onOpenPendingPayments,
  onOpenBalanceHistory,
  onOpenFaq,
  onOpenPrivacy,
  onOpenTerms,
  onOpenSupport,
  promoCode = '',
  onPromoCodeChange,
  onRedeemPromo,
  isRedeemingPromo = false,
  promoMessage = null,
}: SettingsPageProps) {
  const toggleTheme = () => onThemeChange(theme === 'dark' ? 'light' : 'dark');

  const hasEmail = Boolean(user?.email);
  const hasTelegram = Boolean(user?.telegram_id);
  const unavailableLabel = (
    <span className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
      {t('web.settings.unavailable')}
    </span>
  );

  const accountItems: SettingsItem[] = [];

  if (hasEmail) {
    accountItems.push({
      icon: Mail,
      label: t('web.settings.labels.emailAccount'),
      action: <CheckCircle className="h-5 w-5 text-[var(--app-success-color,#16a34a)]" />,
    });
  }

  if (hasTelegram) {
    accountItems.push({
      icon: () => (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            fill="#229ED9"
            d="M21.9 4.6c.3-.9-.6-1.7-1.5-1.4L3.5 9.3c-1 .3-1 1.7 0 2l4 1.2 1.5 4.8c.3 1 .1 1.1.5 1.1.4 0 .6-.2.9-.5l2.3-2.2 4.4 3.2c.8.6 1.9.2 2.1-.8L21.9 4.6zm-3 1.8-7.7 6.9a.9.9 0 0 0-.3.5l-.6 2.8-1-3.1a.9.9 0 0 0-.6-.6l-3.1-.9 13.3-5.6z"
          />
        </svg>
      ),
      label: t('web.settings.labels.telegramAccount'),
      action: <CheckCircle className="h-5 w-5 text-[var(--app-success-color,#16a34a)]" />,
    });
  }

  if (!isTelegramWebApp && !hasTelegram && onLinkTelegram) {
    accountItems.push({
      icon: () => (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            fill="#229ED9"
            d="M21.9 4.6c.3-.9-.6-1.7-1.5-1.4L3.5 9.3c-1 .3-1 1.7 0 2l4 1.2 1.5 4.8c.3 1 .1 1.1.5 1.1.4 0 .6-.2.9-.5l2.3-2.2 4.4 3.2c.8.6 1.9.2 2.1-.8L21.9 4.6zm-3 1.8-7.7 6.9a.9.9 0 0 0-.3.5l-.6 2.8-1-3.1a.9.9 0 0 0-.6-.6l-3.1-.9 13.3-5.6z"
          />
        </svg>
      ),
      label: t('web.settings.labels.linkTelegram'),
      action: (
        <button
          onClick={onLinkTelegram}
          className="px-3 py-1 bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
        >
          {t('web.settings.actions.link')}
        </button>
      ),
    });
  }

  if (isTelegramWebApp && !hasEmail && onLinkBrowser) {
    accountItems.push({
      icon: LinkIcon,
      label: t('web.settings.labels.linkBrowser'),
      action: (
        <button
          onClick={onLinkBrowser}
          className="px-3 py-1 bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
        >
          {t('web.settings.actions.link')}
        </button>
      ),
    });
  }

  const settingsSections: SettingsSection[] = [
    {
      title: t('web.settings.sections.accounts'),
      items: accountItems,
    },
    {
      title: t('web.settings.sections.main'),
      items: [
        {
          icon: Globe,
          label: t('web.settings.labels.language'),
          action: (
            <span className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
              {t('web.settings.labels.russian')}
            </span>
          ),
        },
        {
          icon: Bell,
          label: t('web.settings.labels.notifications'),
          action: onOpenNotificationsCenter ? (
            <button
              onClick={onOpenNotificationsCenter}
              className="inline-flex items-center gap-2 rounded-lg bg-[var(--tg-theme-button-color,#3390ec)] px-3 py-1 text-sm font-medium text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90"
            >
              {t('web.settings.actions.open')}
              {notificationUnreadCount > 0 && (
                <span className="rounded-full bg-white/20 px-1.5 py-0.5 text-[11px] font-semibold">
                  {notificationUnreadCount > 99 ? '99+' : notificationUnreadCount}
                </span>
              )}
            </button>
          ) : (
            unavailableLabel
          ),
        },
      ],
    },
    {
      title: t('web.settings.sections.finance'),
      items: [
        {
          icon: RefreshCw,
          label: t('web.settings.labels.pendingPayments'),
          action: onOpenPendingPayments ? (
            <button
              onClick={onOpenPendingPayments}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-3 py-1 text-sm font-medium text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90"
            >
              {t('web.settings.actions.open')}
              {activePaymentsCount > 0 ? (
                <span className="rounded-full bg-[var(--tg-theme-button-color,#3390ec)] px-1.5 py-0.5 text-[11px] font-semibold text-[var(--tg-theme-button-text-color,#ffffff)]">
                  {activePaymentsCount}
                </span>
              ) : null}
            </button>
          ) : (
            unavailableLabel
          ),
        },
        {
          icon: History,
          label: t('web.settings.labels.balanceHistory'),
          action: onOpenBalanceHistory ? (
            <button
              onClick={onOpenBalanceHistory}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-3 py-1 text-sm font-medium text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90"
            >
              {t('web.settings.actions.open')}
            </button>
          ) : (
            unavailableLabel
          ),
        },
      ],
    },
    {
      title: t('web.settings.sections.support'),
      items: [
        {
          icon: MessageCircle,
          label: t('web.settings.labels.support'),
          action: onOpenSupport ? (
            <button
              onClick={onOpenSupport}
              className="inline-flex items-center gap-2 rounded-lg bg-[var(--tg-theme-button-color,#3390ec)] px-3 py-1 text-sm font-medium text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90"
            >
              {t('web.settings.actions.go')}
            </button>
          ) : (
            unavailableLabel
          ),
        },
        {
          icon: HelpCircle,
          label: t('web.settings.labels.faq'),
          action: onOpenFaq ? (
            <button
              onClick={onOpenFaq}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-3 py-1 text-sm font-medium text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90"
            >
              {t('web.settings.actions.open')}
            </button>
          ) : (
            unavailableLabel
          ),
        },
        {
          icon: Shield,
          label: t('web.settings.labels.privacy'),
          action: onOpenPrivacy ? (
            <button
              onClick={onOpenPrivacy}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-3 py-1 text-sm font-medium text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90"
            >
              {t('web.settings.actions.open')}
            </button>
          ) : (
            unavailableLabel
          ),
        },
        {
          icon: FileText,
          label: t('web.settings.labels.terms'),
          action: onOpenTerms ? (
            <button
              onClick={onOpenTerms}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-3 py-1 text-sm font-medium text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90"
            >
              {t('web.settings.actions.open')}
            </button>
          ) : (
            unavailableLabel
          ),
        },
      ],
    },
  ];

  return (
    <div className="pb-20 px-4 pt-4 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)]">
          {t('web.settings.title')}
        </h1>
      </div>
      <div className="flex items-center justify-between gap-4 rounded-2xl bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-4">
        <div>
          <div className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
            {t('web.settings.themeTitle')}
          </div>
          <div className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
            {t('web.settings.themeSubtitle')}
          </div>
        </div>
        <ThemeToggle theme={theme} onToggle={toggleTheme} />
      </div>

      <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[linear-gradient(135deg,var(--tg-theme-secondary-bg-color,#f4f4f5)_0%,var(--app-surface-color,#dbe4f2)_100%)] px-4 py-4">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)]">
            <LinkIcon className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
              {t('web.settings.accountLinkingTitle')}
            </div>
            <p className="mt-1 text-sm leading-6 text-[var(--app-muted-contrast,#475569)]">
              {t('web.settings.accountLinkingBody')}
            </p>
          </div>
        </div>
      </div>

      {onPromoCodeChange && onRedeemPromo ? (
        <PromoRedeemCard
          code={promoCode}
          onCodeChange={onPromoCodeChange}
          onRedeem={onRedeemPromo}
          isSubmitting={isRedeemingPromo}
          message={promoMessage}
          className="border-none bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] shadow-none dark:border dark:border-slate-800/80 dark:bg-slate-900/90"
        />
      ) : null}

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
                    <Icon className="h-5 w-5 text-[var(--tg-theme-button-color,#3390ec)]" />
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
          {t('web.settings.actions.logout')}
        </button>
      )}
    </div>
  );
}
