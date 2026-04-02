import { t } from '../../lib/i18n';

type Primitive = string | number | boolean | null | undefined;

export type ApiErrorParams = Record<string, Primitive>;

export type ParsedApiError = {
  detail: string;
  errorCode: string | null;
  errorParams: ApiErrorParams;
};

export function parseApiErrorPayload(
  payload: unknown,
  fallbackDetail = ''
): ParsedApiError {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return {
      detail: fallbackDetail,
      errorCode: null,
      errorParams: {},
    };
  }

  const record = payload as Record<string, unknown>;
  const rawParams = record.error_params;

  return {
    detail: typeof record.detail === 'string' ? record.detail : fallbackDetail,
    errorCode: typeof record.error_code === 'string' ? record.error_code : null,
    errorParams:
      rawParams && typeof rawParams === 'object' && !Array.isArray(rawParams)
        ? (rawParams as ApiErrorParams)
        : {},
  };
}

export function getTrialErrorMessage(errorCode: string | null, detail: string): string {
  switch (errorCode ?? detail) {
    case 'account_blocked':
      return t('web.app.errors.trial.accountBlocked');
    case 'trial_already_used':
      return t('web.app.errors.trial.alreadyUsed');
    case 'subscription_exists':
      return t('web.app.errors.trial.subscriptionExists');
    case 'remnawave_identity_conflict':
      return t('web.app.errors.trial.identityConflict');
    case 'remnawave_not_configured':
      return t('web.app.errors.trial.notConfigured');
    case 'remnawave_unavailable':
      return t('web.app.errors.trial.unavailable');
    default:
      return detail;
  }
}

export function getPromoErrorMessage(errorCode: string | null, detail: string): string {
  switch (errorCode ?? detail) {
    case 'code_not_found':
    case 'promo code not found':
      return t('web.app.errors.promo.notFound');
    case 'code_disabled':
    case 'promo code is disabled':
      return t('web.app.errors.promo.disabled');
    case 'campaign_inactive':
    case 'promo campaign is not active':
      return t('web.app.errors.promo.campaignInactive');
    case 'campaign_not_started':
    case 'promo campaign has not started yet':
      return t('web.app.errors.promo.notStarted');
    case 'campaign_ended':
    case 'promo campaign has already ended':
      return t('web.app.errors.promo.alreadyEnded');
    case 'account_blocked':
    case 'blocked accounts cannot redeem promo codes':
      return t('web.app.errors.promo.blocked');
    case 'selected_plans_only':
    case 'promo code can be used only for selected plans':
      return t('web.app.errors.promo.selectedPlansOnly');
    case 'not_for_plan':
    case 'promo code is not available for this plan':
      return t('web.app.errors.promo.notForPlan');
    case 'first_purchase_only':
    case 'promo code is available only for the first paid purchase':
      return t('web.app.errors.promo.firstPurchaseOnly');
    case 'requires_active_subscription':
    case 'promo code requires an active subscription':
      return t('web.app.errors.promo.requiresActiveSubscription');
    case 'requires_no_subscription':
    case 'promo code requires no active subscription':
      return t('web.app.errors.promo.requiresNoSubscription');
    case 'campaign_limit_reached':
    case 'promo campaign redemption limit reached':
      return t('web.app.errors.promo.campaignLimitReached');
    case 'account_limit_reached':
    case 'promo code redemption limit reached for this account':
      return t('web.app.errors.promo.accountLimitReached');
    case 'code_limit_reached':
    case 'promo code redemption limit reached':
      return t('web.app.errors.promo.codeLimitReached');
    case 'currency_mismatch':
    case 'promo code currency does not match selected payment method':
      return t('web.app.errors.promo.currencyMismatch');
    case 'no_price_improvement':
    case 'promo code does not improve the selected plan price':
      return t('web.app.errors.promo.noPriceImprovement');
    case 'zero_payment_use_direct':
    case 'promo code reduces payment amount to zero; use direct redemption instead':
      return t('web.app.errors.promo.directRedeem');
    case 'cannot_use_for_plan_purchase':
    case 'promo code cannot be used for plan purchase':
      return t('web.app.errors.promo.otherScenario');
    case 'cannot_redeem_directly':
    case 'promo code cannot be redeemed directly':
      return t('web.app.errors.promo.useOnPurchase');
    default:
      return detail;
  }
}

