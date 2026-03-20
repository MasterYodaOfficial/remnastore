import React from 'react';
import { Check, Zap } from 'lucide-react';
import { formatRubles } from '../../lib/currency';
import { t } from '../../lib/i18n';

interface Plan {
  id: string;
  name: string;
  price: number;
  priceStars?: number | null;
  duration: number; // days
  features: string[];
  popular?: boolean;
}

interface PlansPageProps {
  plans: Plan[];
  balance: number;
  onBuyPlan: (planId: string) => void;
  onTopUp: () => void;
  isLoading?: boolean;
  checkoutPlanId?: string | null;
  isTelegramWebApp?: boolean;
  resumablePlanIds?: string[];
}

export function PlansPage({
  plans,
  balance,
  onBuyPlan,
  onTopUp,
  isLoading = false,
  checkoutPlanId = null,
  isTelegramWebApp = false,
  resumablePlanIds = [],
}: PlansPageProps) {
  const getPlanButtonLabel = (plan: Plan): string => {
    if (resumablePlanIds.includes(plan.id)) {
      return t('web.plans.buttonResume');
    }

    const canPayFromBalance = balance >= plan.price;

    if (!isTelegramWebApp) {
      return canPayFromBalance ? t('web.plans.buttonChooseMethod') : t('web.plans.buttonBuy');
    }
    if (canPayFromBalance && plan.priceStars) {
      return t('web.plans.buttonChooseMethod');
    }
    if (canPayFromBalance) {
      return t('web.plans.buttonChooseMethod');
    }
    if (plan.priceStars) {
      return t('web.plans.buttonChooseMethod');
    }
    return t('web.plans.buttonCard');
  };

  if (isLoading && !plans.length) {
    return (
      <div className="pb-20 px-4 pt-4 space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)] mb-2">
            {t('web.plans.title')}
          </h1>
          <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
            {t('web.plans.loadingSubtitle')}
          </p>
        </div>
      </div>
    );
  }

  if (!plans.length) {
    return (
      <div className="pb-20 px-4 pt-4 space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)] mb-2">
            {t('web.plans.title')}
          </h1>
          <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
            {t('web.plans.emptySubtitle')}
          </p>
        </div>

        <button
          onClick={onTopUp}
          className="w-full rounded-xl bg-[var(--tg-theme-button-color,#3390ec)] py-3 font-medium text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90"
        >
          {t('web.header.topUpAction')}
        </button>
      </div>
    );
  }

  return (
    <div className="pb-20 px-4 pt-4 space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)] mb-2">
          {t('web.plans.title')}
        </h1>
        <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
          {t('web.plans.subtitle', { amount: formatRubles(balance) })}
        </p>
      </div>

      <div className="rounded-[24px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[linear-gradient(135deg,var(--tg-theme-secondary-bg-color,#f4f4f5)_0%,var(--app-surface-color,#dbe4f2)_100%)] p-4">
        <div className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
          {t('web.plans.introTitle')}
        </div>
        <p className="mt-1 text-sm leading-6 text-[var(--app-muted-contrast,#475569)]">
          {t('web.plans.introBody')}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {[t('web.plans.introChipBalance'), t('web.plans.introChipCard'), t('web.plans.introChipTelegram')].map((item) => (
            <span
              key={item}
              className="rounded-full border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-3 py-1 text-xs font-medium text-[var(--tg-theme-text-color,#000000)]"
            >
              {item}
            </span>
          ))}
        </div>
      </div>

      <div className="grid gap-4">
        {plans.map((plan) => (
          <div
            key={plan.id}
            className={`relative bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] rounded-2xl p-4 ${
              plan.popular ? 'ring-2 ring-[var(--tg-theme-button-color,#3390ec)]' : ''
            }`}
          >
            {plan.popular && (
              <div className="absolute -top-2 left-4 flex items-center gap-1 rounded-full bg-[var(--tg-theme-button-color,#3390ec)] px-3 py-1 text-xs font-semibold text-[var(--tg-theme-button-text-color,#ffffff)]">
                <Zap className="w-3 h-3" />
                {t('web.plans.popularBadge')}
              </div>
            )}
            
            <div className="mb-4">
              <h3 className="text-xl font-bold text-[var(--tg-theme-text-color,#000000)]">
                {plan.name}
              </h3>
              <div className="mt-2 space-y-1">
                <div className="flex items-baseline gap-1">
                  <span className="text-3xl font-bold text-[var(--tg-theme-button-color,#3390ec)]">
                    {formatRubles(plan.price)}
                  </span>
                  <span className="text-lg text-[var(--tg-theme-hint-color,#999999)]">₽</span>
                  <span className="ml-1 text-sm text-[var(--tg-theme-hint-color,#999999)]">
                    {t('web.plans.duration', { days: plan.duration })}
                  </span>
                </div>
                {isTelegramWebApp && plan.priceStars ? (
                  <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
                    {t('web.plans.starsNote', { stars: plan.priceStars })}
                  </p>
                ) : null}
              </div>
            </div>

            <div className="space-y-2 mb-4">
              {plan.features.map((feature, index) => (
                <div key={index} className="flex items-start gap-2">
                  <Check className="mt-0.5 h-5 w-5 shrink-0 text-[var(--app-success-color,#16a34a)]" />
                  <span className="text-sm text-[var(--tg-theme-text-color,#000000)]">
                    {feature}
                  </span>
                </div>
              ))}
            </div>

            <button
              onClick={() => onBuyPlan(plan.id)}
              disabled={checkoutPlanId === plan.id}
              className="w-full py-3 rounded-xl font-medium bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)] hover:opacity-90 transition-opacity disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {checkoutPlanId === plan.id
                ? t('web.plans.buttonOpening')
                : getPlanButtonLabel(plan)}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
