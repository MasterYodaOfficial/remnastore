import React from 'react';
import { HelpCircle } from 'lucide-react';

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from './ui/accordion';
import { InfoPageLayout } from './InfoPageLayout';

interface FaqPageProps {
  onBack: () => void;
}

const FAQ_ITEMS = [
  {
    id: 'account-linking',
    question: 'Как работает привязка аккаунтов?',
    answer:
      'Browser и Telegram могут быть связаны в один локальный аккаунт. Это нужно, чтобы подписка, баланс, рефералы и уведомления не расходились между разными способами входа.',
  },
  {
    id: 'trial',
    question: 'Когда доступен пробный период?',
    answer:
      'Пробный период доступен только один раз и только если у аккаунта еще нет активной подписки в Remnawave. Перед активацией backend делает проверку eligibility.',
  },
  {
    id: 'payments',
    question: 'Что происходит, если я закрыл оплату и не завершил её?',
    answer:
      'Незавершенные попытки оплаты не висят бесконечно. Backend отслеживает срок жизни pending-платежей, переводит просроченные попытки в expired и не предлагает продолжать мертвую оплату.',
  },
  {
    id: 'notifications',
    question: 'Какие уведомления сейчас приходят?',
    answer:
      'Сейчас в центре уведомлений появляются события по успешной и неуспешной оплате, скорому окончанию подписки, окончанию подписки, реферальным начислениям и созданию заявки на вывод.',
  },
  {
    id: 'referrals',
    question: 'Когда начисляется реферальная награда?',
    answer:
      'Награда начисляется не в момент перехода по ссылке, а только после первой успешной платной покупки приглашенного пользователя. Trial в реферальную награду не входит.',
  },
  {
    id: 'support',
    question: 'Куда писать, если что-то пошло не так?',
    answer:
      'Используйте кнопку поддержки в настройках. Она ведет в Telegram-support, где можно приложить скриншот, описание сценария и, если есть, время проблемы.',
  },
];

export function FaqPage({ onBack }: FaqPageProps) {
  return (
    <InfoPageLayout
      title="FAQ"
      subtitle="Короткие ответы на базовые вопросы по доступу, оплате, trial и уведомлениям."
      onBack={onBack}
    >
      <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--app-surface-color,#dbe4f2)] p-4">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)]">
            <HelpCircle className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
              База знаний внутри приложения
            </div>
            <p className="mt-1 text-sm leading-6 text-[var(--app-muted-contrast,#475569)]">
              Здесь собраны операционные правила текущей версии продукта. Если ответ не нашелся,
              переходите в поддержку.
            </p>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4">
        <Accordion type="single" collapsible className="w-full">
          {FAQ_ITEMS.map((item) => (
            <AccordionItem key={item.id} value={item.id} className="border-[var(--app-border-color,rgba(15,23,42,0.12))]">
              <AccordionTrigger className="py-5 text-[var(--tg-theme-text-color,#000000)] hover:no-underline">
                {item.question}
              </AccordionTrigger>
              <AccordionContent className="pb-5 text-[var(--app-muted-contrast,#475569)]">
                {item.answer}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </InfoPageLayout>
  );
}
