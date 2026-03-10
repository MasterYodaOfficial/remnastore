# Production Env

Этот документ фиксирует production-контракт по env-переменным для всего стека `api`, `bot`, `web` и локального запуска через Docker Compose.

`.env.example` в корне проекта является production-style шаблоном:
- в нем нет локальных демо-значений вроде `localhost` без необходимости
- в нем нет неиспользуемых переменных
- его можно копировать в `.env` и дальше заполнять своими значениями

## Принцип

Один root `.env` используется как основной источник конфигурации для:
- `apps/api`
- `apps/bot`
- `apps/web`
- локального запуска через `ops/docker/compose.yml`

Если добавляется новая обязательная env-переменная, нужно обновлять:
- `.env.example`
- этот документ

## Обязательные переменные

### Public URLs

- `WEBAPP_URL`
  - публичный URL frontend
  - используется bot и API
  - пример: `https://app.example.com`

- `VITE_API_BASE_URL`
  - публичный URL API для браузера
  - используется web runtime
  - пример: `https://api.example.com`

- `VITE_TELEGRAM_BOT_URL`
  - публичная ссылка на Telegram-бота
  - используется browser login entrypoint
  - пример: `https://t.me/your_bot_username`

### Bot

- `BOT_TOKEN`
  - токен Telegram-бота
  - секрет

- `BOT_USERNAME`
  - username бота без `@`
  - используется API для генерации deep-link URL

- `BOT_USE_WEBHOOK`
  - `true` для production webhook mode
  - `false` для локального polling mode без публичного HTTPS

- `BOT_WEBHOOK_BASE_URL`
  - публичная база webhook URL
  - обязательна, если `BOT_USE_WEBHOOK=true`
  - обычно совпадает с публичным доменом API

- `BOT_WEBHOOK_PATH`
  - путь webhook
  - по умолчанию: `/bot/webhook`

- `BOT_WEBHOOK_SECRET`
  - отдельный secret token для Telegram webhook
  - не должен совпадать с `BOT_TOKEN`

- `BOT_WEB_SERVER_HOST`
  - host bot web server
  - обычно `0.0.0.0`

- `BOT_WEB_SERVER_PORT`
  - port bot web server
  - обычно `8080`

- `API_URL`
  - внутренний URL API для запросов из bot
  - если bot и api в одном compose-сети, обычно `http://api:8000`

- `API_TOKEN`
  - зарезервирован для будущей server-to-server авторизации bot -> api
  - сейчас bot его отправляет, но API его не валидирует
  - пока можно оставлять пустым

### API

- `DATABASE_URL`
  - строка подключения SQLAlchemy/asyncpg
  - пример для compose-сети:
    `postgresql+asyncpg://user:password@db:5432/remnastore`

- `REDIS_URL`
  - URL Redis
  - пример для compose-сети:
    `redis://redis:6379/0`

- `JWT_SECRET`
  - секрет для backend JWT
  - обязательный секрет

- `SUPABASE_URL`
  - URL проекта Supabase

- `SUPABASE_ANON_KEY`
  - anon key проекта Supabase
  - не является приватным ключом, но должен соответствовать правильному проекту

- `REMNAWAVE_API_URL`
  - base URL Remnawave API

- `REMNAWAVE_API_TOKEN`
  - токен доступа к Remnawave API
  - секрет

- `REMNAWAVE_WEBHOOK_SECRET`
  - секрет для проверки входящих webhook от Remnawave
  - используется API endpoint `POST /api/v1/webhooks/remnawave`
  - должен совпадать с секретом, настроенным в панели Remnawave

- `YOOKASSA_SHOP_ID`
  - идентификатор магазина ЮKassa
  - обязателен для платежей через YooKassa

- `YOOKASSA_SECRET_KEY`
  - секретный ключ магазина ЮKassa
  - обязательный секрет

### Web

- `VITE_SUPABASE_URL`
  - обязателен
  - должен соответствовать `SUPABASE_URL`

- `VITE_SUPABASE_ANON_KEY`
  - обязателен
  - должен соответствовать `SUPABASE_ANON_KEY`

