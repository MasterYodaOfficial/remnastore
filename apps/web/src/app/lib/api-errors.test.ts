import { describe, expect, it } from 'vitest';

import {
  getLinkingErrorMessage,
  getPaymentErrorMessage,
  getPromoErrorMessage,
  getWithdrawalErrorMessage,
  isReferralAlreadyHandledError,
  isReferralCodeNotFoundError,
  isReferralSelfError,
  parseApiErrorPayload,
} from './api-errors';

describe('parseApiErrorPayload', () => {
  it('extracts detail, error code and params from backend payload', () => {
    expect(
      parseApiErrorPayload({
        detail: 'Недостаточно средств.',
        error_code: 'insufficient_funds',
        error_params: { amount: 30 },
      })
    ).toEqual({
      detail: 'Недостаточно средств.',
      errorCode: 'insufficient_funds',
      errorParams: { amount: 30 },
    });
  });

  it('falls back cleanly for non-object payloads', () => {
    expect(parseApiErrorPayload(null, 'fallback')).toEqual({
      detail: 'fallback',
      errorCode: null,
      errorParams: {},
    });
  });
});

describe('error mappers', () => {
  it('maps payment error codes before looking at raw detail', () => {
    expect(getPaymentErrorMessage('yookassa_not_configured', 'raw detail')).toBe(
      'Оплата картой пока недоступна.'
    );
  });

  it('maps promo error codes to localized web copy', () => {
    expect(getPromoErrorMessage('code_limit_reached', 'raw detail')).toBe(
      'Лимит активаций этого промокода уже исчерпан.'
    );
  });

  it('uses structured amount params for withdrawal minimum amount', () => {
    expect(
      getWithdrawalErrorMessage('minimum_amount', 'raw detail', { amount: 30 })
    ).toBe('Минимальная сумма вывода: 30.');
  });

  it('maps linking error codes to localized web copy', () => {
    expect(getLinkingErrorMessage('token_already_used', 'raw detail')).toBe(
      'Эта ссылка для привязки уже использована.'
    );
  });
});

describe('referral error guards', () => {
  it('treats already claimed and window closed codes as handled', () => {
    expect(isReferralAlreadyHandledError('already_claimed', 'raw')).toBe(true);
    expect(isReferralAlreadyHandledError('window_closed', 'raw')).toBe(true);
  });

  it('detects self-referral and not-found codes', () => {
    expect(isReferralSelfError('self_referral', 'raw')).toBe(true);
    expect(isReferralCodeNotFoundError('code_not_found', 'raw')).toBe(true);
  });
});
