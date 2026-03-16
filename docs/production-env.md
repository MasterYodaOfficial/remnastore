# Production Env

Этот документ фиксирует production-контракт по env-переменным для всего стека `api`, `bot`, `web` и локального запуска через Docker Compose.

`.env.example` в корне проекта является production-style шаблоном:
- в нем нет локальных демо-значений вроде `localhost` без необходимости
- в нем нет неиспользуемых переменных
- его можно копировать в `.env` и дальше заполнять своими значениями

## Принцип

Один root `.env` используется как основной источник конфигурации для:
- `apps/api`
- `apps/bot`
- `apps/web`
- `apps/admin`
- локального запуска через `ops/docker/compose.yml`

Если добавляется новая обязательная env-переменная, нужно обновлять:
- `.env.example`
- этот документ

## Обязательные переменные

### Public URLs

- `WEBAPP_URL`
  - публичный URL frontend
  - используется bot и API
  - пример: `https://app.example.com`

- `VITE_API_BASE_URL`
  - публичный URL API для браузера
  - используется web runtime
  - пример: `https://api.example.com`

- `VITE_TELEGRAM_BOT_URL`
  - публичная ссылка на Telegram-бота
  - используется browser login entrypoint
  - пример: `https://t.me/your_bot_username`

- `VITE_SUPPORT_TELEGRAM_URL`
  - публичная ссылка на Telegram support-группу или support-чату
  - используется frontend settings page и support entrypoint
  - пример: `https://t.me/your_support_group`

### Bot

- `BOT_TOKEN`
  - токен Telegram-бота
  - секрет

- `BOT_USERNAME`
  - username бота без `@`
  - используется API для генерации deep-link URL

- `BOT_USE_WEBHOOK`
  - `true` для production webhook mode
  - `false` для локального polling mode без публичного HTTPS

- `BOT_WEBHOOK_BASE_URL`
  - публичная база webhook URL
  - обязательна, если `BOT_USE_WEBHOOK=true`
  - обычно совпадает с публичным доменом API

- `BOT_WEBHOOK_PATH`
  - путь webhook
  - по умолчанию: `/bot/webhook`

- `BOT_WEBHOOK_SECRET`
  - отдельный secret token для Telegram webhook
  - не должен совпадать с `BOT_TOKEN`

- `BOT_WEB_SERVER_HOST`
  - host bot web server
  - обычно `0.0.0.0`

- `BOT_WEB_SERVER_PORT`
  - port bot web server
  - обычно `8080`

- `API_URL`
  - внутренний URL API для запросов из bot
  - если bot и api в одном compose-сети, обычно `http://api:8000`

- `API_TOKEN`
  - обязательный shared secret для внутренних callback'ов bot -> api
  - используется для `POST /api/v1/webhooks/payments/telegram-stars/pre-checkout`
  - используется для `POST /api/v1/webhooks/payments/telegram-stars`
  - должен быть одинаковым в `apps/api` и `apps/bot`

### API

- `DATABASE_URL`
  - строка подключения SQLAlchemy/asyncpg
  - пример для compose-сети:
    `postgresql+asyncpg://user:password@db:5432/remnastore`

- `REDIS_URL`
  - URL Redis
  - пример для compose-сети:
    `redis://redis:6379/0`
  - используется не только для cache, но и для distributed lock фоновых payment jobs

- `JWT_SECRET`
  - секрет для backend JWT
  - обязательный секрет

- `ADMIN_JWT_ACCESS_TOKEN_EXPIRES_SECONDS`
  - TTL admin access token в секундах
  - используется только admin auth контуром

- `ADMIN_BOOTSTRAP_USERNAME`
  - логин первого администратора
  - используется только если таблица `admins` еще пуста

- `ADMIN_BOOTSTRAP_PASSWORD`
  - пароль первого администратора
  - обязателен вместе с `ADMIN_BOOTSTRAP_USERNAME`, если нужен bootstrap

- `ADMIN_BOOTSTRAP_EMAIL`
  - опциональный email bootstrap-админа

