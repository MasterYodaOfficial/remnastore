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
  openLink?: (
    url: string,
    options?: { try_browser?: string; try_instant_view?: boolean }
  ) => void;
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebAppLike;
    };
  }
}

const TELEGRAM_SCRIPT_URL = 'https://telegram.org/js/telegram-web-app.js';
const DEFAULT_TELEGRAM_FALLBACK_SCRIPT_PATH = '/vendor/telegram-web-app.js';
const TELEGRAM_HASH_PREFIX = 'tgWebApp';
const TELEGRAM_SCRIPT_TIMEOUT_MS = 4000;

let telegramScriptLoadPromise: Promise<boolean> | null = null;

type TelegramRuntimeConfigKey = 'VITE_TELEGRAM_WEB_APP_FALLBACK_URL';

type TelegramRuntimeConfigStore = Partial<Record<TelegramRuntimeConfigKey, string>>;

const telegramRuntimeConfigGlobal = globalThis as typeof globalThis & {
  __REMNASTORE_RUNTIME_CONFIG__?: TelegramRuntimeConfigStore;
};

const safeDecodeURIComponent = (value: string): string => {
  try {
    return decodeURIComponent(value.replace(/\+/g, '%20'));
  } catch {
    return value;
  }
};

const parseQueryString = (queryString: string): Record<string, string> => {
  if (!queryString) {
    return {};
  }

  return queryString.split('&').reduce<Record<string, string>>((params, entry) => {
    if (!entry) {
      return params;
    }

    const [rawName, rawValue] = entry.split('=');
    const key = safeDecodeURIComponent(rawName ?? '');
    if (!key) {
      return params;
    }

    params[key] = safeDecodeURIComponent(rawValue ?? '');
    return params;
  }, {});
};

const parseHashParams = (locationHash: string): Record<string, string> => {
  const normalizedHash = locationHash.replace(/^#/, '');
  if (!normalizedHash) {
    return {};
  }

  const queryStartIndex = normalizedHash.indexOf('?');
  const queryString = queryStartIndex >= 0
    ? normalizedHash.slice(queryStartIndex + 1)
    : normalizedHash;

  return parseQueryString(queryString);
};

const parseTelegramInitData = (initData: string): TelegramWebAppLike['initDataUnsafe'] => {
  const params = parseQueryString(initData);
  const initDataUnsafe: NonNullable<TelegramWebAppLike['initDataUnsafe']> = {};

  if (!params.user) {
    return initDataUnsafe;
  }

  try {
    const parsedUser = JSON.parse(params.user) as TelegramWebAppUser;
    initDataUnsafe.user = parsedUser;
  } catch {
    return initDataUnsafe;
  }

  return initDataUnsafe;
};

const normalizeHexColor = (value?: string): string | null => {
  if (!value) {
    return null;
  }

  const normalized = value.trim();
  if (/^#[0-9a-fA-F]{6}$/.test(normalized)) {
    return normalized.toLowerCase();
  }

  if (/^#[0-9a-fA-F]{3}$/.test(normalized)) {
    const [, r, g, b] = normalized;
    return `#${r}${r}${g}${g}${b}${b}`.toLowerCase();
  }

  return null;
};

const inferColorScheme = (rawThemeParams?: string): TelegramTheme | undefined => {
  if (!rawThemeParams) {
    return undefined;
  }

  try {
    const parsedThemeParams = JSON.parse(rawThemeParams) as { bg_color?: string };
    const bgColor = normalizeHexColor(parsedThemeParams.bg_color);
    if (!bgColor) {
      return undefined;
    }

    const red = Number.parseInt(bgColor.slice(1, 3), 16);
    const green = Number.parseInt(bgColor.slice(3, 5), 16);
    const blue = Number.parseInt(bgColor.slice(5, 7), 16);
    const brightness = red * 0.299 + green * 0.587 + blue * 0.114;

    return brightness < 128 ? 'dark' : 'light';
  } catch {
    return undefined;
  }
};

const readTelegramRuntimeConfigValue = (
  name: TelegramRuntimeConfigKey,
  fallbackValue: string | undefined
): string | undefined => {
  const runtimeValue = telegramRuntimeConfigGlobal.__REMNASTORE_RUNTIME_CONFIG__?.[name];
  const candidate = typeof runtimeValue === 'string' ? runtimeValue : fallbackValue;
  const normalized = candidate?.trim();
  return normalized ? normalized : undefined;
};

const getTelegramFallbackScriptUrl = (): string =>
  readTelegramRuntimeConfigValue(
    'VITE_TELEGRAM_WEB_APP_FALLBACK_URL',
    import.meta.env.VITE_TELEGRAM_WEB_APP_FALLBACK_URL
  ) ?? DEFAULT_TELEGRAM_FALLBACK_SCRIPT_PATH;

const getTelegramScriptUrls = (): string[] => {
  const scriptUrls = [TELEGRAM_SCRIPT_URL, getTelegramFallbackScriptUrl()];
  return scriptUrls.filter((url, index) => scriptUrls.indexOf(url) === index);
};

const getTelegramWebAppFallback = (): TelegramWebAppLike | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  const launchParams = parseHashParams(window.location.hash);
  if (!Object.keys(launchParams).some((key) => key.startsWith(TELEGRAM_HASH_PREFIX))) {
    return null;
  }

  const initData = launchParams.tgWebAppData;
  return {
    initData,
    initDataUnsafe: initData ? parseTelegramInitData(initData) : undefined,
    platform: launchParams.tgWebAppPlatform,
    colorScheme: inferColorScheme(launchParams.tgWebAppThemeParams),
    expand: () => undefined,
    onEvent: () => undefined,
    offEvent: () => undefined,
  };
};

