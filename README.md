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
  docker/ Production-oriented Docker-стек
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
cp .env.example .env
uv sync --frozen
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

### Python workflow через uv

- основной Python environment в репозитории: `.venv`
- локально запускать Python-команды нужно через `uv run ...`
- интерпретатор PyCharm вида `/home/yoda/PycharmProjects/remnastore/.venv/bin/python` нормальный, это uv-managed virtualenv
- `web` и `admin` не переводятся на `uv`, потому что это Node/Vite приложения и для них остаются `npm`/`package-lock.json`

Примеры:

```bash
uv run --no-sync python -m unittest discover -s apps/bot/tests -p 'test_*.py'
uv run --no-sync python -m unittest discover -s apps/api/tests -p 'test_*.py'
./scripts/test.sh bot
./scripts/test.sh api
./scripts/test.sh all
./scripts/pr-check.sh python
./scripts/pr-check.sh
./scripts/coverage.sh api
./scripts/coverage.sh bot --html
./scripts/coverage.sh all --fail-under 30
```

Coverage считается отдельно для:
- `apps/api/app`
- `apps/bot/bot`

HTML-отчеты сохраняются в:
- `.coverage_html/api`
- `.coverage_html/bot`

### 2. Поднять Docker-стек

```bash
./scripts/stack.sh up --build
```

Сервисы:
- Web: `http://localhost:5173`
- Admin: `http://localhost:5174`
- API: `http://localhost:8000`
- Bot webhook server: `http://localhost:8080`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`

Что важно:
- в Docker оставлен только один production-oriented stack: `ops/docker/compose.yml`
- bind-mount overlay и autoreload убраны; любое изменение кода, зависимостей или build-time env требует пересборки нужного сервиса
- `web` и `admin` внутри Docker теперь собираются как статические production-бандлы и отдаются через `nginx`
- все основные действия доступны через helper `./scripts/stack.sh help`
- Python-сервисы внутри контейнеров запускаются через `uv run --no-sync`, то есть runtime использует тот же lockfile, что и CI

## Полезные команды

### Основные Docker-команды

```bash
./scripts/stack.sh logs
./scripts/stack.sh logs api
./scripts/stack.sh ps
./scripts/stack.sh restart api
./scripts/stack.sh stop
./scripts/stack.sh down
./scripts/stack.sh rebuild
./scripts/stack.sh rebuild web admin
```

### Python quality-команды

```bash
uv run --group dev ruff check apps/api apps/bot common scripts
uv run --group dev ruff format --check apps/api apps/bot common scripts
./scripts/test.sh all
./scripts/pr-check.sh python
```

### Frontend quality-команды

```bash
cd apps/web && npm run lint && npm run test && npm run typecheck && npm run build
cd apps/web && npm run test:e2e
cd apps/admin && npm run lint && npm run test && npm run typecheck && npm run build
cd apps/admin && npm run test:e2e
./scripts/pr-check.sh web admin
./scripts/pr-check.sh --install --install-playwright
```

### Полная локальная проверка перед push / PR

`./scripts/pr-check.sh` повторяет текущие шаги из [`.github/workflows/ci.yml`](.github/workflows/ci.yml):
- `python`: `ruff check`, `ruff format --check`, `./scripts/test.sh all`
- `web`: `lint`, `test`, `typecheck`, `test:e2e`, `build`
- `admin`: `lint`, `test`, `typecheck`, `test:e2e`, `build`

Полезные режимы:

```bash
./scripts/pr-check.sh
./scripts/pr-check.sh python
./scripts/pr-check.sh web admin --install
./scripts/pr-check.sh all --install --install-playwright
```

Если хочешь запускать это автоматически перед каждым `git push`, включи репозиторный hook:

```bash
./scripts/install-git-hooks.sh
```

После этого `git push` будет вызывать `./scripts/pr-check.sh`. Если полный прогон для тебя слишком тяжелый на каждый push, оставь hook выключенным и запускай скрипт вручную перед открытием PR.

### Полный сброс с чистой БД

```bash
./scripts/stack.sh down --volumes --remove-orphans --rmi local
docker builder prune -a -f
./scripts/stack.sh rebuild
```

## Основные документы

- [`docs/architecture.md`](docs/architecture.md) - общая архитектура системы
- [`docs/account-linking.md`](docs/account-linking.md) - логика связки Telegram и browser-аккаунтов
- [`docs/broadcasts-v1.md`](docs/broadcasts-v1.md) - доменный контракт админских рассылок
- [`docs/production-env.md`](docs/production-env.md) - production-контракт по env-переменным
- [`apps/web/FRONTEND_CONTRACT.md`](apps/web/FRONTEND_CONTRACT.md) - единый контракт frontend на русском

App-level документация:

- [`apps/api/README.md`](apps/api/README.md) - краткое описание API-приложения
- [`apps/bot/README.md`](apps/bot/README.md) - краткое описание Telegram-бота
- [`packages/locales/README.md`](packages/locales/README.md) - устройство пакета локалей
- [`packages/shared/README.md`](packages/shared/README.md) - общий пакет

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

- В репозитории держим только README, контракты и поясняющие документы, которые помогают сопровождать runtime.
- Процессные трекеры, roadmap-ы, checklist-артефакты и одноразовые отчеты в репозитории не копим.
- Если документ перестал быть источником истины, его лучше удалить, чем поддерживать для вида.
