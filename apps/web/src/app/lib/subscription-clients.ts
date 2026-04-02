import { t } from '../../lib/i18n';

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
      installLabel: t('web.subscriptionClients.installLabels.appStore'),
      urlScheme: 'happ://add/',
      description: t('web.subscriptionClients.apps.happIos.description'),
      manualHint: t('web.subscriptionClients.apps.happIos.manualHint'),
    },
    {
      id: 'stash-ios',
      platform: 'ios',
      name: 'Stash',
      installUrl: 'https://apps.apple.com/us/app/stash-rule-based-proxy/id1596063349',
      installLabel: t('web.subscriptionClients.installLabels.appStore'),
      urlScheme: 'stash://install-config?url=',
      description: t('web.subscriptionClients.apps.stashIos.description'),
      manualHint: t('web.subscriptionClients.apps.stashIos.manualHint'),
    },
    {
      id: 'shadowrocket-ios',
      platform: 'ios',
      name: 'Shadowrocket',
      installUrl: 'https://apps.apple.com/ru/app/shadowrocket/id932747118',
      installLabel: t('web.subscriptionClients.installLabels.appStore'),
      urlScheme: 'sub://',
      requiresBase64: true,
      description: t('web.subscriptionClients.apps.shadowrocketIos.description'),
      manualHint: t('web.subscriptionClients.apps.shadowrocketIos.manualHint'),
    },
  ],
  android: [
    {
      id: 'happ-android',
      platform: 'android',
      name: 'Happ',
      featured: true,
      installUrl: 'https://play.google.com/store/apps/details?id=com.happproxy',
      installLabel: t('web.subscriptionClients.installLabels.googlePlay'),
      urlScheme: 'happ://add/',
      description: t('web.subscriptionClients.apps.happAndroid.description'),
      manualHint: t('web.subscriptionClients.apps.happAndroid.manualHint'),
    },
    {
      id: 'v2rayng-android',
      platform: 'android',
      name: 'v2rayNG',
      installUrl: 'https://github.com/2dust/v2rayNG/releases/latest',
      installLabel: t('web.subscriptionClients.installLabels.githubRelease'),
      urlScheme: 'v2rayng://install-config?name=RemnaStore&url=',
      description: t('web.subscriptionClients.apps.v2rayngAndroid.description'),
      manualHint: t('web.subscriptionClients.apps.v2rayngAndroid.manualHint'),
    },
    {
      id: 'hiddify-android',
      platform: 'android',
      name: 'Hiddify',
      installUrl: 'https://play.google.com/store/apps/details?id=com.vpn4tv.hiddify',
      installLabel: t('web.subscriptionClients.installLabels.googlePlay'),
      urlScheme: 'hiddify://import/',
      description: t('web.subscriptionClients.apps.hiddifyAndroid.description'),
      manualHint: t('web.subscriptionClients.apps.hiddifyAndroid.manualHint'),
    },
  ],
  desktop: [
    {
      id: 'happ-desktop',
      platform: 'desktop',
      name: 'Happ',
      featured: true,
      installUrl: 'https://github.com/Happ-proxy/happ-desktop/releases/latest',
      installLabel: t('web.subscriptionClients.installLabels.githubRelease'),
      urlScheme: 'happ://add/',
      description: t('web.subscriptionClients.apps.happDesktop.description'),
      manualHint: t('web.subscriptionClients.apps.happDesktop.manualHint'),
    },
    {
      id: 'clash-verge-desktop',
      platform: 'desktop',
      name: 'Clash Verge',
      installUrl: 'https://github.com/clash-verge-rev/clash-verge-rev/releases/latest',
      installLabel: t('web.subscriptionClients.installLabels.githubRelease'),
      urlScheme: 'clash://install-config?url=',
      description: t('web.subscriptionClients.apps.clashVergeDesktop.description'),
      manualHint: t('web.subscriptionClients.apps.clashVergeDesktop.manualHint'),
    },
    {
      id: 'flclashx-desktop',
      platform: 'desktop',
      name: 'FlClash',
      installUrl: 'https://github.com/chen08209/FlClash/releases/latest',
      installLabel: t('web.subscriptionClients.installLabels.githubRelease'),
      urlScheme: 'flclashx://install-config?url=',
      description: t('web.subscriptionClients.apps.flClashDesktop.description'),
      manualHint: t('web.subscriptionClients.apps.flClashDesktop.manualHint'),
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
