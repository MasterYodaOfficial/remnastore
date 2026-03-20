# Mini App Runbook

## Когда открывать

- Telegram Mini App не открывается
- белый экран или вечная загрузка
- backend auth через `initData` не проходит
- linking / payments / referrals ломаются только внутри Mini App
- переходы из бота в Mini App идут не туда или открывают не тот state

## Что собрать сразу

- ссылка, из которой открывали Mini App
- устройство и платформа Telegram
- время ошибки
- account id / telegram id
- `request_id`, если API уже успел ответить ошибкой

## Где смотреть

- `./scripts/dev.sh logs api`
- `./scripts/dev.sh logs bot`
- `./scripts/dev.sh logs web`
  - только чтобы убедиться, что frontend отдается и не сломан deploy/static layer
- browser/devtools reproduction, если кейс воспроизводим в desktop Telegram или мобильном браузере

## Ключевые точки проверки

- `WEBAPP_URL` совпадает с реальным публичным URL
- `VITE_API_BASE_URL` указывает на живой API
- `VITE_TELEGRAM_BOT_URL` и `BOT_USERNAME` согласованы
- Mini App открывается только по `HTTPS`
- auth идет через `POST /api/v1/auth/telegram/webapp`
- raw `initData` не логируется и не пересылается в support-каналы

## Быстрый разбор

### 1. Открывается ли сам frontend

- если нет даже shell, проверять `web` deploy, URL и Telegram button target
- если shell есть, а данные не грузятся, идти в `api` auth/data flow

### 2. Проходит ли Telegram auth

- искать ошибки вокруг `POST /api/v1/auth/telegram/webapp`
- если Mini App падает только в Telegram, а browser app жив, это почти всегда auth/initData/config case

### 3. Ломается ли linking

- если проблема в связке browser и Telegram, смотреть account linking flow и account timeline:
  - `account.link.telegram_token.created`
  - `account.link.browser_token.created`
  - `account.link.telegram_confirmed`
  - `account.link.browser_completed`

### 4. Ломается ли покупка/выдача

- если платеж стартует, но выдача/подписка не открывается, смотреть отдельно:
  - payment flow
  - subscription snapshot
  - Remnawave/webhook path

## Безопасные действия

- можно перезапустить `web`, `api` или `bot`, если проблема в свежем deploy/config
- нельзя просить пользователя прислать сырое `initData`
- нельзя диагностировать Mini App только по frontend-состоянию без проверки `api`

## Когда эскалировать

- Mini App не открывается вообще, хотя `WEBAPP_URL` живой и `HTTPS` корректный
- auth проходит нестабильно только на части клиентов Telegram
- browser app работает, а Mini App системно расходится по данным/flow
- проблема похожа на Telegram platform regression, а не на локальный backend/frontend баг