- `ADMIN_BOOTSTRAP_FULL_NAME`
  - опциональное отображаемое имя bootstrap-админа

- `SUPABASE_URL`
  - URL проекта Supabase

- `SUPABASE_ANON_KEY`
  - anon key проекта Supabase
  - не является приватным ключом, но должен соответствовать правильному проекту

- `REMNAWAVE_API_URL`
  - base URL Remnawave API

- `REMNAWAVE_API_TOKEN`
  - токен доступа к Remnawave API
  - секрет

- `REMNAWAVE_WEBHOOK_SECRET`
  - секрет для проверки входящих webhook от Remnawave
  - используется API endpoint `POST /api/v1/webhooks/remnawave`
  - должен совпадать с секретом, настроенным в панели Remnawave
  - рекомендуемый минимальный набор событий в панели Remnawave:
    - `user.expires_in_72_hours`
    - `user.expires_in_48_hours`
    - `user.expires_in_24_hours`
    - `user.expired`
  - backend уже принимает и другие scope/event combinations через общий dispatcher, но пока бизнес-логика подписочных уведомлений реализована только для этих `user.*` событий

- `REMNAWAVE_USERNAME_PREFIX`
  - короткий ASCII-prefix для `username` пользователя в панели Remnawave
  - пример: `remna`, тогда username будет выглядеть как `remna_tg123456789`
  - если не задан, backend попробует использовать `BOT_USERNAME`, затем `APP_NAME`, затем fallback `acc`

- `REMNAWAVE_USER_LABEL`
  - человекочитаемое имя бренда для `description` пользователя в панели Remnawave
  - пример: `RemnaStore`
  - если не задан, backend использует `BOT_USERNAME`, затем fallback `Remnastore`

- `REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUID`
  - предпочтительный способ указать squad для новых и обновляемых пользователей
  - если задан, backend привязывает пользователя именно к этому `Internal Squad`
  - рекомендовано для production, особенно если squad может переименовываться

- `REMNAWAVE_DEFAULT_INTERNAL_SQUAD_NAME`
  - fallback-конфиг для случаев, когда удобнее искать squad по имени
  - если `UUID` не задан и в панели только один squad, backend автоматически использует его даже при смене имени
  - если squad'ов несколько, лучше использовать `REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUID`

- `MIN_WITHDRAWAL_AMOUNT_RUB`
  - минимальная сумма пользовательской заявки на вывод реферальных средств
  - если не задана, backend использует дефолт из `apps/api/app/core/config.py`

- `PAYMENT_PENDING_TTL_SECONDS_YOOKASSA`
  - локальный fallback TTL для pending YooKassa платежей, если провайдер не вернул `expires_at`
  - нужен для cleanup stale pending payments

- `PAYMENT_PENDING_TTL_SECONDS_TELEGRAM_STARS`
  - локальный TTL для pending Telegram Stars платежей
  - без него брошенные invoice link будут висеть в `pending` бесконечно

- `PAYMENT_EXPIRE_STALE_INTERVAL_SECONDS`
  - период запуска worker job, который переводит просроченные pending платежи в `expired`

- `PAYMENT_RECONCILE_YOOKASSA_INTERVAL_SECONDS`
  - период запуска worker job сверки pending YooKassa платежей с провайдером

- `PAYMENT_RECONCILE_YOOKASSA_MIN_AGE_SECONDS`
  - минимальный возраст pending YooKassa платежа, после которого worker начинает его сверять с провайдером

- `PAYMENT_JOBS_BATCH_SIZE`
  - максимальный размер батча для payment maintenance jobs
  - влияет на память и длину транзакций worker'а

- `PAYMENT_JOB_LOCK_TTL_SECONDS`
  - TTL Redis lock для payment maintenance jobs
  - защищает от параллельного запуска одинаковой job на нескольких инстансах

- `NOTIFICATION_TELEGRAM_DELIVERY_INTERVAL_SECONDS`
  - период запуска worker job, который отправляет pending Telegram notifications

