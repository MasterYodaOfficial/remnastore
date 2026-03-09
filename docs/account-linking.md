# Связка аккаунтов

## Цель

Связать browser auth и Telegram auth в один локальный аккаунт без дублирования баланса, рефералов и подписок.

## Источник истины

- Таблица `accounts` в локальной БД - источник истины для состояния аккаунта.
- `Supabase` используется только для browser-аутентификации, но не хранит бизнес-состояние.
- Вся логика связки и merge выполняется на backend.

## Поддерживаемые сценарии

### Browser -> Telegram

Используется, когда пользователь уже вошел через browser auth и хочет привязать Telegram.

1. Браузер вызывает `POST /api/v1/accounts/link-telegram`.
2. API возвращает deep link в Telegram-бота с одноразовым токеном.
3. Пользователь открывает ссылку в боте.
4. Бот получает `/start link_*` и вызывает `POST /api/v1/accounts/link-telegram-confirm`.
5. API валидирует токен и привязывает Telegram к browser-аккаунту или выполняет merge двух локальных записей.

### Telegram -> Browser

Используется, когда пользователь уже вошел в Telegram Mini App и хочет привязать Google/email browser auth.

1. Telegram Mini App вызывает `POST /api/v1/accounts/link-browser`.
2. API возвращает browser URL с `link_token`.
3. Пользователь завершает Google/email login в браузере.
4. Browser frontend вызывает `POST /api/v1/accounts/link-browser-complete`.
5. API валидирует токен и merge-ит browser account в Telegram account.

## Правила

- Токены связки типизированы, одноразовые и имеют TTL.
- Связка browser-аккаунта по email допускается только для подтвержденной email identity.
- Merge аккаунтов выполняется только на backend, не на клиенте.
- В Telegram Mini App приоритетен Telegram-аватар.
- В браузере, если `Supabase` отдает Google avatar, UI использует его.

## Важные эндпоинты

### Защищенные

- `POST /api/v1/accounts/link-telegram`
- `POST /api/v1/accounts/link-browser`
- `POST /api/v1/accounts/link-browser-complete`
- `GET /api/v1/accounts/me`

### Для бота

- `POST /api/v1/accounts/link-telegram-confirm`
- `POST /api/v1/accounts/link-browser-confirm`

Примечание: `link-browser-confirm` сохранен только как legacy failure path. Основной сценарий завершения browser-link должен происходить в браузере после OAuth login.

## Обязательная конфигурация

### API

- `BOT_USERNAME`
- `WEBAPP_URL`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `JWT_SECRET`

### Bot

- `BOT_TOKEN`
- `API_URL`
- `API_TOKEN` опционально, пока только как задел под будущую server-to-server авторизацию
- `BOT_USE_WEBHOOK` и webhook-настройки, если используется webhook mode

### Web

- `VITE_API_BASE_URL`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_TELEGRAM_BOT_URL`

## Основные файлы реализации

- `apps/api/app/services/account_linking.py`
- `apps/api/app/services/accounts.py`
- `apps/api/app/api/v1/endpoints/accounts.py`
- `apps/api/app/api/v1/endpoints/linking.py`
- `apps/bot/bot/handlers/start.py`
- `apps/web/src/app/App.tsx`
- `apps/web/src/app/components/SettingsPage.tsx`

## Замечания по поддержке

- Держи этот файл сфокусированным на flow и инвариантах.
- Не создавай отдельные `FINAL_SUMMARY`, `IMPLEMENTATION_READY`, `QUICKSTART`, `START_HERE` документы для той же фичи.
- Если меняется важное продуктовое правило, обновляй этот файл и при необходимости `README`.
