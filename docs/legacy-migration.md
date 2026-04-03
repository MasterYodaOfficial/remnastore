# Перенос старой SQLite

Сценарий рассчитан на обычный серверный каталог `/opt/remnastore`, где лежат только:

- `compose.yml`
- `.env`
- `old_db/db_2.sqlite3`

Исходники проекта на сервере не нужны. Скрипт миграции встроен в `api`-образ и запускается как разовый `docker compose` сервис `legacy-migration`.

## Что подготовить

1. Поднимите новый стек:

```bash
cd /opt/remnastore
docker compose pull
docker compose up -d
```

2. Положите старую SQLite базу сюда:

```bash
mkdir -p /opt/remnastore/old_db /opt/remnastore/migration-reports
cp /path/to/db_2.sqlite3 /opt/remnastore/old_db/db_2.sqlite3
```

По умолчанию migration tool ищет файл именно по пути `./old_db/db_2.sqlite3`.

## Проверка без записи

```bash
cd /opt/remnastore
docker compose --profile tools run --rm legacy-migration \
  --dry-run \
  --output-json /app/migration-reports/legacy-dry-run.json
```

Отчет появится на хосте в каталоге `./migration-reports`.

## Импорт в новую PostgreSQL

```bash
cd /opt/remnastore
docker compose --profile tools run --rm legacy-migration \
  --apply-db \
  --output-json /app/migration-reports/legacy-apply.json
```

`DATABASE_URL` брать отдельно не нужно: сервис читает его из вашего `.env`.

Для слабого VDS лучше сразу уменьшать размер батча, например до `100`:

```bash
cd /opt/remnastore
docker compose --profile tools run --rm legacy-migration \
  --apply-db \
  --db-batch-size 100 \
  --output-json /app/migration-reports/legacy-apply.json
```

Скрипт печатает прогресс по фазам и батчам прямо в консоль.

## Проверка состояния Remnawave

Только отчет, без изменений:

```bash
cd /opt/remnastore
docker compose --profile tools run --rm legacy-migration \
  --report-remnawave \
  --output-json /app/migration-reports/remnawave-report.json
```

Синхронизация панели:

```bash
cd /opt/remnastore
docker compose --profile tools run --rm legacy-migration \
  --sync-remnawave \
  --output-json /app/migration-reports/remnawave-sync.json
```

Если панель большая или сервер слабый, можно уменьшить batch size:

```bash
cd /opt/remnastore
docker compose --profile tools run --rm legacy-migration \
  --sync-remnawave \
  --remnawave-batch-size 50 \
  --output-json /app/migration-reports/remnawave-sync.json
```

## Если файл называется иначе

```bash
cd /opt/remnastore
docker compose --profile tools run --rm legacy-migration \
  --legacy-db /app/old_db/my-legacy.sqlite3 \
  --dry-run
```

## Что важно

- Сначала делайте `--dry-run`.
- Потом `--apply-db`.
- Только после этого имеет смысл запускать `--report-remnawave` или `--sync-remnawave`.
- Это разовый сервис. Он не должен работать постоянно и не поднимается обычной командой `docker compose up -d`.
