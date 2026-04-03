# RemnaStore

GitHub: `https://github.com/MasterYodaOfficial/remnastore`  
Docker Hub: `masteryodaofficial/remnastorepy`

## Что это

RemnaStore состоит из нескольких сервисов:

- `api` — backend на `FastAPI`
- `bot` — Telegram-бот
- `web` — пользовательский кабинет и Telegram Mini App
- `admin` — админка
- `worker`, `notifications-worker`, `broadcast-worker` — фоновые задачи

## Быстрый запуск на VDS

Для сервера не нужен `git clone`. Достаточно скачать два deployment-файла, заполнить `.env` и запустить `docker compose`.

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

Что обязательно заполнить в `.env`:

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

Подробно: [docs/deploy-vds.md](/home/yoda/PycharmProjects/remnastore/docs/deploy-vds.md)

## Обновление на VDS

```bash
cd /opt/remnastore
curl -fsSL -o compose.yml https://raw.githubusercontent.com/MasterYodaOfficial/remnastore/main/deploy/compose.yml
docker compose pull
docker compose up -d
docker compose logs -f --tail=100
```

Если в новой версии появились дополнительные переменные, скачайте свежий `.env.example` и перенесите недостающие ключи в свой `.env`.

## Перенос старой SQLite

Если у вас есть старая база `db_2.sqlite3`, ее не нужно импортировать вручную через локальный Python. Migration tool уже лежит внутри `api`-образа и запускается как разовый compose-сервис.

```bash
cd /opt/remnastore
mkdir -p old_db migration-reports
cp /path/to/db_2.sqlite3 old_db/db_2.sqlite3
docker compose --profile tools run --rm legacy-migration --dry-run \
  --output-json /app/migration-reports/legacy-dry-run.json
docker compose --profile tools run --rm legacy-migration --apply-db \
  --output-json /app/migration-reports/legacy-apply.json
```

Если VDS слабый, запускайте импорт меньшими батчами:

```bash
docker compose --profile tools run --rm legacy-migration --apply-db \
  --db-batch-size 100 \
  --output-json /app/migration-reports/legacy-apply.json
```

Подробно: [docs/legacy-migration.md](/home/yoda/PycharmProjects/remnastore/docs/legacy-migration.md)

## Локальный запуск из исходников

Этот режим нужен для разработки и проверки текущей ветки.

```bash
git clone https://github.com/MasterYodaOfficial/remnastore.git
cd remnastore
cp .env.example .env
docker compose --env-file .env \
  -f ops/docker/compose.yml \
  -f ops/docker/compose.local.yml \
  up -d --build
```

Подробно: [docs/local-run.md](/home/yoda/PycharmProjects/remnastore/docs/local-run.md)

## Локально через CloudPub

CloudPub проксирует локальные порты в публичные HTTPS-адреса. Это удобно для:

- Google OAuth
- Supabase email redirect
- Telegram webhook
- проверки с телефона

Обычно используют такую схему:

- `api-*.cloudpub.ru` -> `8000`
- `web-*.cloudpub.ru` -> `5173`
- `admin-*.cloudpub.ru` -> `5174`
- `bot-*.cloudpub.ru` -> `8080`

Подробно: [docs/local-run.md](/home/yoda/PycharmProjects/remnastore/docs/local-run.md)

## Если на сервере свой nginx

Нормальная схема:

- один IP
- отдельные домены `api.mydomen.net`, `web.mydomen.net`, `admin.mydomen.net`, `bot.mydomen.net`
- главный `nginx` на сервере слушает `80/443`
- `nginx` проксирует на локальные порты Docker-стека `8000/5173/5174/8080`

Готовый пример: [docs/nginx-vhost-example.md](/home/yoda/PycharmProjects/remnastore/docs/nginx-vhost-example.md)

## Полезные документы

- [docs/deploy-vds.md](/home/yoda/PycharmProjects/remnastore/docs/deploy-vds.md) — запуск и обновление на VDS
- [docs/local-run.md](/home/yoda/PycharmProjects/remnastore/docs/local-run.md) — локальный запуск и CloudPub
- [docs/nginx-vhost-example.md](/home/yoda/PycharmProjects/remnastore/docs/nginx-vhost-example.md) — пример главного nginx на одном IP
- [docs/production-env.md](/home/yoda/PycharmProjects/remnastore/docs/production-env.md) — что заполнять в `.env`
- [docs/legacy-migration.md](/home/yoda/PycharmProjects/remnastore/docs/legacy-migration.md) — разовый перенос старой SQLite
- [docs/architecture.md](/home/yoda/PycharmProjects/remnastore/docs/architecture.md) — краткая схема сервисов
