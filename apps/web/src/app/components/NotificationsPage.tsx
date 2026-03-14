import React from 'react';
import {
  AlertCircle,
  ArrowLeft,
  ArrowUpRight,
  Bell,
  CheckCheck,
  ChevronRight,
  Clock3,
  CreditCard,
  Gift,
  ImageIcon,
  Loader2,
  MessageCircle,
  Wallet,
} from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';

type NotificationPriority = 'info' | 'success' | 'warning' | 'error';
type NotificationType =
  | 'broadcast'
  | 'payment_succeeded'
  | 'payment_failed'
  | 'subscription_expiring'
  | 'subscription_expired'
  | 'referral_reward_received'
  | 'withdrawal_created'
  | 'withdrawal_paid'
  | 'withdrawal_rejected';

interface NotificationAction {
  label: string;
  url: string;
}

interface BroadcastNotificationPayload {
  broadcastId: number | null;
  contentType: 'text' | 'photo';
  imageUrl: string | null;
  bodyHtml: string | null;
  buttons: NotificationAction[];
}

export interface NotificationItemView {
  id: number;
  type: NotificationType;
  title: string;
  body: string;
  priority: NotificationPriority;
  payload?: Record<string, unknown> | null;
  actionLabel?: string | null;
  actionUrl?: string | null;
  isRead: boolean;
  createdAt: string;
}

interface NotificationsPageProps {
  items: NotificationItemView[];
  total: number;
  unreadCount: number;
  isLoading: boolean;
  isLoadingMore?: boolean;
  isUpdatingReadState?: boolean;
  embedded?: boolean;
  onBack?: () => void;
  onMarkRead: (notificationId: number) => void;
  onMarkAllRead: () => void;
  onLoadMore?: () => void;
  onOpenAction?: (notification: NotificationItemView, action?: NotificationAction) => void;
}

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function getStringValue(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const normalized = value.trim();
  return normalized || null;
}

function getBroadcastPayload(notification: NotificationItemView): BroadcastNotificationPayload | null {
  if (notification.type !== 'broadcast' || !isObjectRecord(notification.payload)) {
    return null;
  }

  const contentTypeRaw = getStringValue(notification.payload.content_type ?? notification.payload.contentType);
  if (contentTypeRaw !== 'text' && contentTypeRaw !== 'photo') {
    return null;
  }

  const buttonsRaw = Array.isArray(notification.payload.buttons) ? notification.payload.buttons : [];
  const buttons: NotificationAction[] = buttonsRaw
    .map((item) => {
      if (!isObjectRecord(item)) {
        return null;
      }
      const label = getStringValue(item.text);
      const url = getStringValue(item.url);
      if (!label || !url) {
        return null;
      }
      return { label, url };
    })
    .filter((item): item is NotificationAction => item !== null);

  const broadcastIdRaw = notification.payload.broadcast_id ?? notification.payload.broadcastId;
  const broadcastId =
    typeof broadcastIdRaw === 'number' && Number.isFinite(broadcastIdRaw) ? broadcastIdRaw : null;

  return {
    broadcastId,
    contentType: contentTypeRaw,
    imageUrl: getStringValue(notification.payload.image_url ?? notification.payload.imageUrl),
    bodyHtml: getStringValue(notification.payload.body_html ?? notification.payload.bodyHtml),
    buttons,
  };
}

function getNotificationActions(
  notification: NotificationItemView,
  payload?: BroadcastNotificationPayload | null
): NotificationAction[] {
  const uniqueActions = new Map<string, NotificationAction>();

  for (const action of payload?.buttons ?? []) {
    uniqueActions.set(`${action.label}|${action.url}`, action);
  }

  if (notification.actionLabel && notification.actionUrl) {
    uniqueActions.set(`${notification.actionLabel}|${notification.actionUrl}`, {
      label: notification.actionLabel,
      url: notification.actionUrl,
    });
  }

  return Array.from(uniqueActions.values());
}