export const hasTelegramLaunchParams = (): boolean => {
  if (typeof window === 'undefined') {
    return false;
  }

  const launchParams = parseHashParams(window.location.hash);
  return Object.keys(launchParams).some((key) => key.startsWith(TELEGRAM_HASH_PREFIX));
};

const loadTelegramScriptFromUrl = (scriptUrl: string): Promise<boolean> => {
  if (typeof window === 'undefined') {
    return Promise.resolve(false);
  }

  if (window.Telegram?.WebApp) {
    return Promise.resolve(true);
  }

  return new Promise((resolve) => {
    const existingScript = document.querySelector<HTMLScriptElement>(
      `script[src="${scriptUrl}"]`
    );
    const script = existingScript ?? document.createElement('script');

    let settled = false;
    let timeoutId = 0;

    const finalize = () => {
      if (settled) {
        return;
      }

      settled = true;
      window.clearTimeout(timeoutId);
      script.removeEventListener('load', handleFinalize);
      script.removeEventListener('error', handleFinalize);
      if (!existingScript && !window.Telegram?.WebApp) {
        script.remove();
      }
      resolve(Boolean(window.Telegram?.WebApp));
    };

    const handleFinalize = () => finalize();

    timeoutId = window.setTimeout(handleFinalize, TELEGRAM_SCRIPT_TIMEOUT_MS);

    script.addEventListener('load', handleFinalize);
    script.addEventListener('error', handleFinalize);

    if (!existingScript) {
      script.src = scriptUrl;
      script.async = true;
      document.head.appendChild(script);
    }
  });
};

// Load Telegram WebApp script dynamically
export const loadTelegramScript = (): Promise<boolean> => {
  if (typeof window === 'undefined') {
    return Promise.resolve(false);
  }

  if (window.Telegram?.WebApp) {
    return Promise.resolve(true);
  }

  if (telegramScriptLoadPromise) {
    return telegramScriptLoadPromise;
  }

  telegramScriptLoadPromise = (async () => {
    for (const scriptUrl of getTelegramScriptUrls()) {
      const loaded = await loadTelegramScriptFromUrl(scriptUrl);
      if (loaded) {
        return true;
      }
    }

    return Boolean(window.Telegram?.WebApp);
  })().finally(() => {
    telegramScriptLoadPromise = null;
  });

  return telegramScriptLoadPromise;
};

// Get Telegram WebApp instance
export const getTelegramWebApp = (): TelegramWebAppLike | null => {
  if (typeof window !== 'undefined') {
    return window.Telegram?.WebApp ?? getTelegramWebAppFallback();
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

export const openTelegramExternalLink = (
  url: string,
  options: { tryBrowser?: string } = {}
): boolean => {
  const tg = getTelegramWebApp();
  if (!tg?.openLink) {
    return false;
  }

  try {
    if (options.tryBrowser) {
      tg.openLink(url, { try_browser: options.tryBrowser });
    } else {
      tg.openLink(url);
    }
    return true;
  } catch (err) {
    console.error('Telegram external link open error:', err);
    return false;
  }
};
