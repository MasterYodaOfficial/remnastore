import React from 'react';
import { Check, Zap } from 'lucide-react';
import { formatRubles } from '../../lib/currency';

interface Plan {
  id: string;
  name: string;
  price: number;
  duration: number; // days
  features: string[];
  popular?: boolean;
}

interface PlansPageProps {
  plans: Plan[];
  balance: number;
  onBuyPlan: (planId: string) => void;
  onTopUp: () => void;
}

export function PlansPage({ plans, balance, onBuyPlan, onTopUp }: PlansPageProps) {
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
              <div className="flex items-baseline gap-1 mt-2">
                <span className="text-3xl font-bold text-[var(--tg-theme-button-color,#3390ec)]">
                  {formatRubles(plan.price)}
                </span>
                <span className="text-lg text-[var(--tg-theme-hint-color,#999999)]">₽</span>
                <span className="text-sm text-[var(--tg-theme-hint-color,#999999)] ml-1">
                  / {plan.duration} дней
                </span>
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
              onClick={() => {
                if (balance >= plan.price) {
                  onBuyPlan(plan.id);
                } else {
                  onTopUp();
                }
              }}
              className={`w-full py-3 rounded-xl font-medium hover:opacity-90 transition-opacity ${
                balance >= plan.price
                  ? 'bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)]'
                  : 'bg-[var(--app-surface-color,#dbe4f2)] text-[var(--app-muted-contrast,#475569)]'
              }`}
            >
              {balance >= plan.price ? 'Купить' : 'Пополнить баланс'}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
