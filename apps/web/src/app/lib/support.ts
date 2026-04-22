import { t } from '../../lib/i18n';

export interface SupportEmailUserContext {
  id?: string | null;
  name?: string | null;
  email?: string | null;
  telegramId?: number | null;
}

export interface SupportEmailSubscriptionContext {
  status?: string | null;
  expiresAt?: string | null;
  isTrial?: boolean;
}

export interface SupportEmailContext {
  browserBrandName?: string | null;
  supportEmail?: string | null;
  user?: SupportEmailUserContext | null;
  subscription?: SupportEmailSubscriptionContext | null;
}

function normalizeSupportValue(value?: string | null): string {
  const normalized = value?.trim();
  return normalized || t('web.supportEmail.values.notSpecified');
}

function formatSupportTimestamp(value?: string | null): string {
  const normalized = value?.trim();
  if (!normalized) {
    return t('web.supportEmail.values.notSpecified');
  }

  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) {
    return normalized;
  }

  return `${new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
  }).format(parsed)} UTC`;
}

function resolveSupportSubscriptionStatus(
  subscription?: SupportEmailSubscriptionContext | null
): string {
  if (subscription?.status === 'ACTIVE') {
    return subscription.isTrial
      ? t('web.supportEmail.values.trial')
      : t('web.supportEmail.values.active');
  }

  return normalizeSupportValue(subscription?.status);
}

export function buildSupportEmailDraft(context: SupportEmailContext): {
  subject: string;
  body: string;
} {
  const user = context.user ?? null;
  const subscription = context.subscription ?? null;
  const browserBrandName =
    context.browserBrandName?.trim() || t('web.supportEmail.values.defaultBrandName');

  return {
    subject: t('web.supportEmail.subject', { brandName: browserBrandName }),
    body: [
      t('web.supportEmail.greeting'),
      '',
      `${t('web.supportEmail.fields.name')}: ${normalizeSupportValue(user?.name)}`,
      `${t('web.supportEmail.fields.email')}: ${normalizeSupportValue(user?.email)}`,
      `${t('web.supportEmail.fields.telegramId')}: ${
        user?.telegramId ? String(user.telegramId) : t('web.supportEmail.values.notSpecified')
      }`,
      `${t('web.supportEmail.fields.accountId')}: ${normalizeSupportValue(user?.id)}`,
      `${t('web.supportEmail.fields.subscriptionStatus')}: ${resolveSupportSubscriptionStatus(
        subscription
      )}`,
      `${t('web.supportEmail.fields.subscriptionExpiresAt')}: ${formatSupportTimestamp(
        subscription?.expiresAt
      )}`,
      '',
      t('web.supportEmail.prompt'),
    ].join('\n'),
  };
}

export function buildSupportMailtoUrl(context: SupportEmailContext): string {
  const supportEmail = context.supportEmail?.trim();
  if (!supportEmail) {
    return '';
  }

  const { subject, body } = buildSupportEmailDraft(context);
  const params = new URLSearchParams({
    subject,
    body,
  });

  return `mailto:${supportEmail}?${params.toString()}`;
}