## Переменные с рабочими дефолтами

- `LOG_LEVEL`
- `JWT_ACCESS_TOKEN_EXPIRES_SECONDS`
- `SUPABASE_USER_CACHE_TTL_SECONDS`
- `AUTH_TOKEN_CACHE_TTL_SECONDS`
- `ACCOUNT_RESPONSE_CACHE_TTL_SECONDS`
- `TELEGRAM_INIT_DATA_TTL_SECONDS`
- `TRIAL_DURATION_DAYS`
- `YOOKASSA_API_URL`
- `YOOKASSA_VERIFY_TLS`

Их можно не менять на первом production deploy, если дефолты подходят.

## Переменные для локального Compose Postgres

Эти переменные нужны, если ты запускаешь bundled `db` сервис из `ops/docker/compose.yml` и хочешь, чтобы credentials были заданы через `.env`, а не захардкожены:
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

Они должны быть согласованы с `DATABASE_URL`.

## Что намеренно не входит в контракт

Следующие переменные сейчас не считаются частью актуального production-контракта:
- `ENV`
- `API_BASE_URL`
- `BOT_ADMIN_IDS`

Причина:
- они либо не используются в текущем runtime-коде
- либо не влияют на работу production-контура

Если одна из них понадобится снова, сначала нужно вернуть реальное использование в коде, потом документировать.

## Правила по значениям

- `BOT_WEBHOOK_SECRET` должен быть отдельной случайной строкой, а не копией `BOT_TOKEN`
- `REMNAWAVE_WEBHOOK_SECRET` должен быть отдельной случайной строкой и использоваться только для проверки webhook от Remnawave
- `YOOKASSA_SECRET_KEY` должен храниться только на backend и никогда не попадать во frontend bundle
- у webhook ЮKassa нет отдельного shared secret; подлинность уведомлений нужно проверять по IP-адресу отправителя и/или дополнительной сверкой статуса платежа через API
- `VITE_*` переменные считаются публичными и попадают во frontend bundle
- `SUPABASE_ANON_KEY` и `VITE_SUPABASE_ANON_KEY` обычно совпадают
- `SUPABASE_URL` и `VITE_SUPABASE_URL` обычно совпадают
- `API_URL` и `VITE_API_BASE_URL` обычно разные:
  - `API_URL` — внутренний адрес для bot внутри сети сервисов
  - `VITE_API_BASE_URL` — публичный адрес для браузера
- `WEBAPP_URL` должен совпадать с реальным публичным URL витрины и Telegram Mini App

## Быстрые сценарии

### Production-like запуск через локальную машину

1. Скопировать шаблон:

```bash
cp .env.example .env
```

2. Заполнить минимум:
- `BOT_TOKEN`
- `BOT_USERNAME`
- `BOT_WEBHOOK_BASE_URL`
- `BOT_WEBHOOK_SECRET`
- `WEBAPP_URL`
- `VITE_API_BASE_URL`
- `VITE_TELEGRAM_BOT_URL`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `JWT_SECRET`
- `REMNAWAVE_API_URL`
- `REMNAWAVE_API_TOKEN`
- `REMNAWAVE_WEBHOOK_SECRET`

3. Запустить стек:

```bash
sudo docker compose -f ops/docker/compose.yml up --build
```

### Локальный smoke без публичного домена

Если нет публичного HTTPS и Telegram webhook не нужен, временно поставь:

```env
BOT_USE_WEBHOOK=false
WEBAPP_URL=http://localhost:5173
VITE_API_BASE_URL=http://localhost:8000
VITE_TELEGRAM_BOT_URL=https://t.me/your_bot_username
```

В этом режиме bot должен работать через polling, а browser/web можно гонять локально.

## Где смотреть использование

- API settings: `apps/api/app/core/config.py`
- Bot settings: `apps/bot/bot/core/config.py`
- Web env usage: `apps/web/utils/supabase/client.ts`, `apps/web/src/app/App.tsx`, `apps/web/src/app/components/LoginPage.tsx`
- Compose: `ops/docker/compose.yml`