- `NOTIFICATION_JOBS_BATCH_SIZE`
  - размер батча для одного прохода notification worker
  - влияет на память, длину транзакции и число сообщений за цикл

- `NOTIFICATION_JOB_LOCK_TTL_SECONDS`
  - TTL Redis lock для notification delivery job
  - нужен, чтобы несколько worker instance не отправили одно и то же сообщение повторно

- `NOTIFICATION_TELEGRAM_MAX_ATTEMPTS`
  - максимальное число попыток доставки одного Telegram notification delivery

- `NOTIFICATION_TELEGRAM_RETRY_BASE_SECONDS`
  - базовый backoff между retry попытками Telegram delivery

- `NOTIFICATION_TELEGRAM_RETRY_MAX_SECONDS`
  - верхняя граница backoff между retry попытками Telegram delivery

- backend-каталог тарифов теперь читается из файла
  - [subscription-plans.json](/home/yoda/PycharmProjects/remnastore/apps/api/app/config/subscription-plans.json)
  - это runtime-источник истины для `GET /api/v1/payments/plans`, `POST /api/v1/payments/yookassa/plans/{plan_code}` и `POST /api/v1/payments/telegram-stars/plans/{plan_code}`
  - каждый тариф должен содержать `code`, `name`, `price_rub`, `duration_days`, `features[]`
  - `price_stars` опционален; если не задан, Mini App не предлагает оплату этого тарифа через Telegram Stars
  - `popular` опционален

- `YOOKASSA_SHOP_ID`
  - идентификатор магазина ЮKassa
  - обязателен для платежей через YooKassa

- `YOOKASSA_SECRET_KEY`
  - секретный ключ магазина ЮKassa
  - обязательный секрет

- `BOT_TOKEN`
  - обязателен также для создания invoice link через Telegram Stars

### Web

- `VITE_SUPABASE_URL`
  - обязателен
  - должен соответствовать `SUPABASE_URL`

- `VITE_SUPABASE_ANON_KEY`
  - обязателен
  - должен соответствовать `SUPABASE_ANON_KEY`

- `VITE_SUPPORT_TELEGRAM_URL`
  - рекомендуется задать явно
  - если переменная не задана, frontend не сможет открыть Telegram-support из настроек и FAQ

### Admin

- отдельный frontend `apps/admin` использует тот же `VITE_API_BASE_URL`, что и пользовательский `apps/web`
- отдельная публичная env-переменная для admin API сейчас не нужна, потому что backend-контур общий
- локальный Docker Compose поднимает admin frontend на `http://localhost:5174`

## Переменные с рабочими дефолтами

- `LOG_LEVEL`
- `JWT_ACCESS_TOKEN_EXPIRES_SECONDS`
- `ADMIN_JWT_ACCESS_TOKEN_EXPIRES_SECONDS`
- `SUPABASE_USER_CACHE_TTL_SECONDS`
- `AUTH_TOKEN_CACHE_TTL_SECONDS`
- `ACCOUNT_RESPONSE_CACHE_TTL_SECONDS`
- `PAYMENT_PENDING_TTL_SECONDS_YOOKASSA`
- `PAYMENT_PENDING_TTL_SECONDS_TELEGRAM_STARS`
- `PAYMENT_EXPIRE_STALE_INTERVAL_SECONDS`
- `PAYMENT_RECONCILE_YOOKASSA_INTERVAL_SECONDS`
- `PAYMENT_RECONCILE_YOOKASSA_MIN_AGE_SECONDS`
- `PAYMENT_JOBS_BATCH_SIZE`
- `PAYMENT_JOB_LOCK_TTL_SECONDS`
- `NOTIFICATION_TELEGRAM_DELIVERY_INTERVAL_SECONDS`
- `NOTIFICATION_JOBS_BATCH_SIZE`
- `NOTIFICATION_JOB_LOCK_TTL_SECONDS`
- `NOTIFICATION_TELEGRAM_MAX_ATTEMPTS`
- `NOTIFICATION_TELEGRAM_RETRY_BASE_SECONDS`
- `NOTIFICATION_TELEGRAM_RETRY_MAX_SECONDS`
- `TELEGRAM_INIT_DATA_TTL_SECONDS`
- `TRIAL_DURATION_DAYS`
- `MIN_WITHDRAWAL_AMOUNT_RUB`
- `YOOKASSA_API_URL`
- `YOOKASSA_VERIFY_TLS`

