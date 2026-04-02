# Архитектура

## Сервисы

- `api` — backend на `FastAPI`, единый источник бизнес-логики
- `bot` — Telegram-бот и webhook server
- `web` — пользовательский кабинет и Telegram Mini App
- `admin` — отдельная админка
- `worker` — фоновые задачи по платежам
- `notifications-worker` — доставка уведомлений
- `broadcast-worker` — рассылки
- `db` — PostgreSQL
- `redis` — кэш и блокировки фоновых задач

## Внешние зависимости

- `Supabase Auth` — browser auth
- `Remnawave` — выдача и продление доступа
- `YooKassa` — оплата картой
- `Telegram Bot API` — бот, Mini App, уведомления

## Базовые потоки

### Авторизация в браузере

`web` -> `Supabase Auth` -> `api /api/v1/bootstrap/me`

### Авторизация в Telegram Mini App

`web` -> `api /api/v1/auth/telegram/webapp`

### Покупка

`web` -> `api` -> платежный провайдер -> `api webhook` -> `Remnawave`

### Telegram-уведомления

`api` -> `notifications-worker` -> `bot`

## Домены в production

Обычная схема:

- `api.mydomen.net` -> `api`
- `web.mydomen.net` -> `web`
- `admin.mydomen.net` -> `admin`
- `bot.mydomen.net` -> `bot`

Все домены могут смотреть на один IP. Разводка делается либо через `CloudPub`, либо через главный `nginx` на сервере.
