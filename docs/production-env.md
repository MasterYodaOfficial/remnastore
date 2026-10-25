# Env для запуска

Есть два шаблона:

- [deploy/.env.example](/home/yoda/PycharmProjects/remnastore/deploy/.env.example) — для VDS и запуска из готовых Docker Hub образов
- [.env.example](/home/yoda/PycharmProjects/remnastore/.env.example) — для локальной работы с репозиторием

Для обычного сервера используйте именно `deploy/.env.example`, копируйте его в `.env` рядом с `compose.yml`.

`web` и `admin` тоже читают настройки из этого файла.  
Публичные `VITE_*` не зашиваются в Docker-образ заранее, а подхватываются контейнером при старте.

## Обязательные переменные

### Публичные адреса

- `WEBAPP_URL` — публичный адрес пользовательского кабинета
- `VITE_API_BASE_URL` — публичный адрес backend API
- `VITE_SUPABASE_URL` — URL проекта Supabase
- `VITE_SUPABASE_ANON_KEY` — публичный ключ Supabase
- `VITE_WEB_BRAND_NAME` — название сервиса в `document.title`
- `VITE_TELEGRAM_BOT_URL` — ссылка на Telegram-бота
- `VITE_SUPPORT_TELEGRAM_URL` — ссылка на поддержку
- `VITE_SUPPORT_EMAIL` — email поддержки для browser-версии кабинета
- `VITE_TELEGRAM_WEB_APP_FALLBACK_URL` — optional fallback URL для self-hosted копии `telegram-web-app.js`

### Telegram и внутренняя связка сервисов

- `BOT_TOKEN`
- `BOT_USERNAME`
- `BOT_USE_WEBHOOK`
- `BOT_WEBHOOK_BASE_URL`
- `BOT_WEBHOOK_PATH`
- `BOT_WEBHOOK_SECRET`
- `API_URL`
- `API_TOKEN`

Обычно внутри Docker:

```env
API_URL=http://api:8000
BOT_WEBHOOK_PATH=/bot/webhook
```

### Backend и хранилища

- `DATABASE_URL`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `REDIS_URL`
- `JWT_SECRET`

### Supabase для backend

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`

Обычно:

- `SUPABASE_URL = VITE_SUPABASE_URL`
- `SUPABASE_ANON_KEY = VITE_SUPABASE_ANON_KEY`

### Яндекс ID (опционально)

- `YANDEX_OAUTH_CLIENT_ID` — Client ID приложения Яндекс для backend-адаптера
  профиля. Без него адаптер выключен и возвращает 503.
- `VITE_YANDEX_AUTH_ENABLED` — показывает кнопку Яндекс ID только при `true`;
  по умолчанию `false`. В Docker передаётся в runtime-конфигурацию frontend.
- Client Secret настраивается только в Supabase Auth, в frontend не передаётся.
  Callback и провайдер `custom:yandex` настраиваются отдельно по
  [инструкции Яндекс ID](yandex-id.md).

Для локального Vite публичные настройки задаются в `apps/web/.env` или
окружении процесса; корневой `.env` сам по себе не включает кнопку в Vite.
Изменения production-конфигурации выполняются только по отдельной команде
на деплой.

### Remnawave

- `REMNAWAVE_API_URL`
- `REMNAWAVE_API_TOKEN`
- `REMNAWAVE_WEBHOOK_SECRET`

Дополнительно можно задать:

- `REMNAWAVE_USERNAME_PREFIX`
- `REMNAWAVE_USER_LABEL`
- `REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUID`
- `REMNAWAVE_DEFAULT_INTERNAL_SQUAD_NAME`

### YooKassa

Если используется оплата картой:

- `YOOKASSA_SHOP_ID`
- `YOOKASSA_SECRET_KEY`

### Первый администратор

Для первого запуска удобно заполнить:

- `ADMIN_BOOTSTRAP_USERNAME`
- `ADMIN_BOOTSTRAP_PASSWORD`
- `ADMIN_BOOTSTRAP_EMAIL`
- `ADMIN_BOOTSTRAP_FULL_NAME`

## Локальный запуск без публичного HTTPS

Если Telegram webhook и внешний OAuth пока не нужны:

```env
BOT_USE_WEBHOOK=false
WEBAPP_URL=http://localhost:5173
VITE_API_BASE_URL=http://localhost:8000
VITE_WEB_BRAND_NAME=QuickVPN
VITE_TELEGRAM_BOT_URL=https://t.me/your_bot_username
VITE_SUPPORT_TELEGRAM_URL=https://t.me/your_support
VITE_SUPPORT_EMAIL=support@example.com
VITE_TELEGRAM_WEB_APP_FALLBACK_URL=/vendor/telegram-web-app.js
```

## Публичный запуск через CloudPub или через свой nginx

Пример для схемы с отдельными доменами:

```env
WEBAPP_URL=https://web.mydomen.net
VITE_API_BASE_URL=https://api.mydomen.net
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_public_key
VITE_WEB_BRAND_NAME=QuickVPN
VITE_TELEGRAM_BOT_URL=https://t.me/your_bot_username
VITE_SUPPORT_TELEGRAM_URL=https://t.me/your_support
VITE_SUPPORT_EMAIL=support@example.com
VITE_TELEGRAM_WEB_APP_FALLBACK_URL=/vendor/telegram-web-app.js

BOT_USE_WEBHOOK=true
BOT_WEBHOOK_BASE_URL=https://bot.mydomen.net
BOT_WEBHOOK_PATH=/bot/webhook
```

Если используется `CloudPub`, он сам проксирует порты в HTTPS.  
Если `CloudPub` не используется, на VDS обычно ставят главный `nginx` с доменами `api/web/admin/bot` на одном IP.

## Docker Hub и теги образов

По умолчанию compose тянет публичные образы:

- `DOCKERHUB_REPOSITORY=masteryodaofficial/remnastorepy`
- `REMNASTORE_VERSION=latest` — последний опубликованный выпуск всех сервисов

Для фиксации выпуска задайте `REMNASTORE_VERSION=1.0.0`. Compose выберет
`api-1.0.0`, `bot-1.0.0`, `web-1.0.0` и `admin-1.0.0`; фоновые задачи используют
тот же образ, что API. Берите Compose из вложений соответствующего GitHub Release.

Старые `API_IMAGE_TAG`, `BOT_IMAGE_TAG`, `WEB_IMAGE_TAG`, `ADMIN_IMAGE_TAG`
поддерживаются и имеют приоритет. Удалите или закомментируйте их, чтобы версия
регулировалась одним параметром. Не заменяйте действующий `.env` шаблоном.

## Что обычно можно не менять на первом запуске

Рабочие дефолты уже есть в `.env.example` для:

- логирования
- trial
- лимита трафика trial
- стратегии сброса лимита трафика trial
- лимита устройств для trial и платных планов без `device_limit` в конфиге
- процента реферального вознаграждения
- минимальной суммы вывода
- интервалов worker-задач
- рассылок

## Источник истины

- [deploy/.env.example](/home/yoda/PycharmProjects/remnastore/deploy/.env.example) — серверный шаблон
- [.env.example](/home/yoda/PycharmProjects/remnastore/.env.example) — локальный шаблон для репозитория
- текущий документ — короткая шпаргалка по назначению переменных
