# Incident Runbooks

Этот каталог фиксирует операционные runbook-документы по типовым инцидентам первого production baseline.

Когда использовать:

- пользователь пишет, что платеж не дошел
- внешний webhook не пришел или отклоняется
- Telegram Mini App не открывается или не авторизует
- бот не отвечает или ломает deep-link / payment flow
- заявки на вывод зависли, обработались неверно или не отражаются в UI

Общий порядок первых минут:

1. Зафиксировать время, окружение, аккаунт, `request_id`, payment id, withdrawal id или другой идентификатор кейса.
2. Посмотреть Docker logs нужного сервиса через `./scripts/dev.sh logs <service>` или production-логирование.
3. Если кейс связан с конкретным аккаунтом, открыть account timeline в admin UI и глобальную вкладку `События`.
4. Не править БД вручную, пока не понятна причина и не проверены идемпотентность, ledger и audit trail.

Доступные runbooks:

- [`payments.md`](./payments.md) — платеж не дошел, завис в `pending`, провайдер подтвердил оплату, а продукт нет
- [`webhooks.md`](./webhooks.md) — входящие webhook/callback проблемы по YooKassa, Telegram Stars и Remnawave
- [`mini-app.md`](./mini-app.md) — Telegram Mini App не открывается, белый экран, auth/linking/payment issues
- [`bot.md`](./bot.md) — бот не отвечает, не работает `/start`, deep-link, кнопка Mini App или internal callback flow
- [`withdrawals.md`](./withdrawals.md) — создание, резерв, ручная обработка и уведомления по заявкам на вывод

Связанные документы:

- [`../logging-observability.md`](../logging-observability.md)
- [`../security-checklist.md`](../security-checklist.md)
- [`../production-env.md`](../production-env.md)
- [`../rollback-checklist.md`](../rollback-checklist.md)
