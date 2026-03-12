import React, { useMemo, useState } from 'react';
import QRCode from 'react-qr-code';
import {
  ArrowLeft,
  Copy,
  ExternalLink,
  KeyRound,
  Link2,
  QrCode,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  Monitor,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import {
  buildClientImportUrl,
  SUBSCRIPTION_CLIENTS,
  type SubscriptionClientApp,
  type SubscriptionClientPlatform,
} from '../lib/subscription-clients';
import {
  decodeAccessLinkLabel,
  formatBytes,
  formatSubscriptionStatus,
  type SubscriptionAccessSnapshot,
} from '../lib/subscription-access';

interface SubscriptionAccessPageProps {
  data: SubscriptionAccessSnapshot | null;
  isLoading: boolean;
  isTelegramWebApp: boolean;
  onBack: () => void;
  onRefresh: () => void;
  onCopy: (value: string, label: string) => void;
}

interface QrState {
  title: string;
  value: string;
  description?: string;
}

const PLATFORM_META: Record<
  SubscriptionClientPlatform,
  { label: string; icon: typeof Smartphone }
> = {
  ios: { label: 'iPhone и iPad', icon: Smartphone },
  android: { label: 'Android', icon: Smartphone },
  desktop: { label: 'Компьютер', icon: Monitor },
};

function openExternal(url: string) {
  if (typeof window === 'undefined') {
    return;
  }

  const popup = window.open(url, '_blank', 'noopener,noreferrer');
  if (!popup) {
    window.location.assign(url);
  }
}

function launchImport(url: string) {
  if (typeof window === 'undefined') {
    return;
  }

  window.location.assign(url);
}

function formatUpdatedAt(value?: string | null): string | null {
  if (!value) {
    return null;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatExpiresAt(value?: string | null): string {
  if (!value) {
    return 'Не указано';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return 'Не указано';
  }

  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function StatusBanner({
  source,
  updatedAt,
}: {
  source: SubscriptionAccessSnapshot['source'];
  updatedAt: string | null;
}) {
  if (source === 'remote') {
    return null;
  }

  const content =
    source === 'cache'
      ? {
          title: 'Показана кэшированная копия',
          body: 'Панель Remnawave недоступна. Отображаем последнюю сохраненную выдачу конфигов.',
          className:
            'border-amber-300/70 bg-amber-50 text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-100',
        }
      : source === 'local_fallback'
        ? {
            title: 'Доступна только локальная ссылка',
            body: 'Raw keys временно недоступны, но основная ссылка подписки сохранена локально.',
            className:
              'border-sky-300/70 bg-sky-50 text-sky-900 dark:border-sky-500/40 dark:bg-sky-500/10 dark:text-sky-100',
          }
        : {
            title: 'Конфиг пока недоступен',
            body: 'У аккаунта еще нет активной ссылки подписки или Remnawave не вернул данные.',
            className:
              'border-slate-300/70 bg-slate-50 text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100',
          };

  return (
    <div className={`rounded-[24px] border px-4 py-4 ${content.className}`}>
      <div className="text-sm font-semibold">{content.title}</div>
      <div className="mt-2 text-sm leading-6 opacity-90">{content.body}</div>
      {updatedAt && <div className="mt-2 text-xs opacity-70">Последнее обновление: {updatedAt}</div>}
    </div>
  );
}

export function SubscriptionAccessPage({
  data,
  isLoading,
  isTelegramWebApp,
  onBack,
  onRefresh,
  onCopy,
}: SubscriptionAccessPageProps) {
  const [qrState, setQrState] = useState<QrState | null>(null);
  const updatedAt = formatUpdatedAt(data?.refreshed_at ?? null);

  const rawLinks = useMemo(
    () =>
      (data?.links ?? []).map((link) => ({
        label: decodeAccessLinkLabel(link),
        value: link,
      })),
    [data]
  );

  const ssConfLinks = useMemo(
    () =>
      Object.entries(data?.ssconf_links ?? {}).map(([key, value]) => ({
        label: key,
        value,
      })),
    [data]
  );

  const renderClientCard = (client: SubscriptionClientApp) => {
    const importUrl = buildClientImportUrl(client, data?.subscription_url ?? null);

    return (
      <div
        key={client.id}
        className={`rounded-[24px] border p-4 ${
          client.featured
            ? 'border-sky-300 bg-sky-50/80 dark:border-sky-500/40 dark:bg-sky-500/10'
            : 'border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)]'
        }`}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-[var(--tg-theme-text-color,#000000)]">
              {client.name}
            </div>
            <div className="mt-2 text-sm leading-6 text-[var(--tg-theme-hint-color,#64748b)]">
              {client.description}
            </div>
          </div>
          {client.featured && (
            <span className="rounded-full bg-[var(--tg-theme-button-color,#3390ec)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--tg-theme-button-text-color,#ffffff)]">
              Рекомендуем
            </span>
          )}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            onClick={() => openExternal(client.installUrl)}
            className="rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-2.5 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition hover:opacity-90"
          >
            Установить
            <span className="ml-2 text-[var(--tg-theme-hint-color,#64748b)]">{client.installLabel}</span>
          </button>
          {importUrl && (
            <button
              onClick={() => launchImport(importUrl)}
              className="rounded-xl bg-[var(--tg-theme-button-color,#3390ec)] px-4 py-2.5 text-sm font-semibold text-[var(--tg-theme-button-text-color,#ffffff)] transition hover:opacity-90"
            >
              Автодобавление
            </button>
          )}
          {data?.subscription_url && (
            <button
              onClick={() => onCopy(data.subscription_url as string, 'Ссылка подписки')}
              className="rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-transparent px-4 py-2.5 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition hover:opacity-90"
            >
              Скопировать ссылку
            </button>
          )}
        </div>

        <div className="mt-4 rounded-2xl bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-3 text-sm leading-6 text-[var(--tg-theme-hint-color,#64748b)]">
          {client.manualHint}
        </div>
      </div>
    );
  };

  return (
    <>
      <Dialog open={Boolean(qrState)} onOpenChange={(open) => !open && setQrState(null)}>
        <DialogContent className="border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>{qrState?.title}</DialogTitle>
            <DialogDescription>{qrState?.description || 'Отсканируйте QR-код для импорта.'}</DialogDescription>
          </DialogHeader>
          {qrState && (
            <div className="flex flex-col items-center gap-4">
              <div className="rounded-[24px] bg-white p-4">
                <QRCode value={qrState.value} size={256} />
              </div>
              <button
                onClick={() => onCopy(qrState.value, qrState.title)}
                className="w-full rounded-xl bg-[var(--tg-theme-button-color,#3390ec)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-button-text-color,#ffffff)] transition hover:opacity-90"
              >
                Скопировать
              </button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <div className="px-4 pb-28 pt-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[1120px] space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button
              onClick={onBack}
              className="inline-flex items-center gap-2 rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-2.5 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition hover:opacity-90"
            >
              <ArrowLeft className="h-4 w-4" />
              Назад
            </button>
            <button
              onClick={onRefresh}
              className="inline-flex items-center gap-2 rounded-xl bg-[var(--tg-theme-button-color,#3390ec)] px-4 py-2.5 text-sm font-semibold text-[var(--tg-theme-button-text-color,#ffffff)] transition hover:opacity-90"
            >
              <RefreshCw className="h-4 w-4" />
              Обновить
            </button>
          </div>

          <section className="rounded-[28px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] p-6 shadow-[0_24px_60px_rgba(15,23,42,0.08)]">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-3xl">
                <div className="inline-flex items-center gap-2 rounded-full bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--tg-theme-hint-color,#64748b)]">
                  <ShieldCheck className="h-4 w-4" />
                  Выдача доступа
                </div>
                <h1 className="mt-4 text-3xl font-semibold tracking-tight text-[var(--tg-theme-text-color,#000000)]">
                  Подключение VPN
                </h1>
                <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--tg-theme-hint-color,#64748b)]">
                  Здесь собраны ссылка подписки, raw keys и быстрые сценарии подключения для клиентов.
                </p>
              </div>
              {isTelegramWebApp && (
                <div className="max-w-sm rounded-[22px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-3 text-sm leading-6 text-[var(--tg-theme-hint-color,#64748b)]">
                  Внутри Telegram deep link клиента может не открыться. Держите как fallback копирование ссылки и QR-коды.
                </div>
              )}
            </div>
          </section>

          {isLoading ? (
            <div className="rounded-[28px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] p-6 text-sm text-[var(--tg-theme-hint-color,#64748b)]">
              Загружаем актуальные данные доступа из панели подписок.
            </div>
          ) : (
            <>
              <StatusBanner source={data?.source ?? 'none'} updatedAt={updatedAt} />

              <section className="grid gap-4 md:grid-cols-3">
                <div className="rounded-[24px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] p-5">
                  <div className="text-xs uppercase tracking-[0.16em] text-[var(--tg-theme-hint-color,#64748b)]">Статус</div>
                  <div className="mt-3 text-2xl font-semibold text-[var(--tg-theme-text-color,#000000)]">
                    {formatSubscriptionStatus(data?.status, data?.is_active)}
                  </div>
                </div>
                <div className="rounded-[24px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] p-5">
                  <div className="text-xs uppercase tracking-[0.16em] text-[var(--tg-theme-hint-color,#64748b)]">До окончания</div>
                  <div className="mt-3 text-2xl font-semibold text-[var(--tg-theme-text-color,#000000)]">
                    {data?.days_left ? `${data.days_left} дн.` : 'Нет данных'}
                  </div>
                  <div className="mt-2 text-sm text-[var(--tg-theme-hint-color,#64748b)]">
                    {formatExpiresAt(data?.expires_at)}
                  </div>
                </div>
                <div className="rounded-[24px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] p-5">
                  <div className="text-xs uppercase tracking-[0.16em] text-[var(--tg-theme-hint-color,#64748b)]">Трафик</div>
                  <div className="mt-3 text-2xl font-semibold text-[var(--tg-theme-text-color,#000000)]">
                    {formatBytes(data?.traffic_used_bytes)} / {formatBytes(data?.traffic_limit_bytes)}
                  </div>
                  <div className="mt-2 text-sm text-[var(--tg-theme-hint-color,#64748b)]">
                    Всего израсходовано: {formatBytes(data?.lifetime_traffic_used_bytes)}
                  </div>
                </div>
              </section>

              {data?.available ? (
                <>
                  <section className="rounded-[28px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] p-6">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="max-w-3xl">
                        <div className="inline-flex items-center gap-2 rounded-full bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--tg-theme-hint-color,#64748b)]">
                          <Link2 className="h-4 w-4" />
                          Основная ссылка подписки
                        </div>
                        <div className="mt-4 break-all rounded-[22px] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-4 text-sm leading-6 text-[var(--tg-theme-text-color,#000000)]">
                          {data.subscription_url || 'Ссылка недоступна'}
                        </div>
                        <div className="mt-4 text-sm leading-6 text-[var(--tg-theme-hint-color,#64748b)]">
                          Если клиент умеет работать с URL подписки, этого достаточно для импорта всей конфигурации.
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {data.subscription_url && (
                          <>
                            <button
                              onClick={() => onCopy(data.subscription_url as string, 'Ссылка подписки')}
                              className="inline-flex items-center gap-2 rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition hover:opacity-90"
                            >
                              <Copy className="h-4 w-4" />
                              Скопировать
                            </button>
                            <button
                              onClick={() =>
                                setQrState({
                                  title: 'Ссылка подписки',
                                  value: data.subscription_url as string,
                                  description: 'Отсканируйте код на другом устройстве или импортируйте ссылку позже.',
                                })
                              }
                              className="inline-flex items-center gap-2 rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition hover:opacity-90"
                            >
                              <QrCode className="h-4 w-4" />
                              QR
                            </button>
                            <button
                              onClick={() => openExternal(data.subscription_url as string)}
                              className="inline-flex items-center gap-2 rounded-xl bg-[var(--tg-theme-button-color,#3390ec)] px-4 py-3 text-sm font-semibold text-[var(--tg-theme-button-text-color,#ffffff)] transition hover:opacity-90"
                            >
                              <ExternalLink className="h-4 w-4" />
                              Открыть
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </section>

                  <section className="rounded-[28px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] p-6">
                    <div className="flex items-center gap-3">
                      <KeyRound className="h-5 w-5 text-[var(--tg-theme-button-color,#3390ec)]" />
                      <div>
                        <h2 className="text-xl font-semibold text-[var(--tg-theme-text-color,#000000)]">Raw keys</h2>
                        <p className="mt-1 text-sm leading-6 text-[var(--tg-theme-hint-color,#64748b)]">
                          Прямые ключи пригодятся, если клиент не умеет импортировать URL подписки.
                        </p>
                      </div>
                    </div>
                    {rawLinks.length > 0 ? (
                      <div className="mt-5 grid gap-3">
                        {rawLinks.map((link) => (
                          <div
                            key={link.value}
                            className="rounded-[22px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] p-4"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div className="min-w-0">
                                <div className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
                                  {link.label}
                                </div>
                                <div className="mt-2 break-all text-xs leading-6 text-[var(--tg-theme-hint-color,#64748b)]">
                                  {link.value}
                                </div>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                <button
                                  onClick={() => onCopy(link.value, link.label)}
                                  className="rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition hover:opacity-90"
                                >
                                  Скопировать
                                </button>
                                <button
                                  onClick={() =>
                                    setQrState({
                                      title: link.label,
                                      value: link.value,
                                      description: 'Отсканируйте код в клиенте для импорта этого конкретного ключа.',
                                    })
                                  }
                                  className="rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition hover:opacity-90"
                                >
                                  QR
                                </button>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="mt-5 rounded-[22px] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-4 text-sm leading-6 text-[var(--tg-theme-hint-color,#64748b)]">
                        Панель не вернула raw keys для этого аккаунта. Используйте основную ссылку подписки.
                      </div>
                    )}

                    {ssConfLinks.length > 0 && (
                      <div className="mt-6">
                        <div className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
                          Дополнительные форматы
                        </div>
                        <div className="mt-3 grid gap-3">
                          {ssConfLinks.map((link) => (
                            <div
                              key={link.label}
                              className="rounded-[20px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] p-4"
                            >
                              <div className="flex flex-wrap items-center justify-between gap-3">
                                <div>
                                  <div className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
                                    {link.label}
                                  </div>
                                  <div className="mt-2 break-all text-xs leading-6 text-[var(--tg-theme-hint-color,#64748b)]">
                                    {link.value}
                                  </div>
                                </div>
                                <button
                                  onClick={() => onCopy(link.value, link.label)}
                                  className="rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition hover:opacity-90"
                                >
                                  Скопировать
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </section>

                  <section className="space-y-6">
                    {Object.entries(SUBSCRIPTION_CLIENTS).map(([platform, clients]) => {
                      const platformMeta = PLATFORM_META[platform as SubscriptionClientPlatform];
                      const Icon = platformMeta.icon;

                      return (
                        <div
                          key={platform}
                          className="rounded-[28px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] p-6"
                        >
                          <div className="flex items-center gap-3">
                            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] text-[var(--tg-theme-button-color,#3390ec)]">
                              <Icon className="h-5 w-5" />
                            </div>
                            <div>
                              <h2 className="text-xl font-semibold text-[var(--tg-theme-text-color,#000000)]">
                                {platformMeta.label}
                              </h2>
                              <p className="mt-1 text-sm leading-6 text-[var(--tg-theme-hint-color,#64748b)]">
                                Установите клиент и затем импортируйте ссылку подписки.
                              </p>
                            </div>
                          </div>
                          <div className="mt-5 grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
                            {clients.map(renderClientCard)}
                          </div>
                        </div>
                      );
                    })}
                  </section>
                </>
              ) : (
                <section className="rounded-[28px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] p-6">
                  <div className="text-xl font-semibold text-[var(--tg-theme-text-color,#000000)]">
                    Конфиг пока не выдан
                  </div>
                  <div className="mt-3 max-w-2xl text-sm leading-7 text-[var(--tg-theme-hint-color,#64748b)]">
                    Сначала активируйте подписку или дождитесь синхронизации с Remnawave. После этого здесь появятся ссылка подписки, raw keys и инструкции по клиентам.
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
