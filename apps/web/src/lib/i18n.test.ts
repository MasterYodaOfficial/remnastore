import { describe, expect, it } from 'vitest';

import { getTranslationValue, t } from './i18n';

describe('t', () => {
  it('falls back to the default locale and interpolates params', () => {
    expect(t('web.referralPage.subtitle', { rewardRate: 25 }, 'en-US')).toBe(
      'Зарабатывайте 25% с первой подтвержденной оплаты приглашенного пользователя.'
    );
  });

  it('returns the translation key when no string value exists', () => {
    expect(t('web.missing.key')).toBe('web.missing.key');
  });
});

describe('getTranslationValue', () => {
  it('returns structured catalog values', () => {
    expect(getTranslationValue<string[]>('web.app.desktop.changes')).toEqual([
      'Можно управлять подпиской и оплатами из одного браузерного кабинета.',
      'Telegram Mini App и браузер остаются одним аккаунтом после штатной привязки.',
      'Центр уведомлений, баланс и рефералы обновляются без перехода в отдельные сценарии.',
    ]);
  });
});