export function getPaymentErrorMessage(errorCode: string | null, detail: string): string {
  switch (errorCode ?? detail) {
    case 'yookassa_not_configured':
    case 'YooKassa credentials are not configured':
      return t('web.app.errors.payment.yookassaNotConfigured');
    case 'stars_bot_token_required':
    case 'BOT_TOKEN is required for Telegram Stars':
      return t('web.app.errors.payment.starsBotTokenRequired');
    case 'stars_callback_not_configured':
    case 'API_TOKEN is required for Telegram Stars callbacks':
      return t('web.app.errors.payment.starsCallbackNotConfigured');
    case 'insufficient_funds':
    case 'insufficient funds':
      return t('web.app.errors.payment.insufficientFunds');
    case 'stars_price_not_configured':
      return t('web.app.errors.payment.starsPriceNotConfigured');
    default: {
      const promoMessage = getPromoErrorMessage(errorCode, detail);
      if (promoMessage !== detail) {
        return promoMessage;
      }

      if (detail.startsWith('Telegram Stars price is not configured for plan ')) {
        return t('web.app.errors.payment.starsPriceNotConfigured');
      }

      return detail;
    }
  }
}

export function getWithdrawalErrorMessage(
  errorCode: string | null,
  detail: string,
  errorParams: ApiErrorParams = {}
): string {
  switch (errorCode ?? detail) {
    case 'destination_required':
    case 'destination value is required':
      return t('web.app.errors.withdrawal.destinationRequired');
    case 'invalid_card':
    case 'invalid bank card number':
      return t('web.app.errors.withdrawal.invalidCard');
    case 'account_blocked':
    case 'blocked accounts cannot create withdrawals':
      return t('web.app.errors.withdrawal.accountBlocked');
    case 'insufficient_available':
    case 'insufficient referral funds for withdrawal':
      return t('web.app.errors.withdrawal.insufficientFunds');
    case 'minimum_amount': {
      const amount = errorParams.amount;
      if (typeof amount === 'number' || typeof amount === 'string') {
        return t('web.app.errors.withdrawal.minimumAmount', { amount });
      }
      break;
    }
    default:
      break;
  }

  if (detail.startsWith('minimum withdrawal amount is ')) {
    return t('web.app.errors.withdrawal.minimumAmount', {
      amount: detail.replace('minimum withdrawal amount is ', ''),
    });
  }

  return detail;
}

export function isReferralAlreadyHandledError(
  errorCode: string | null,
  detail: string
): boolean {
  return (
    errorCode === 'already_claimed' ||
    errorCode === 'window_closed' ||
    detail === 'referral already claimed' ||
    detail === t('web.app.referralDetail.alreadyClaimed') ||
    detail === 'referral attribution is closed after the first paid purchase' ||
    detail === t('web.app.referralDetail.windowClosed')
  );
}

export function isReferralSelfError(errorCode: string | null, detail: string): boolean {
  return (
    errorCode === 'self_referral' ||
    detail === 'self referral is not allowed' ||
    detail === t('web.app.referralDetail.selfReferral')
  );
}

export function isReferralCodeNotFoundError(
  errorCode: string | null,
  detail: string
): boolean {
  return (
    errorCode === 'code_not_found' ||
    detail === 'referral code not found' ||
    detail === t('web.app.referralDetail.notFound')
  );
}

export function getLinkingErrorMessage(errorCode: string | null, detail: string): string {
  switch (errorCode ?? detail) {
    case 'token_not_found':
      return t('web.app.errors.linking.tokenNotFound');
    case 'token_expired':
      return t('web.app.errors.linking.tokenExpired');
    case 'token_already_used':
      return t('web.app.errors.linking.tokenAlreadyUsed');
    case 'token_type_invalid':
      return t('web.app.errors.linking.tokenTypeInvalid');
    case 'telegram_already_linked':
      return t('web.app.errors.linking.telegramAlreadyLinked');
    case 'telegram_required':
      return t('web.app.errors.linking.telegramRequired');
    case 'webapp_url_missing':
      return t('web.app.errors.linking.webappUrlMissing');
    case 'browser_complete_in_browser':
      return t('web.app.errors.linking.browserCompleteInBrowser');
    case 'account_not_found':
      return t('web.app.errors.linking.accountNotFound');
    case 'merge_conflict':
      return t('web.app.errors.linking.mergeConflict');
    default:
      return detail;
  }
}
