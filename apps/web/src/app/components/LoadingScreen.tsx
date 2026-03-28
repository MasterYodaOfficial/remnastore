import React from 'react';

import { t } from '../../lib/i18n';
import { AppLogo } from './AppLogo';

export function LoadingScreen() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[var(--tg-theme-bg-color,#ffffff)] px-4">
      <div className="relative">
        <AppLogo
          className="h-20 w-20 animate-pulse shadow-[0_14px_32px_rgba(51,144,236,0.22)]"
          imageClassName="p-[14%]"
        />
        <div className="absolute inset-0 h-20 w-20 rounded-full border-4 border-[var(--tg-theme-button-color,#3390ec)] border-t-transparent animate-spin"></div>
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
