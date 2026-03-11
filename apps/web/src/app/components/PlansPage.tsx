import React from 'react';
import { Check, Zap } from 'lucide-react';
import { formatRubles } from '../../lib/currency';

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
}

export function PlansPage({
  plans,
  balance,
  onBuyPlan,
  onTopUp,
  isLoading = false,
  checkoutPlanId = null,
  isTelegramWebApp = false,
}: PlansPageProps) {
  const getPlanButtonLabel = (plan: Plan): string => {
    const canPayFromBalance = balance >= plan.price;

    if (!isTelegramWebApp) {
      return canPayFromBalance ? 'Выбрать способ оплаты' : 'Оплатить тариф';
    }
    if (canPayFromBalance && plan.priceStars) {
      return 'Выбрать способ оплаты';
    }
    if (canPayFromBalance) {
      return 'Выбрать способ оплаты';
    }
    if (plan.priceStars) {
      return 'Выбрать способ оплаты';
    }
    return 'Оплатить картой';
  };

  if (isLoading && !plans.length) {
    return (
      <div className="pb-20 px-4 pt-4 space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)] mb-2">
            Выберите тариф
          </h1>
          <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
            Загружаем актуальные тарифы с backend...
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
            Выберите тариф
          </h1>
          <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
            Каталог тарифов пока недоступен. Попробуйте открыть экран позже.
          </p>
        </div>

        <button
          onClick={onTopUp}
          className="w-full rounded-xl bg-[var(--tg-theme-button-color,#3390ec)] py-3 font-medium text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90"
        >
          Пополнить баланс
        </button>
      </div>
    );
  }

  return (
    <div className="pb-20 px-4 pt-4 space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-[var(--tg-theme-text-color,#000000)] mb-2">
          Выберите тариф
        </h1>
        <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
          Ваш баланс: <span className="font-semibold">{formatRubles(balance)} ₽</span>
        </p>
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
                Популярный
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
                    / {plan.duration} дней
                  </span>
                </div>
                {isTelegramWebApp && plan.priceStars ? (
                  <p className="text-sm text-[var(--tg-theme-hint-color,#999999)]">
                    Или {plan.priceStars} Stars внутри Telegram.
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
                ? 'Открываем оплату...'
                : getPlanButtonLabel(plan)}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
