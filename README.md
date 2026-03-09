# RemnaStore

RemnaStore - монорепозиторий VPN-сервиса с тремя основными клиентами:
- `API` на `FastAPI`
- `Bot` для Telegram
- `Web` / `Telegram Mini App` на `React + Vite`

## Структура репозитория

```text
apps/
  api/    FastAPI backend, модели БД, миграции, интеграции
  bot/    Telegram-бот и webhook-сервер
  web/    Браузерное приложение и Telegram Mini App
ops/
  docker/ Локальный Docker-стек
scripts/  Вспомогательные скрипты
packages/ Общие пакеты
```

## Роли сервисов

- `API` - источник истины для аккаунтов, баланса, подписок, рефералов и интеграций.
- `Bot` - канал онбординга, связки аккаунтов, уведомлений и поддержки.
- `Web` - пользовательский интерфейс для браузера и Telegram Mini App.

## Локальный запуск

### 1. Подготовить окружение

```bash
cp .env_old.example .env_old
```

Минимально заполни в `.env`:
- `BOT_TOKEN`
- `BOT_USERNAME`
- `API_URL`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_API_BASE_URL`
- `VITE_TELEGRAM_BOT_URL`
- `JWT_SECRET`
- `WEBAPP_URL`
- `REMNAWAVE_API_URL`
- `REMNAWAVE_API_TOKEN`
- `REMNAWAVE_WEBHOOK_SECRET`

Подробный production-контракт по env-переменным: [`docs/production-env.md`](docs/production-env.md)

### 2. Поднять стек

```bash
sudo docker compose -f ops/docker/compose.yml up --build
```

Сервисы:
- Web: `http://localhost:5173`
- API: `http://localhost:8000`
- Bot webhook server: `http://localhost:8080`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`

## Полезные команды

### Полный сброс с чистой БД

```bash
sudo docker compose -f ops/docker/compose.yml down --volumes --remove-orphans --rmi local
sudo docker builder prune -a -f
sudo docker compose -f ops/docker/compose.yml up --build --force-recreate
```

### Перезапуск одного сервиса

```bash
sudo docker compose -f ops/docker/compose.yml restart api
sudo docker compose -f ops/docker/compose.yml restart bot
sudo docker compose -f ops/docker/compose.yml restart web
```

## Основные документы

- [`docs/architecture.md`](docs/architecture.md) - общая архитектура системы
- [`docs/account-linking.md`](docs/account-linking.md) - логика связки Telegram и browser-аккаунтов
- [`docs/launch-roadmap.md`](docs/launch-roadmap.md) - путь до первого коммерческого запуска
- [`docs/launch-progress.md`](docs/launch-progress.md) - трекер выполнения по фазам запуска
- [`docs/production-env.md`](docs/production-env.md) - production-контракт по env-переменным
- [`docs/security-checklist.md`](docs/security-checklist.md) - базовый security checklist
- [`apps/web/FRONTEND_CONTRACT.md`](apps/web/FRONTEND_CONTRACT.md) - единый контракт frontend на русском

## Ключевые замечания

### Авторизация и связка аккаунтов

- Browser auth использует `Supabase Auth`.
- Telegram Mini App авторизуется через backend.
- Локальные записи аккаунтов живут в проектной БД.
- Browser и Telegram можно связать в один локальный аккаунт.
- Баланс и реферальные начисления хранятся в рублях как целые числа.

## Текущий стек

- Backend: `FastAPI`, `SQLAlchemy`, `Alembic`, `PostgreSQL`, `Redis`
- Bot: `aiogram`
- Frontend: `React`, `TypeScript`, `Vite`, `Tailwind`
- Auth: `Supabase Auth`

## Правило по документации

- В корне должен оставаться только минимальный набор документации.
- Подробные документы держим в `docs/`.
- Не плодим файлы вида `FINAL_SUMMARY.md`, `IMPLEMENTATION_READY.md`, `START_HERE.md` и аналогичные одноразовые отчеты.
