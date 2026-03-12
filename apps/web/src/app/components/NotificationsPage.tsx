import React from 'react';
import {
  AlertCircle,
  Bell,
  CheckCheck,
  ChevronRight,
  Clock3,
  CreditCard,
  Gift,
  Loader2,
  Wallet,
} from 'lucide-react';

type NotificationPriority = 'info' | 'success' | 'warning' | 'error';
type NotificationType =
  | 'payment_succeeded'
  | 'payment_failed'
  | 'subscription_expiring'
  | 'subscription_expired'
  | 'referral_reward_received'
  | 'withdrawal_created'
  | 'withdrawal_paid'
  | 'withdrawal_rejected';

export interface NotificationItemView {
  id: number;
  type: NotificationType;
  title: string;
  body: string;
  priority: NotificationPriority;
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
  onMarkRead: (notificationId: number) => void;
  onMarkAllRead: () => void;
  onLoadMore?: () => void;
  onOpenAction?: (notification: NotificationItemView) => void;
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
  onMarkRead,
  onMarkAllRead,
  onLoadMore,
  onOpenAction,
}: NotificationsPageProps) {
  const hasMore = typeof onLoadMore === 'function' && items.length < total;

  return (
    <div className={embedded ? 'space-y-4' : 'px-4 pb-20 pt-4 space-y-4'}>
      <div className="flex flex-wrap items-start justify-between gap-3">
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
  );
}
