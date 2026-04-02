import React from 'react';
import { AlertTriangle, RefreshCw, RotateCcw } from 'lucide-react';

interface AppErrorBoundaryProps {
  children: React.ReactNode;
}

interface AppErrorBoundaryState {
  error: Error | null;
}

function resetLocalAppState() {
  if (typeof window === 'undefined') {
    return;
  }

  const keysToRemove = Object.keys(window.localStorage).filter((key) =>
    key.startsWith('remnastore.')
  );
  for (const key of keysToRemove) {
    window.localStorage.removeItem(key);
  }

  window.sessionStorage.removeItem('remnastore.password_recovery_active');
}

export class AppErrorBoundary extends React.Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = {
    error: null,
  };

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('App render error:', error, errorInfo);
  }

  handleReload = () => {
    if (typeof window !== 'undefined') {
      window.location.reload();
    }
  };

  handleReset = () => {
    resetLocalAppState();
    this.handleReload();
  };

  render() {
    if (!this.state.error) {
      return this.props.children;
    }

    const errorDetails = this.state.error?.stack || this.state.error?.message || String(this.state.error);

    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4 py-8 text-slate-950 dark:bg-slate-950 dark:text-slate-50">
        <div className="w-full max-w-xl rounded-[28px] border border-slate-200 bg-white p-8 shadow-[0_24px_60px_rgba(15,23,42,0.12)] dark:border-slate-800 dark:bg-slate-900">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-100 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300">
            <AlertTriangle className="h-7 w-7 shrink-0" />
          </div>
          <h1 className="mt-6 text-2xl font-semibold">Интерфейс не смог загрузиться</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
            Обычно это связано с битым состоянием в браузере или ошибкой в рантайме после hot reload.
            Можно просто перезагрузить страницу или сбросить локальную сессию.
          </p>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={this.handleReload}
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
            >
              <RefreshCw className="h-4 w-4 shrink-0" />
              Перезагрузить страницу
            </button>
            <button
              type="button"
              onClick={this.handleReset}
              className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-5 py-3 text-sm font-semibold text-slate-700 transition-all duration-200 hover:-translate-y-0.5 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
            >
              <RotateCcw className="h-4 w-4 shrink-0" />
              Сбросить локальную сессию
            </button>
          </div>
          {import.meta.env.DEV ? (
            <pre className="mt-6 overflow-x-auto rounded-2xl bg-slate-950/95 p-4 text-xs leading-6 text-slate-100">
              {errorDetails}
            </pre>
          ) : null}
        </div>
      </div>
    );
  }
}