Их можно не менять на первом production deploy, если дефолты подходят.

## Переменные для локального Compose Postgres

Эти переменные нужны, если ты запускаешь bundled `db` сервис из `ops/docker/compose.yml` и хочешь, чтобы credentials были заданы через `.env`, а не захардкожены:
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

Они должны быть согласованы с `DATABASE_URL`.

## Что намеренно не входит в контракт

Следующие переменные сейчас не считаются частью актуального production-контракта:
- `ENV`
- `API_BASE_URL`
- `BOT_ADMIN_IDS`

Причина:
- они либо не используются в текущем runtime-коде
- либо не влияют на работу production-контура

Если одна из них понадобится снова, сначала нужно вернуть реальное использование в коде, потом документировать.

## Правила по значениям

- `BOT_WEBHOOK_SECRET` должен быть отдельной случайной строкой, а не копией `BOT_TOKEN`
- `REMNAWAVE_WEBHOOK_SECRET` должен быть отдельной случайной строкой и использоваться только для проверки webhook от Remnawave
- `YOOKASSA_SECRET_KEY` должен храниться только на backend и никогда не попадать во frontend bundle
- `API_TOKEN` должен храниться только на backend и в bot, но не во frontend bundle
- у webhook ЮKassa нет отдельного shared secret; подлинность уведомлений нужно проверять по IP-адресу отправителя и/или дополнительной сверкой статуса платежа через API
- `API_TOKEN` теперь является обязательным для Telegram Stars; без него pre-checkout и finalization callbacks из bot в api не пройдут
- `VITE_*` переменные считаются публичными и попадают во frontend bundle
- `SUPABASE_ANON_KEY` и `VITE_SUPABASE_ANON_KEY` обычно совпадают
- `SUPABASE_URL` и `VITE_SUPABASE_URL` обычно совпадают
- `API_URL` и `VITE_API_BASE_URL` обычно разные:
  - `API_URL` — внутренний адрес для bot внутри сети сервисов
  - `VITE_API_BASE_URL` — публичный адрес для браузера
- `WEBAPP_URL` должен совпадать с реальным публичным URL витрины и Telegram Mini App
- payment worker использует Redis lock, поэтому при нескольких replica `api/worker` нельзя отключать `REDIS_URL`

## Рекомендуемая topology

### Локальный и ранний stage

Для локальной машины и раннего production-like stage текущая схема считается нормальной:
- `api`: 1 container, 1 HTTP process
- `worker`: 1 container для payment maintenance jobs
- `notifications-worker`: 1 container для Telegram notification delivery
- `bot`: 1 container
- `db`: 1 container
- `redis`: 1 container

Это соответствует текущему `ops/docker/compose.yml` и достаточно для:
- разработки
- smoke-тестов
- первого ограниченного трафика

### Первый production tier

Когда проект переходит из стадии локальных проверок в реальный production-трафик, рекомендуемая схема такая:
- `api`: 1-2 container replica
- в каждом `api` container: 2 HTTP worker process
- `worker`: 1 отдельный container
- `notifications-worker`: 1 отдельный container
- `bot`: 1 container
- `db` и `redis`: managed service или отдельные выделенные инстансы

Практический смысл:
- HTTP traffic масштабируется отдельно от фоновых job
- фоновые payment jobs не конкурируют с API request handling
- Redis lock не дает нескольким worker instance одновременно выполнять один и тот же cleanup/reconcile loop

### Что именно масштабируется

