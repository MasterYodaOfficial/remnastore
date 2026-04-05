# Запуск на VDS

## Что нужно заранее

- VDS с Linux
- установленный `Docker Engine` и `docker compose plugin`
- домены или `CloudPub`
- доступы к `Supabase`, `Remnawave`, `Telegram Bot`, `YooKassa`

## Что скачивать на сервер

Для деплоя нужны только два файла из GitHub-репозитория `MasterYodaOfficial/remnastore`:

- `deploy/compose.yml`
- `deploy/.env.example`

Сами Docker-образы берутся из Docker Hub `masteryodaofficial/remnastorepy`.

## Первый запуск

```bash
mkdir -p /opt/remnastore && cd /opt/remnastore
curl -fsSL -o compose.yml https://raw.githubusercontent.com/MasterYodaOfficial/remnastore/main/deploy/compose.yml
curl -fsSL -o .env.example https://raw.githubusercontent.com/MasterYodaOfficial/remnastore/main/deploy/.env.example
cp .env.example .env
nano .env
docker compose pull
docker compose up -d
docker compose logs -f
```

## Как это работает

- `compose.yml` описывает стек сервисов
- `.env` хранит ваши домены, ключи и токены
- `docker compose pull` тянет готовые образы из Docker Hub
- `docker compose up -d` запускает или обновляет контейнеры

`git clone` для обычного деплоя не нужен.

## Что обязательно заполнить в `.env`

Минимум:

- `BOT_TOKEN`
- `BOT_USERNAME`
- `JWT_SECRET`
- `API_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `REMNAWAVE_API_URL`
- `REMNAWAVE_API_TOKEN`
- `REMNAWAVE_WEBHOOK_SECRET`

Остальное берите из [production-env.md](/home/yoda/PycharmProjects/remnastore/docs/production-env.md) и шаблона [deploy/.env.example](/home/yoda/PycharmProjects/remnastore/deploy/.env.example).

## Публичные адреса

Пример для схемы с отдельными доменами:

```env
WEBAPP_URL=https://web.mydomen.net
VITE_API_BASE_URL=https://api.mydomen.net
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_public_key
VITE_WEB_BRAND_NAME=QuickVPN
VITE_TELEGRAM_BOT_URL=https://t.me/your_bot_username
VITE_SUPPORT_TELEGRAM_URL=https://t.me/your_support
VITE_TELEGRAM_WEB_APP_FALLBACK_URL=/vendor/telegram-web-app.js

BOT_USE_WEBHOOK=true
BOT_WEBHOOK_BASE_URL=https://bot.mydomen.net
BOT_WEBHOOK_PATH=/bot/webhook
```

## Если используется свой nginx

В standalone `compose.yml` сервисы по умолчанию слушают только `127.0.0.1`, поэтому их удобно проксировать главным `nginx` на сервере.

Готовый пример: [nginx-vhost-example.md](/home/yoda/PycharmProjects/remnastore/docs/nginx-vhost-example.md)

## Если используется CloudPub

Тогда вместо своего `nginx` и своих сертификатов можно пробрасывать такие порты:

- `8000` -> `api-*.cloudpub.ru`
- `5173` -> `web-*.cloudpub.ru`
- `5174` -> `admin-*.cloudpub.ru`
- `8080` -> `bot-*.cloudpub.ru`

Для этого обычно достаточно оставить дефолтные `API_PORT`, `WEB_PORT`, `ADMIN_PORT`, `BOT_PORT`.

## Обновление проекта

```bash
cd /opt/remnastore
curl -fsSL -o compose.yml https://raw.githubusercontent.com/MasterYodaOfficial/remnastore/main/deploy/compose.yml
docker compose pull
docker compose up -d
docker compose logs -f --tail=100
```

Если в новой версии появились дополнительные переменные:

```bash
curl -fsSL -o .env.example https://raw.githubusercontent.com/MasterYodaOfficial/remnastore/main/deploy/.env.example
```

После этого перенесите недостающие ключи в свой `.env`.

## Перенос старой SQLite

Если нужно перетащить пользователей из старой SQLite базы, исходники проекта на сервере не нужны. В `api`-образ уже встроен migration tool.

Короткий сценарий:

```bash
cd /opt/remnastore
mkdir -p old_db migration-reports
cp /path/to/db_2.sqlite3 old_db/db_2.sqlite3
docker compose --profile tools run --rm legacy-migration --dry-run \
  --output-json /app/migration-reports/legacy-dry-run.json
docker compose --profile tools run --rm legacy-migration --apply-db \
  --output-json /app/migration-reports/legacy-apply.json
```

Если сервер слабый, уменьшайте размер батча:

```bash
docker compose --profile tools run --rm legacy-migration --apply-db \
  --db-batch-size 100 \
  --output-json /app/migration-reports/legacy-apply.json
```

Подробно: [legacy-migration.md](/home/yoda/PycharmProjects/remnastore/docs/legacy-migration.md)

## Фиксация конкретного релиза

Если не хотите всегда тянуть `latest`, задайте в `.env`:

```env
API_IMAGE_TAG=api-<tag>
BOT_IMAGE_TAG=bot-<tag>
WEB_IMAGE_TAG=web-<tag>
ADMIN_IMAGE_TAG=admin-<tag>
```

## Что проверить после запуска

```bash
cd /opt/remnastore
docker compose ps
docker compose logs -f api
docker compose logs -f web
```

Минимум должно открываться:

- `https://web...`
- `https://admin...`
- `https://api.../api/v1/health`
