import React from 'react';
import { HelpCircle } from 'lucide-react';

import { getTranslationValue, t } from '../../lib/i18n';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from './ui/accordion';
import { InfoPageLayout } from './InfoPageLayout';

interface FaqPageProps {
  onBack: () => void;
}

interface FaqItem {
  id: string;
  question: string;
  answer: string;
}

const FAQ_ITEMS = getTranslationValue<FaqItem[]>('web.faq.items') ?? [];

export function FaqPage({ onBack }: FaqPageProps) {
  return (
    <InfoPageLayout
      title={t('web.faq.title')}
      subtitle={t('web.faq.subtitle')}
      onBack={onBack}
    >
      <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--app-surface-color,#dbe4f2)] p-4">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)]">
            <HelpCircle className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
              {t('web.faq.introTitle')}
            </div>
            <p className="mt-1 text-sm leading-6 text-[var(--app-muted-contrast,#475569)]">
              {t('web.faq.introBody')}
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