`api`:
- масштабируется по HTTP latency, RPS и CPU
- это отдельный контур от background jobs
- увеличение числа HTTP worker process не заменяет отдельный `worker`

`worker`:
- сейчас предназначен для payment maintenance jobs
- на текущей реализации обычно должен быть один instance
- поднимать несколько одинаковых payment worker instance безопасно, но полезного ускорения почти не даст, потому что одинаковые job защищены Redis lock

`notifications-worker`:
- отвечает за Telegram delivery `notification_deliveries(channel=telegram)`
- на текущей реализации тоже должен быть одним instance
- несколько одинаковых instance безопасны только при рабочем Redis lock, иначе можно получить дубли отправки

`bot`:
- на текущем этапе держать одним instance
- горизонтальное масштабирование bot-контейнера имеет смысл только после появления реальной нагрузки на webhook handling и после дополнительной проверки идемпотентности всех bot-side действий

### Когда увеличивать `api`

Увеличивать HTTP workers или число `api` replica имеет смысл, когда:
- p95/p99 latency API стабильно растет
- один `api` process упирается в CPU
- запросы начинают очередиться
- видно, что API медленнее отвечает под параллельной нагрузкой

Практический порядок:
1. сначала включить 2 HTTP worker process у `api`
2. потом смотреть метрики
3. только после этого увеличивать число `api` container replica

### Когда не нужно увеличивать `worker`

Не нужно автоматически поднимать второй такой же payment worker только из-за роста общего числа пользователей.

Сначала нужно увидеть реальные симптомы:
- cleanup/reconcile не укладываются в свой интервал
- backlog старых `pending` платежей не уменьшается
- каждый проход worker постоянно выбирает полный batch
- задержка финализации платежей становится заметна пользователю

До этого момента один payment worker предпочтительнее:
- меньше operational complexity
- меньше гонок
- проще наблюдаемость

### Рекомендуемая следующая эволюция

Если фоновых задач станет больше, масштабировать лучше не копиями текущего worker, а разделением ролей:
- один scheduler/dispatcher
- отдельный `payments worker`
- отдельный `notifications worker`
- отдельный `broadcast worker`, если появятся массовые рассылки из админки

То есть сначала масштабируется HTTP слой `api`, а background layer раскладывается на специализированные worker'ы только по фактической нагрузке.

## Быстрые сценарии

### Production-like запуск через локальную машину

1. Скопировать шаблон:

```bash
cp .env.example .env
```

2. Заполнить минимум:
- `BOT_TOKEN`
- `BOT_USERNAME`
- `BOT_WEBHOOK_BASE_URL`
- `BOT_WEBHOOK_SECRET`
- `WEBAPP_URL`
- `VITE_API_BASE_URL`
- `VITE_TELEGRAM_BOT_URL`
- `VITE_SUPPORT_TELEGRAM_URL`
- `API_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `JWT_SECRET`
- `REMNAWAVE_API_URL`
- `REMNAWAVE_API_TOKEN`
- `REMNAWAVE_WEBHOOK_SECRET`

3. Запустить стек:

```bash
sudo docker compose -f ops/docker/compose.yml up --build
```

### Локальный smoke без публичного домена

Если нет публичного HTTPS и Telegram webhook не нужен, временно поставь:

```env
BOT_USE_WEBHOOK=false
WEBAPP_URL=http://localhost:5173
VITE_API_BASE_URL=http://localhost:8000
VITE_TELEGRAM_BOT_URL=https://t.me/your_bot_username
VITE_SUPPORT_TELEGRAM_URL=https://t.me/your_support_group
```

В этом режиме bot должен работать через polling, а browser/web можно гонять локально.

## Где смотреть использование

- API settings: `apps/api/app/core/config.py`
- Bot settings: `apps/bot/bot/core/config.py`
- Web env usage: `apps/web/utils/supabase/client.ts`, `apps/web/src/app/App.tsx`, `apps/web/src/app/components/LoginPage.tsx`
- Compose: `ops/docker/compose.yml`
