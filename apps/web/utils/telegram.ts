export type TelegramTheme = 'light' | 'dark';

export interface TelegramWebAppUser {
  id: number;
  photo_url?: string;
}

export interface TelegramWebAppLike {
  initData?: string;
  initDataUnsafe?: {
    user?: TelegramWebAppUser;
  };
  platform?: string;
  colorScheme?: TelegramTheme;
  expand?: () => void;
  setHeaderColor?: (color: string) => void;
  setBottomBarColor?: (color: string) => void;
  onEvent?: (event: 'themeChanged', handler: () => void) => void;
  offEvent?: (event: 'themeChanged', handler: () => void) => void;
  openInvoice?: (invoiceUrl: string, callback?: (status: string) => void) => void;
  openTelegramLink?: (url: string) => void;
  openLink?: (url: string, options?: { try_browser?: boolean }) => void;
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebAppLike;
    };
  }
}

// Load Telegram WebApp script dynamically
export const loadTelegramScript = (): Promise<void> => {
  return new Promise((resolve) => {
    if (typeof window !== 'undefined') {
      if (window.Telegram?.WebApp) {
        resolve();
        return;
      }

      const script = document.createElement('script');
      script.src = 'https://telegram.org/js/telegram-web-app.js';
      script.async = true;
      script.onload = () => resolve();
      document.head.appendChild(script);
    } else {
      resolve();
    }
  });
};

// Get Telegram WebApp instance
export const getTelegramWebApp = (): TelegramWebAppLike | null => {
  if (typeof window !== 'undefined') {
    return window.Telegram?.WebApp ?? null;
  }
  return null;
};

export const openTelegramInvoice = (
  invoiceUrl: string,
  callback?: (status: string) => void
): boolean => {
  const tg = getTelegramWebApp();
  if (!tg?.openInvoice) {
    return false;
  }

  try {
    tg.openInvoice(invoiceUrl, callback);
    return true;
  } catch (err) {
    console.error('Telegram invoice open error:', err);
    return false;
  }
};

export const openTelegramLink = (url: string): boolean => {
  const tg = getTelegramWebApp();
  if (!tg?.openTelegramLink) {
    return false;
  }

  try {
    tg.openTelegramLink(url);
    return true;
  } catch (err) {
    console.error('Telegram link open error:', err);
    return false;
  }
};
