import React from 'react';
import { Shield } from 'lucide-react';

export function LoadingScreen() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[var(--tg-theme-bg-color,#ffffff)] px-4">
      <div className="relative">
        <div className="w-20 h-20 rounded-full bg-[var(--tg-theme-button-color,#3390ec)] flex items-center justify-center animate-pulse">
          <Shield className="w-12 h-12 text-white" />
        </div>
        <div className="absolute inset-0 w-20 h-20 rounded-full border-4 border-[var(--tg-theme-button-color,#3390ec)] border-t-transparent animate-spin"></div>
      </div>
      <p className="mt-6 text-lg font-medium text-[var(--tg-theme-text-color,#000000)]">
        Загрузка...
      </p>
      <p className="mt-2 text-sm text-[var(--tg-theme-hint-color,#999999)]">
        Пожалуйста, подождите
      </p>
    </div>
  );
}
