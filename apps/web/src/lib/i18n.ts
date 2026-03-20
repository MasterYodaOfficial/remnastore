import commonRu from '@locales/ru/common.json';
import webRu from '@locales/ru/web.json';

type Primitive = string | number | boolean | null | undefined;
type TranslationParams = Record<string, Primitive>;

const DEFAULT_LOCALE = 'ru';

function deepMerge(
  left: Record<string, unknown>,
  right: Record<string, unknown>
): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...left };

  for (const [key, value] of Object.entries(right)) {
    const current = merged[key];
    if (
      value &&
      typeof value === 'object' &&
      !Array.isArray(value) &&
      current &&
      typeof current === 'object' &&
      !Array.isArray(current)
    ) {
      merged[key] = deepMerge(
        current as Record<string, unknown>,
        value as Record<string, unknown>
      );
      continue;
    }
    merged[key] = value;
  }

  return merged;
}

const catalogs: Record<string, Record<string, unknown>> = {
  ru: deepMerge(commonRu as Record<string, unknown>, webRu as Record<string, unknown>),
};

function normalizeLocale(locale?: string | null): string {
  if (!locale) {
    return DEFAULT_LOCALE;
  }

  const normalized = locale.trim().toLowerCase().replace('_', '-');
  return normalized.split('-', 1)[0] || DEFAULT_LOCALE;
}

function resolveValue(payload: Record<string, unknown>, key: string): unknown {
  let current: unknown = payload;
  for (const segment of key.split('.')) {
    if (!current || typeof current !== 'object' || Array.isArray(current) || !(segment in current)) {
      return null;
    }
    current = (current as Record<string, unknown>)[segment];
  }
  return current;
}

export function t(key: string, params: TranslationParams = {}, locale?: string | null): string {
  const normalizedLocale = normalizeLocale(locale);
  const catalog = catalogs[normalizedLocale] ?? catalogs[DEFAULT_LOCALE];
  const fallbackCatalog = catalogs[DEFAULT_LOCALE];

  const rawValue = resolveValue(catalog, key) ?? resolveValue(fallbackCatalog, key);
  if (typeof rawValue !== 'string') {
    return key;
  }

  return rawValue.replace(/\{(\w+)\}/g, (_match, token: string) => {
    const value = params[token];
    return value === undefined || value === null ? `{${token}}` : String(value);
  });
}

export function getTranslationValue<T = unknown>(key: string, locale?: string | null): T | null {
  const normalizedLocale = normalizeLocale(locale);
  const catalog = catalogs[normalizedLocale] ?? catalogs[DEFAULT_LOCALE];
  const fallbackCatalog = catalogs[DEFAULT_LOCALE];

  const rawValue = resolveValue(catalog, key) ?? resolveValue(fallbackCatalog, key);
  return rawValue === null ? null : (rawValue as T);
}

export function getLocaleCatalog(locale?: string | null): Record<string, unknown> {
  return catalogs[normalizeLocale(locale)] ?? catalogs[DEFAULT_LOCALE];
}
