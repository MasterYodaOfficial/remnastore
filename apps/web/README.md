# Web-приложение

`apps/web` - пользовательское приложение для двух режимов:
- браузерное приложение
- Telegram Mini App

## Назначение

Web-клиент отвечает за:
- browser login через `Supabase Auth`
- Telegram Mini App UI
- отображение профиля, баланса, подписки и реферальной информации
- сценарии связки Telegram и browser-аккаунтов
- покупку тарифов, уведомления и пользовательские настройки

## Что уже есть

- login flow для браузера
- login flow для Telegram Mini App
- единый app shell для мобильного режима
- светлая и темная тема
- страницы профиля, тарифов, рефералов и настроек
- frontend для связки аккаунтов

## Что еще должно появиться

- полноценный purchase flow с YooKassa и Telegram Stars
- центр уведомлений
- экран истории операций
- заявки на вывод реферальных средств
- FAQ и policy pages
- отдельный admin app в `apps/admin` (не здесь)

## Текущая архитектура

- UI: `React + TypeScript + Vite`
- стили: `Tailwind` и локальные CSS-переменные темы
- browser auth: `Supabase Auth`
- бизнес-данные: backend API из `apps/api`

## Важное правило

Frontend не является источником истины для:
- баланса
- trial
- подписки
- реферальных начислений
- выводов

Все эти состояния должны приходить из backend API.

## Полезные документы

- [`../../README.md`](../../README.md)
- [`../../docs/account-linking.md`](../../docs/account-linking.md)
- [`../../docs/launch-roadmap.md`](../../docs/launch-roadmap.md)
- [`../../docs/launch-progress.md`](../../docs/launch-progress.md)
- [`OAUTH_SETUP.md`](OAUTH_SETUP.md)
- [`TELEGRAM_DEPLOYMENT.md`](TELEGRAM_DEPLOYMENT.md)
