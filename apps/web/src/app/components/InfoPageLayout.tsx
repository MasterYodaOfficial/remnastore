import React from 'react';
import { ArrowLeft } from 'lucide-react';
import { t } from '../../lib/i18n';

interface InfoPageLayoutProps {
  title: string;
  subtitle: string;
  onBack: () => void;
  children: React.ReactNode;
}

export function InfoPageLayout({ title, subtitle, onBack, children }: InfoPageLayoutProps) {
  return (
    <div className="px-4 pb-20 pt-4 space-y-4">
      <div className="flex items-start gap-3">
        <button
          onClick={onBack}
          className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90"
          aria-label={t('web.infoPageLayout.backAriaLabel')}
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)]">{title}</h1>
          <p className="mt-2 text-sm leading-6 text-[var(--tg-theme-hint-color,#999999)]">
            {subtitle}
          </p>
        </div>
      </div>

      {children}
    </div>
  );
}
