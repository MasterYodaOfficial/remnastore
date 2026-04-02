import React from 'react';
import { FileText, Shield } from 'lucide-react';

import { getTranslationValue, t } from '../../lib/i18n';
import { InfoPageLayout } from './InfoPageLayout';

interface LegalDocumentPageProps {
  kind: 'privacy' | 'terms';
  onBack: () => void;
}

interface LegalSection {
  title: string;
  paragraphs: string[];
}

const PRIVACY_SECTIONS = getTranslationValue<LegalSection[]>('web.legal.privacy.sections') ?? [];
const TERMS_SECTIONS = getTranslationValue<LegalSection[]>('web.legal.terms.sections') ?? [];

export function LegalDocumentPage({ kind, onBack }: LegalDocumentPageProps) {
  const isPrivacy = kind === 'privacy';
  const title = isPrivacy ? t('web.legal.privacy.title') : t('web.legal.terms.title');
  const subtitle = isPrivacy
    ? t('web.legal.privacy.subtitle')
    : t('web.legal.terms.subtitle');
  const sections = isPrivacy ? PRIVACY_SECTIONS : TERMS_SECTIONS;
  const Icon = isPrivacy ? Shield : FileText;

  return (
    <InfoPageLayout title={title} subtitle={subtitle} onBack={onBack}>
      <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--app-surface-color,#dbe4f2)] p-4">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#ffffff)]">
            <Icon className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
              {t('web.legal.currentVersionTitle')}
            </div>
            <p className="mt-1 text-sm leading-6 text-[var(--app-muted-contrast,#475569)]">
              {t('web.legal.currentVersionBody')}
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-4">
        {sections.map((section) => (
          <section
            key={section.title}
            className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] p-5"
          >
            <h2 className="text-base font-semibold text-[var(--tg-theme-text-color,#000000)]">
              {section.title}
            </h2>
            <div className="mt-3 space-y-3 text-sm leading-6 text-[var(--app-muted-contrast,#475569)]">
              {section.paragraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </div>
          </section>
        ))}
      </div>
    </InfoPageLayout>
  );
}
