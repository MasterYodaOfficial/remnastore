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

## Тарифы и дополнительные устройства

Тарифы хранятся в PostgreSQL (`subscription_plans`) и редактируются в админке.
JSON используется только для первоначального переноса каталога миграцией.
Изменять файл в работающем контейнере больше не нужно.

В редакторе тарифа поле «Цена дополнительного устройства» задаёт стоимость
**одного дополнительного места за весь срок этого тарифа**, в рублях. Пустое
поле отключает продажу на этом тарифе. Например, можно указать 50 ₽ за 30 дней,
135 ₽ за 90 дней, 240 ₽ за 180 дней: скидка за срок задаётся этими ценами.
Это примеры, миграция не устанавливает платные цены автоматически.

В кабинете клиента, в настройках, появляется раздел «Устройства»:

- список подключённых устройств, удаление одного и сброс всех с подтверждением;
- расчёт доплаты и покупка дополнительных мест с баланса;
- выбор количества дополнительных мест для следующего продления, включая ноль;
- при оплате тарифа — количество мест, общая сумма и единая дата окончания.

Докупка оплачивается только до текущей даты окончания подписки, пропорционально
оставшемуся времени. Если клиент заранее оплатил несколько периодов, расчёт
учитывает сохранённую цену каждого периода. Уже определённые цены периодов
не меняются вслед за редактированием каталога. Для старых подписок цены
восстанавливаются по грантам подписки; при отсутствии истории продажа мест
станет доступна после обычного продления.

Отключение опции в настройках сохраняет оплаченный лимит до следующего
продления. При досрочном продлении с меньшим количеством мест лимит
уменьшается сразу, остаток фактической оплаты за удалённые места возвращается
на внутренний баланс. Перед уменьшением клиенту нужно удалить регистрации,
не помещающиеся в новый лимит. Возврат округляется вниз до рубля, доплата —
вверх. Удаление регистрации устройства само по себе не отменяет платное место.

Автоматических списаний нет. Докупка производится с рублёвого баланса;
продление тарифа вместе с местами — с баланса или через YooKassa. Telegram
Stars доступны при выборе нуля дополнительных мест. Промокод на скидку
тарифа не уменьшает цену дополнительных мест. Бонусные дни промокода входят
в общую дату окончания. Бесплатное продление администратором или промокодом
сохраняет текущий лимит без отдельного списания.

Новая миграция `20261019_hwid_devices` добавляет настройки лимита, периоды
цен и историю покупок/перерасчётов. Перед обновлением сделайте резервную копию
PostgreSQL; штатный запуск API применяет миграции Alembic. Обновляйте API,
кабинет, админку и payment worker одним релизом. Worker повторяет применение
уже оплаченного лимита после недоступности Remnawave без нового списания.
Если подписка закончилась до применения покупки мест, деньги возвращаются
на баланс. При ожидающей оплате или синхронизации изменение оплаченного
набора мест блокируется до завершения операции.

В Remnawave должен быть включён HWID Device Limit и настроен доступ API к
HWID-операциям. Интеграция использует установленный SDK Remnawave 2.x с UUID
пользователя. На реальной панели проверьте список, удаление, сброс и изменение
лимита перед включением продаж. Стандартный лимит для новых подписок берётся
из тарифа или `DEFAULT_SUBSCRIPTION_DEVICE_LIMIT`; пробный — из
`TRIAL_DEVICE_LIMIT`. Существующие ручные лимиты, включая безлимит `0`,
сохраняются при первом включении управления устройствами.

Учёт зависит от поддержки HWID приложением клиента; рекомендуемый клиент —
Happ. Удаление HWID очищает регистрацию, но не гарантирует немедленного
разрыва VPN-соединения и не блокирует устройство навсегда: при новом
обращении оно может зарегистрироваться снова. См. [документацию Remnawave](https://docs.rw/features/hwid-device-limit/).

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
VITE_SUPPORT_EMAIL=support@example.com
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

## Переход на хранение тарифов в БД

Начиная с миграции `20261019_subscription_plans`, каталог тарифов хранится в
PostgreSQL, в таблице `subscription_plans`. Управление остаётся в разделе тарифов
админки. Изменения применяются без перезапуска и сохраняются при замене контейнера.

При первом запуске миграция переносит каталог из
`/app/app/config/subscription-plans.json`. Затем приложение работает только с БД.
При последующих обновлениях тарифы из образа не перезаписывают записи в БД.

Если вы меняли тарифы в админке старой версии, сохраните JSON **до удаления или
пересоздания старого контейнера**, чтобы перенести именно ваши цены и настройки:

```bash
cd /opt/remnastore
docker compose cp api:/app/app/config/subscription-plans.json ./subscription-plans.backup.json
docker compose pull
docker compose stop api worker notifications-worker broadcast-worker
docker compose run --rm \
  -v "$PWD/subscription-plans.backup.json:/app/app/config/subscription-plans.json:ro" \
  api uv run --no-sync alembic -c alembic.ini upgrade head
docker compose up -d
```

Если каталог не менялся, достаточно обычного обновления: миграция автоматически
импортирует начальные тарифы. После перехода JSON редактировать больше не нужно.

## Перенос старой SQLite

Если нужно перетащить пользователей из старой SQLite базы, исходники проекта на сервере не нужны. В `api`-образ уже встроен migration tool.

Короткий сценарий:

```bash
cd /opt/remnastore
mkdir -p testdb_db migration-reports
cp /path/to/db_2.sqlite3 testdb_db/db_2.sqlite3
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
