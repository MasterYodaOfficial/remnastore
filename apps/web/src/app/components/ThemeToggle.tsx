import React from 'react';
import { Moon, Sun } from 'lucide-react';

interface ThemeToggleProps {
  theme: 'light' | 'dark';
  onToggle: () => void;
}

export function ThemeToggle({ theme, onToggle }: ThemeToggleProps) {
  const isDark = theme === 'dark';

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isDark}
      aria-label="Переключить тему"
      onClick={onToggle}
      className="relative inline-flex h-8 w-14 shrink-0 items-center overflow-hidden rounded-full border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--app-toggle-track,#dbe7ff)] p-1 transition"
    >
      <span
        className={`flex h-6 w-6 items-center justify-center rounded-full bg-[var(--app-toggle-thumb,#ffffff)] shadow-sm transition-transform ${
          isDark
            ? 'translate-x-6 text-[var(--tg-theme-button-color,#3390ec)]'
            : 'translate-x-0 text-[var(--app-warning-color,#ca8a04)]'
        }`}
      >
        {isDark ? <Moon className="h-3.5 w-3.5" /> : <Sun className="h-3.5 w-3.5" />}
      </span>
      <span className="pointer-events-none absolute left-2 text-[var(--app-warning-color,#ca8a04)] opacity-80">
        <Sun className="h-3.5 w-3.5" />
      </span>
      <span className="pointer-events-none absolute right-2 text-[var(--app-muted-contrast,#94a3b8)]">
        <Moon className="h-3.5 w-3.5" />
      </span>
    </button>
  );
}
