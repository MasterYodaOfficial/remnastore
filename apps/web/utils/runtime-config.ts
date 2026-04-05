type PublicRuntimeConfigKey =
  | 'VITE_API_BASE_URL'
  | 'VITE_SUPABASE_URL'
  | 'VITE_SUPABASE_ANON_KEY'
  | 'VITE_WEB_BRAND_NAME'
  | 'VITE_TELEGRAM_BOT_URL'
  | 'VITE_SUPPORT_TELEGRAM_URL'
  | 'VITE_TELEGRAM_WEB_APP_FALLBACK_URL'

type RuntimeConfigStore = Partial<Record<PublicRuntimeConfigKey, string>>

const DEFAULT_WEB_BRAND_NAME = 'QuickVPN'

const runtimeConfigGlobal = globalThis as typeof globalThis & {
  __REMNASTORE_RUNTIME_CONFIG__?: RuntimeConfigStore
}

function readConfigValue(
  name: PublicRuntimeConfigKey,
  fallbackValue: string | undefined
): string | undefined {
  const runtimeValue = runtimeConfigGlobal.__REMNASTORE_RUNTIME_CONFIG__?.[name]
  const candidate = typeof runtimeValue === 'string' ? runtimeValue : fallbackValue
  const normalized = candidate?.trim()
  return normalized ? normalized : undefined
}

function requireConfigValue(
  name: PublicRuntimeConfigKey,
  fallbackValue: string | undefined
): string {
  const value = readConfigValue(name, fallbackValue)
  if (!value) {
    throw new Error(`Missing required frontend config: ${name}`)
  }
  return value
}

export const apiBaseUrl = (
  readConfigValue('VITE_API_BASE_URL', import.meta.env.VITE_API_BASE_URL) ??
  'http://localhost:8000'
).replace(/\/+$/, '')

export const supabaseUrl = requireConfigValue(
  'VITE_SUPABASE_URL',
  import.meta.env.VITE_SUPABASE_URL
).replace(/\/+$/, '')

export const supabaseAnonKey = requireConfigValue(
  'VITE_SUPABASE_ANON_KEY',
  import.meta.env.VITE_SUPABASE_ANON_KEY
)

export const webBrandName =
  readConfigValue('VITE_WEB_BRAND_NAME', import.meta.env.VITE_WEB_BRAND_NAME) ??
  DEFAULT_WEB_BRAND_NAME

export const telegramBotUrl = (
  readConfigValue('VITE_TELEGRAM_BOT_URL', import.meta.env.VITE_TELEGRAM_BOT_URL) ?? ''
).replace(/\/+$/, '')

export const supportTelegramUrl =
  readConfigValue(
    'VITE_SUPPORT_TELEGRAM_URL',
    import.meta.env.VITE_SUPPORT_TELEGRAM_URL
  ) ?? ''