function truncateText(value: string, maxLength: number): string {
  const normalized = value.trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

function formatNotificationCreatedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }

  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.max(0, Math.round(diffMs / 60000));
  if (diffMinutes < 1) {
    return 'только что';
  }
  if (diffMinutes < 60) {
    return `${diffMinutes} мин назад`;
  }

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours} ч назад`;
  }

  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function getNotificationAccent(priority: NotificationPriority): string {
  switch (priority) {
    case 'success':
      return 'var(--app-success-color,#16a34a)';
    case 'warning':
      return 'var(--app-warning-color,#ca8a04)';
    case 'error':
      return 'var(--app-danger-bg,#ef4444)';
    default:
      return 'var(--tg-theme-button-color,#3390ec)';
  }
}

function getNotificationIcon(notificationType: NotificationType) {
  switch (notificationType) {
    case 'broadcast':
      return Bell;
    case 'payment_succeeded':
      return CreditCard;
    case 'payment_failed':
      return AlertCircle;
    case 'subscription_expiring':
    case 'subscription_expired':
      return Clock3;
    case 'referral_reward_received':
      return Gift;
    case 'withdrawal_created':
    case 'withdrawal_paid':
    case 'withdrawal_rejected':
      return Wallet;
    default:
      return Bell;
  }
}

export function NotificationsPage({
  items,
  total,
  unreadCount,
  isLoading,
  isLoadingMore = false,
  isUpdatingReadState = false,
  embedded = false,
  onBack,
  onMarkRead,
  onMarkAllRead,
  onLoadMore,
  onOpenAction,
}: NotificationsPageProps) {
  const hasMore = typeof onLoadMore === 'function' && items.length < total;
  const [selectedBroadcastId, setSelectedBroadcastId] = React.useState<number | null>(null);
  const selectedBroadcastNotification =
    items.find((item) => item.id === selectedBroadcastId) ?? null;
  const selectedBroadcastPayload = selectedBroadcastNotification
    ? getBroadcastPayload(selectedBroadcastNotification)
    : null;
  const selectedBroadcastActions = selectedBroadcastNotification
    ? getNotificationActions(selectedBroadcastNotification, selectedBroadcastPayload)
    : [];

  function openBroadcastDetails(notification: NotificationItemView) {
    setSelectedBroadcastId(notification.id);
    if (!notification.isRead) {
      onMarkRead(notification.id);
    }
  }

  return (
    <>
      <div className={embedded ? 'space-y-4' : 'px-4 pb-20 pt-4 space-y-4'}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            {!embedded && onBack ? (
              <button
                onClick={onBack}
                className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90"
                aria-label="Назад"
              >
                <ArrowLeft className="h-5 w-5" />
              </button>
            ) : null}
            <div>
              <h1 className={`${embedded ? 'text-xl' : 'text-2xl'} font-bold text-[var(--tg-theme-text-color,#000000)]`}>
                Уведомления
              </h1>
              <p className="mt-1 text-sm text-[var(--tg-theme-hint-color,#999999)]">
                {unreadCount > 0
                  ? `${unreadCount} непрочитанных из ${total}`
                  : total > 0
                    ? `Все уведомления прочитаны (${total})`
                    : 'Здесь будут события по подписке, оплатам и начислениям'}
              </p>
            </div>
          </div>
          <button
            onClick={onMarkAllRead}
            disabled={unreadCount === 0 || isUpdatingReadState}
            className="inline-flex items-center gap-2 rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-2 text-sm font-medium text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isUpdatingReadState ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCheck className="h-4 w-4" />}
            Прочитать все
          </button>
        </div>

        {isLoading ? (
          <div className="rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--app-surface-color,#dbe4f2)] p-5 text-sm text-[var(--tg-theme-hint-color,#999999)]">
            Загружаем уведомления...
          </div>
        ) : items.length > 0 ? (
          <div className="space-y-3">
            {items.map((item) => {
              const broadcastPayload = getBroadcastPayload(item);
              const broadcastActions = getNotificationActions(item, broadcastPayload);
              const primaryBroadcastAction = broadcastActions[0] ?? null;

              if (broadcastPayload) {
                return (
                  <article
                    key={item.id}
                    className={`overflow-hidden rounded-[28px] border p-3 shadow-[0_18px_42px_rgba(15,23,42,0.08)] transition-colors ${
                      item.isRead
                        ? 'border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)]/80'
                        : 'border-[color:var(--tg-theme-button-color,#3390ec)]/25 bg-[linear-gradient(180deg,rgba(51,144,236,0.12)_0%,rgba(255,255,255,0.02)_100%)]'
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => openBroadcastDetails(item)}
                      className="block w-full text-left"
                      aria-haspopup="dialog"
                    >
                      <div className="overflow-hidden rounded-[24px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[linear-gradient(160deg,rgba(51,144,236,0.16)_0%,rgba(51,144,236,0.03)_52%,rgba(255,255,255,0.02)_100%)] p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="inline-flex items-center gap-2 rounded-full bg-[var(--tg-theme-button-color,#3390ec)]/12 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--tg-theme-button-color,#3390ec)]">
                            <MessageCircle className="h-3.5 w-3.5" />
                            Рассылка
                          </div>
                          <div className="pt-1 text-xs font-medium uppercase tracking-[0.12em] text-[var(--tg-theme-hint-color,#999999)]">
                            {formatNotificationCreatedAt(item.createdAt)}
                          </div>
                        </div>

                        {broadcastPayload.imageUrl ? (
                          <div className="mt-4 overflow-hidden rounded-[22px] border border-white/55 bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] shadow-[0_18px_40px_rgba(51,144,236,0.16)]">
                            <img
                              src={broadcastPayload.imageUrl}
                              alt={item.title}
                              className="h-36 w-full object-cover"
                              loading="lazy"
                            />
                          </div>
                        ) : (
                          <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-3 py-2 text-xs font-medium text-[var(--tg-theme-hint-color,#999999)]">
                            <ImageIcon className="h-4 w-4" />
                            Без фото
                          </div>
                        )}

                        <div className="mt-4 flex items-start gap-3">
                          <div
                            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-white shadow-[0_14px_24px_rgba(51,144,236,0.22)]"
                            style={{ backgroundColor: getNotificationAccent(item.priority) }}
                          >
                            <Bell className="h-5 w-5" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <h2 className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
                                {item.title}
                              </h2>
                              {!item.isRead && (
                                <span className="inline-flex h-2.5 w-2.5 rounded-full bg-[var(--tg-theme-button-color,#3390ec)]" />
                              )}
                            </div>
                            <p
                              className="mt-2 text-sm leading-6 text-[var(--app-muted-contrast,#475569)]"
                              style={{
                                display: '-webkit-box',
                                WebkitBoxOrient: 'vertical',
                                WebkitLineClamp: 3,
                                overflow: 'hidden',
                              }}
                            >
                              {truncateText(item.body, 220)}
                            </p>
                            <div className="mt-3 flex items-center gap-2 text-xs font-medium text-[var(--tg-theme-hint-color,#999999)]">
                              <span>{broadcastPayload.contentType === 'photo' ? 'Фото-рассылка' : 'Текстовая рассылка'}</span>
                              {broadcastActions.length > 1 ? (
                                <span>· +{broadcastActions.length - 1} кнопки в деталях</span>
                              ) : null}
                              {broadcastPayload.broadcastId !== null ? (
                                <span>· #{broadcastPayload.broadcastId}</span>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      </div>
                    </button>

                    <div className="mt-3 flex flex-wrap items-center gap-2 px-1 pb-1">
                      {!item.isRead && (
                        <button
                          onClick={() => onMarkRead(item.id)}
                          className="rounded-xl bg-[var(--tg-theme-button-color,#3390ec)] px-3 py-2 text-xs font-semibold text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90"
                        >
                          Отметить прочитанным
                        </button>
                      )}
                      {primaryBroadcastAction && onOpenAction ? (
                        <button
                          onClick={() => onOpenAction(item, primaryBroadcastAction)}
                          className="inline-flex items-center gap-1 rounded-xl bg-[var(--tg-theme-button-color,#3390ec)] px-4 py-2 text-xs font-semibold text-[var(--tg-theme-button-text-color,#ffffff)] shadow-[0_14px_28px_rgba(51,144,236,0.22)] transition-opacity hover:opacity-90"
                        >
                          {primaryBroadcastAction.label}
                          <ArrowUpRight className="h-3.5 w-3.5" />
                        </button>
                      ) : null}
                    </div>
                  </article>
                );
              }

              const Icon = getNotificationIcon(item.type);
              const accent = getNotificationAccent(item.priority);
              const canOpenAction = Boolean(item.actionLabel && item.actionUrl && onOpenAction);

              return (
                <article
                  key={item.id}
                  className={`rounded-2xl border p-4 transition-colors ${
                    item.isRead
                      ? 'border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)]/70'
                      : 'border-[color:var(--tg-theme-button-color,#3390ec)]/25 bg-[var(--app-surface-color,#dbe4f2)]'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-white"
                      style={{ backgroundColor: accent }}
                    >
                      <Icon className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <h2 className="text-sm font-semibold text-[var(--tg-theme-text-color,#000000)]">
                              {item.title}
                            </h2>
                            {!item.isRead && (
                              <span className="inline-flex h-2.5 w-2.5 rounded-full bg-[var(--tg-theme-button-color,#3390ec)]" />
                            )}
                          </div>
                          <p className="mt-2 text-sm leading-6 text-[var(--app-muted-contrast,#475569)]">
                            {item.body}
                          </p>
                        </div>
                        <div className="text-xs font-medium uppercase tracking-[0.12em] text-[var(--tg-theme-hint-color,#999999)]">
                          {formatNotificationCreatedAt(item.createdAt)}
                        </div>
                      </div>

                      <div className="mt-4 flex flex-wrap items-center gap-2">
                        {!item.isRead && (
                          <button
                            onClick={() => onMarkRead(item.id)}
                            className="rounded-xl bg-[var(--tg-theme-button-color,#3390ec)] px-3 py-2 text-xs font-semibold text-[var(--tg-theme-button-text-color,#ffffff)] transition-opacity hover:opacity-90"
                          >
                            Отметить прочитанным
                          </button>
                        )}
                        {canOpenAction && (
                          <button
                            onClick={() => onOpenAction?.(item)}
                            className="inline-flex items-center gap-1 rounded-xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-transparent px-3 py-2 text-xs font-semibold text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90"
                          >
                            {item.actionLabel}
                            <ChevronRight className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </article>
              );
            })}

            {hasMore && (
              <button
                onClick={onLoadMore}
                disabled={isLoadingMore}
                className="flex w-full items-center justify-center gap-2 rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-3 text-sm font-medium text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLoadingMore ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {isLoadingMore ? 'Загружаем...' : 'Показать еще'}
              </button>
            )}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-5 py-10 text-center">
            <Bell className="mx-auto mb-4 h-14 w-14 text-[var(--tg-theme-hint-color,#999999)] opacity-60" />
            <div className="text-base font-semibold text-[var(--tg-theme-text-color,#000000)]">
              Уведомлений пока нет
            </div>
            <p className="mt-2 text-sm leading-6 text-[var(--tg-theme-hint-color,#999999)]">
              Когда появятся события по оплатам, подписке или рефералам, они будут собираться здесь.
            </p>
          </div>
        )}
      </div>

      <Dialog
        open={selectedBroadcastNotification !== null && selectedBroadcastPayload !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedBroadcastId(null);
          }
        }}
      >
        <DialogContent className="max-h-[calc(100vh-2rem)] max-w-2xl overflow-hidden rounded-[30px] border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-bg-color,#ffffff)] p-0 text-[var(--tg-theme-text-color,#000000)] shadow-[0_28px_90px_rgba(15,23,42,0.28)]">
          {selectedBroadcastNotification && selectedBroadcastPayload ? (
            <div className="max-h-[calc(100vh-2rem)] overflow-y-auto">
              {selectedBroadcastPayload.imageUrl ? (
                <div className="overflow-hidden border-b border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[linear-gradient(180deg,rgba(51,144,236,0.16)_0%,rgba(51,144,236,0.04)_100%)]">
                  <img
                    src={selectedBroadcastPayload.imageUrl}
                    alt={selectedBroadcastNotification.title}
                    className="max-h-[320px] w-full object-cover"
                  />
                </div>
              ) : null}

              <div className="p-5 sm:p-6">
                <DialogHeader className="gap-3 text-left">
                  <div className="flex flex-wrap items-center justify-between gap-3 pr-10">
                    <div className="inline-flex items-center gap-2 rounded-full bg-[var(--tg-theme-button-color,#3390ec)]/12 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--tg-theme-button-color,#3390ec)]">
                      <MessageCircle className="h-3.5 w-3.5" />
                      Рассылка
                    </div>
                    <div className="text-xs font-medium uppercase tracking-[0.12em] text-[var(--tg-theme-hint-color,#999999)]">
                      {formatNotificationCreatedAt(selectedBroadcastNotification.createdAt)}
                    </div>
                  </div>
                  <DialogTitle className="pr-10 text-2xl font-semibold leading-tight text-[var(--tg-theme-text-color,#000000)]">
                    {selectedBroadcastNotification.title}
                  </DialogTitle>
                  <DialogDescription className="text-sm leading-6 text-[var(--tg-theme-hint-color,#999999)]">
                    {selectedBroadcastPayload.contentType === 'photo'
                      ? 'Фото-рассылка'
                      : 'Текстовая рассылка'}
                    {selectedBroadcastPayload.broadcastId !== null
                      ? ` · кампания #${selectedBroadcastPayload.broadcastId}`
                      : ''}
                  </DialogDescription>
                </DialogHeader>

                {selectedBroadcastPayload.bodyHtml ? (
                  <div
                    className="mt-6 space-y-4 text-sm leading-7 text-[var(--app-muted-contrast,#475569)] [&_a]:font-semibold [&_a]:text-[var(--tg-theme-button-color,#3390ec)] [&_blockquote]:rounded-2xl [&_blockquote]:border-l-4 [&_blockquote]:border-[var(--tg-theme-button-color,#3390ec)]/25 [&_blockquote]:bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] [&_blockquote]:px-4 [&_blockquote]:py-3 [&_code]:rounded-md [&_code]:bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] [&_code]:px-1.5 [&_code]:py-0.5 [&_pre]:overflow-x-auto [&_pre]:rounded-2xl [&_pre]:bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] [&_pre]:p-4"
                    dangerouslySetInnerHTML={{ __html: selectedBroadcastPayload.bodyHtml }}
                  />
                ) : (
                  <p className="mt-6 text-sm leading-7 text-[var(--app-muted-contrast,#475569)]">
                    {selectedBroadcastNotification.body}
                  </p>
                )}

                {selectedBroadcastActions.length > 0 ? (
                  <div className="mt-7 grid gap-3">
                    {selectedBroadcastActions.map((action) => (
                      <button
                        key={`${action.label}:${action.url}`}
                        onClick={() => onOpenAction?.(selectedBroadcastNotification, action)}
                        className="inline-flex items-center justify-between rounded-2xl border border-[var(--app-border-color,rgba(15,23,42,0.12))] bg-[var(--tg-theme-secondary-bg-color,#f4f4f5)] px-4 py-3 text-left text-sm font-semibold text-[var(--tg-theme-text-color,#000000)] transition-opacity hover:opacity-90"
                      >
                        <span>{action.label}</span>
                        <ArrowUpRight className="h-4 w-4 shrink-0 text-[var(--tg-theme-button-color,#3390ec)]" />
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
