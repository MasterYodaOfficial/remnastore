import React from 'react';
import { Shield } from 'lucide-react';

import { t } from '../../lib/i18n';

export function LoadingScreen() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[var(--tg-theme-bg-color,#ffffff)] px-4">
      <div className="relative">
        <div className="flex h-20 w-20 items-center justify-center rounded-full bg-[var(--tg-theme-button-color,#3390ec)] animate-pulse">
          <Shield className="h-12 w-12 text-[var(--tg-theme-button-text-color,#ffffff)]" />
        </div>
        <div className="absolute inset-0 w-20 h-20 rounded-full border-4 border-[var(--tg-theme-button-color,#3390ec)] border-t-transparent animate-spin"></div>
      </div>
      <p className="mt-6 text-lg font-medium text-[var(--tg-theme-text-color,#000000)]">
        {t('web.loadingScreen.title')}
      </p>
      <p className="mt-2 text-sm text-[var(--tg-theme-hint-color,#999999)]">
        {t('web.loadingScreen.subtitle')}
      </p>
    </div>
  );
}
