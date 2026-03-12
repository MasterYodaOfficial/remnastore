export type SubscriptionClientPlatform = 'ios' | 'android' | 'desktop';

export interface SubscriptionClientApp {
  id: string;
  platform: SubscriptionClientPlatform;
  name: string;
  featured?: boolean;
  installUrl: string;
  installLabel: string;
  urlScheme?: string;
  requiresBase64?: boolean;
  description: string;
  manualHint: string;
}

export const SUBSCRIPTION_CLIENTS: Record<SubscriptionClientPlatform, SubscriptionClientApp[]> = {
  ios: [
    {
      id: 'happ-ios',
      platform: 'ios',
      name: 'Happ',
      featured: true,
      installUrl: 'https://apps.apple.com/us/app/happ-proxy-utility/id6504287215',
      installLabel: 'App Store',
      urlScheme: 'happ://add/',
      description: 'Открывает ссылку подписки напрямую и быстро добавляет профиль.',
      manualHint: 'Если автодобавление не сработало, скопируйте ссылку подписки и импортируйте ее вручную в Happ.',
    },
    {
      id: 'stash-ios',
      platform: 'ios',
      name: 'Stash',
      installUrl: 'https://apps.apple.com/us/app/stash-rule-based-proxy/id1596063349',
      installLabel: 'App Store',
      urlScheme: 'stash://install-config?url=',
      description: 'Хороший вариант для iPhone и iPad, если нужен ручной контроль профилей.',
      manualHint: 'В Stash можно открыть раздел профилей и вставить URL подписки вручную.',
    },
    {
      id: 'shadowrocket-ios',
      platform: 'ios',
      name: 'Shadowrocket',
      installUrl: 'https://apps.apple.com/ru/app/shadowrocket/id932747118',
      installLabel: 'App Store',
      urlScheme: 'sub://',
      requiresBase64: true,
      description: 'Поддерживает импорт подписки через `sub://` ссылку.',
      manualHint: 'Если iOS не открыл Shadowrocket автоматически, импортируйте ссылку подписки через буфер обмена.',
    },
  ],
  android: [
    {
      id: 'happ-android',
      platform: 'android',
      name: 'Happ',
      featured: true,
      installUrl: 'https://play.google.com/store/apps/details?id=com.happproxy',
      installLabel: 'Google Play',
      urlScheme: 'happ://add/',
      description: 'Самый простой импорт для Android, если нужен минимальный onboarding.',
      manualHint: 'Если переход не сработал, откройте Happ и добавьте ссылку подписки вручную.',
    },
    {
      id: 'v2rayng-android',
      platform: 'android',
      name: 'v2rayNG',
      installUrl: 'https://github.com/2dust/v2rayNG/releases/latest',
      installLabel: 'GitHub Release',
      urlScheme: 'v2rayng://install-config?name=RemnaStore&url=',
      description: 'Подходит для Android и умеет импортировать URL подписки напрямую.',
      manualHint: 'В v2rayNG откройте меню профилей и вставьте URL подписки, если deep link не сработал.',
    },
    {
      id: 'hiddify-android',
      platform: 'android',
      name: 'Hiddify',
      installUrl: 'https://play.google.com/store/apps/details?id=com.vpn4tv.hiddify',
      installLabel: 'Google Play',
      urlScheme: 'hiddify://import/',
      description: 'Рабочий вариант для Android TV и обычных Android-устройств.',
      manualHint: 'При неудачном автодобавлении импортируйте подписку из буфера обмена внутри Hiddify.',
    },
  ],
  desktop: [
    {
      id: 'happ-desktop',
      platform: 'desktop',
      name: 'Happ',
      featured: true,
      installUrl: 'https://github.com/Happ-proxy/happ-desktop/releases/latest',
      installLabel: 'GitHub Release',
      urlScheme: 'happ://add/',
      description: 'Нативный desktop-клиент с поддержкой прямого импорта подписки.',
      manualHint: 'Если deep link не открылся, импортируйте URL подписки вручную из меню профилей.',
    },
    {
      id: 'clash-verge-desktop',
      platform: 'desktop',
      name: 'Clash Verge',
      installUrl: 'https://github.com/clash-verge-rev/clash-verge-rev/releases/latest',
      installLabel: 'GitHub Release',
      urlScheme: 'clash://install-config?url=',
      description: 'Удобный desktop-клиент для Windows, macOS и Linux.',
      manualHint: 'В Clash Verge можно вставить URL подписки в раздел Profiles и импортировать вручную.',
    },
    {
      id: 'flclashx-desktop',
      platform: 'desktop',
      name: 'FlClash',
      installUrl: 'https://github.com/chen08209/FlClash/releases/latest',
      installLabel: 'GitHub Release',
      urlScheme: 'flclashx://install-config?url=',
      description: 'Кроссплатформенный вариант с импортом по URL и ручным профилем.',
      manualHint: 'Если ссылка не открыла приложение, создайте профиль вручную и вставьте URL подписки.',
    },
  ],
};

function encodeImportUrl(url: string, requiresBase64?: boolean): string {
  if (requiresBase64) {
    return btoa(url);
  }

  return encodeURIComponent(url);
}

export function buildClientImportUrl(
  client: SubscriptionClientApp,
  subscriptionUrl: string | null | undefined
): string | null {
  if (!client.urlScheme || !subscriptionUrl) {
    return null;
  }

  return `${client.urlScheme}${encodeImportUrl(subscriptionUrl, client.requiresBase64)}`;
}
