# Быстрый старт для web-приложения

Этот документ нужен для быстрого старта frontend-разработки и ручной проверки пользовательского интерфейса.

## Что нужно для запуска

1. Заполнить `.env` в корне проекта.
2. Настроить `Supabase Auth` для browser login.
3. Поднять Docker-стек проекта.

Основная команда:

```bash
sudo docker compose -f ops/docker/compose.yml up --build
```

## Что проверить в первую очередь

### Браузер
- вход через Google
- получение локального профиля через backend
- отображение баланса, подписки и настроек
- переходы между разделами
- mobile layout в браузере

### Telegram Mini App
- вход через Telegram WebApp
- получение backend JWT
- отображение профиля и подписки
- связка Telegram -> browser
- корректное переключение темы

## Минимальный ручной smoke test

1. Открыть приложение в браузере и выполнить login.
2. Проверить `GET /api/v1/accounts/me`.
3. Проверить экран настроек и статус связки Telegram.
4. Открыть приложение в Telegram Mini App.
5. Проверить сценарий `Telegram -> browser` и `browser -> Telegram`.
6. Проверить мобильный layout: фиксированные header/footer, safe areas, скролл контента.

## Актуальные документы

- [`../../README.md`](../../README.md) - общий вход в проект
- [`../../docs/launch-roadmap.md`](../../docs/launch-roadmap.md) - дорожная карта запуска
- [`../../docs/launch-progress.md`](../../docs/launch-progress.md) - трекер выполнения по фазам
- [`OAUTH_SETUP.md`](OAUTH_SETUP.md) - настройка browser auth

## Важно

Старые документы из эпохи `Supabase Edge Functions` и `KV Store` нельзя считать источником истины для нового backend-контура. Для разработки ориентируйся на `apps/api` и документы в `docs/`.
