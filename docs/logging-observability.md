# Logging And Observability

Этот документ фиксирует целевой контур логирования и пошаговый план внедрения, чтобы не потерять контекст между сессиями.

## Цели

- быстро находить ошибки и деградации на реальных клиентах
- иметь единый формат логов для `api`, `bot` и Python worker'ов
- не раздувать логи бесконтрольно
- не утекать в логи секретами, токенами и чувствительными payload'ами
- иметь путь от локального `docker compose logs` до production-аналитики

## Принципы

- Основной runtime-канал логов: `stdout/stderr`
- Базовая ротация: на уровне Docker, а не только внутри Python
- Файловые логи: опционально и только для локального операционного удобства
- Формат логов: `text` для локальной читаемости, `json` для production-сбора
- Корреляция: каждый HTTP request должен иметь `request_id`
- Security-first: не логируем токены, секреты, `initData`, recovery links и полные query strings
- Audit log и application log разделяются концептуально: audit trail для бизнес-событий живет отдельно и не должен подменяться обычными runtime-логами

## Фазы

### Phase 0. Foundation

Статус: завершено частично до этой сессии.

Что было:
- базовое `logging.basicConfig()` в `api` и `bot`
- чтение `LOG_LEVEL` из env для `api`
- просмотр логов через `docker compose logs`

Проблемы:
- нет структурированных логов
- нет request correlation
- нет общей конфигурации для `api`, `bot`, worker'ов
- нет контролируемой файловой ротации
- `uvicorn` логируется не полностью под нашим контролем

### Phase 1. Unified Runtime Logging

Статус: завершено.

Цель:
- получить единый production-ready baseline без внешней observability-платформы

Скоуп:
- единый logging config через `dictConfig`
- форматы `text/json`
- env-настройки для логирования и файловой ротации
- `request_id` middleware для API
- access logging в API без query string
- отдельные component names для `api`, `bot`, `payments-worker`, `notifications-worker`, `broadcast-worker`
- отключение дефолтного uvicorn access log в пользу нашего
- Docker log rotation через `max-size` и `max-file`
- документация по env и эксплуатации

Definition of done:
- все Python runtime'ы используют единый лог-контур
- API возвращает `X-Request-ID`
- в логах API видно `request_id`
- контейнерные логи не растут бесконечно
- можно включить `LOG_FORMAT=json` и получить machine-readable output

### Phase 2. Security And Audit Logging

Статус: завершено для текущего production baseline без Phase 3.

Скоуп:
- redaction/filter для секретов и опасных payload'ов
- отдельные security-события: login success/fail, provider link/unlink, sensitive admin actions
- развитие audit trail в БД для auth/balance/referral/account-linking событий
- явная политика по тому, что разрешено и запрещено логировать

Definition of done:
- security-sensitive flows пишут минимально достаточный audit trail
- runtime-логи не содержат секретов и чувствительных пользовательских данных

Что уже реализовано:

- redaction фильтр для `token`, `secret`, `password`, `init_data`, `Authorization`, `Cookie` и сходных полей
- audit logger `app.audit`
- persistent audit trail в БД через `account_event_logs`
- admin endpoint для просмотра account event history
- account timeline в admin UI с фильтрами по `event_type`, `outcome`, `source`, `request_id`
- фильтры в admin API по `event_type`, `outcome`, `source`, `request_id`
- global admin support search по `account_event_logs` с фильтрами по `request_id`, `telegram_id`, `account_id`, `actor_account_id`, `actor_admin_id`
- runtime audit events для внутренних bot endpoints и внешних webhook endpoints
- security/business audit events для:
  - `admin.login`
  - `auth.telegram_webapp`
  - `account.link.*`
  - `referral.claim`
  - `referral.intent.*`
  - `admin.balance_adjustment`
- DB-backed account events для:
  - `auth.telegram_webapp`
  - `account.link.*`
  - `admin.account_status_change`
  - `admin.balance_adjustment`
  - `admin.subscription_grant`
  - `admin.withdrawal.status_change`
  - `payment.intent.created`
  - `payment.topup.applied`
  - `payment.finalized`
  - `subscription.trial.activated`
  - `subscription.remnawave.webhook`
  - `subscription.wallet_purchase.*`
  - `subscription.direct_payment.*`
  - `withdrawal.created`
  - `referral.claim`
  - `referral.attributed`
  - `referral.intent.apply`
  - `referral.reward.granted`

Что остается:

- добить редкие admin/system lifecycle кейсы только если они реально понадобятся в support-разборе
- при необходимости расширить audit trail за пределы account-only событий в отдельные aggregated operational views
- отдельно поднять Phase 3 с внешним мониторингом и централизованным поиском

### Phase 3. Error Monitoring And Search

Статус: запланировано.

Скоуп:
- подключение `Sentry` для исключений и stack trace grouping
- централизованный поиск логов (`Loki/Grafana` или аналог)
- сохраненные фильтры по `service`, `component`, `request_id`, `account_id`, `telegram_id`
- базовые алерты на spikes ошибок и падения worker'ов

Definition of done:
- можно быстро найти инцидент по времени, пользователю или `request_id`
- ошибки агрегируются и не теряются в сыром log stream

### Phase 4. Metrics And Tracing

Статус: позже, не блокирует запуск.

Скоуп:
- health/metrics контур
- latency/error-rate метрики
- distributed tracing только если стек реально усложнится

## Phase 1 Implementation Notes

### Runtime env

Phase 1 использует такие env-переменные:

- `LOG_LEVEL`
- `LOG_FORMAT`
- `LOG_TO_FILE`
- `LOG_DIR`
- `LOG_FILE_MAX_BYTES`
- `LOG_FILE_BACKUP_COUNT`
- `ACCESS_LOG_ENABLED`

Рекомендуемые режимы:

- local dev:
  - `LOG_FORMAT=text`
  - `LOG_TO_FILE=false`
- production baseline:
  - `LOG_FORMAT=json`
  - `LOG_TO_FILE=false`
  - Docker rotation включена
- production with local error tail:
  - `LOG_FORMAT=json`
  - `LOG_TO_FILE=true`
  - `LOG_DIR` примонтирован в отдельный volume

### Что смотреть при инциденте

Минимальный operational flow:

1. Найти сервис и временное окно проблемы.
2. Для API взять `X-Request-ID` из ответа или reverse proxy.
3. Отфильтровать логи по `request_id`.
4. Если это worker flow, фильтровать по `component` и entity id.
5. Если это security/business case, дополнительно смотреть audit trail в БД.

## Краткая инструкция эксплуатации

### Где что хранится

- Технические ошибки, traceback'и и HTTP/runtime logs живут в контейнерных логах Docker.
- Business/security audit по конкретным аккаунтам живет в БД в `account_event_logs`.
- Если включить `LOG_TO_FILE=true`, дополнительно появятся локальные файлы с ротацией, но это опционально.

### Где смотреть ошибки

- API: `docker compose logs api --tail=200`
- Bot: `docker compose logs bot --tail=200`
- Workers: `docker compose logs payments-worker`, `docker compose logs notifications-worker`, `docker compose logs broadcast-worker`
- Для потока по конкретному запросу искать по `request_id`, который API возвращает в `X-Request-ID`

### Что смотреть в админке

- В карточке аккаунта:
  - timeline событий аккаунта
  - фильтры по `event_type`, `outcome`, `source`, `request_id`
  - payload события, actor и время
- Во вкладке `События`:
  - глобальный поиск по event history
  - фильтры по `request_id`, `telegram_id`, `account_id`, `actor_account_id`, `actor_admin_id`
  - быстрый переход из события в карточку аккаунта

### Когда смотреть Docker logs, а когда админку

- Docker logs:
  - traceback
  - 5xx/4xx поток запроса
  - ошибки webhook'ов, интеграций, воркеров
  - проблемы запуска контейнера
- Админка / `account_event_logs`:
  - входил ли пользователь
  - создавался ли payment intent
  - применился ли платеж
  - активировался ли trial
  - пришел ли Remnawave webhook
  - был ли referral / withdrawal / admin action

### Минимальный support flow

1. Если пользователь прислал ошибку из интерфейса, сначала взять `request_id`.
2. Найти этот `request_id` в Docker logs API.
3. Если проблема относится к аккаунту или оплате, открыть аккаунт в админке и посмотреть timeline.
4. Если неясно, кто инициировал действие, открыть глобальную вкладку `События` и отфильтровать по `request_id` или `telegram_id`.
5. Если это инфраструктурная ошибка без account context, оставаться в Docker logs.

### Что уже достаточно для старта

- для первых реальных клиентов этого контура достаточно
- ошибки не теряются сразу из-за бесконечного роста логов, потому что есть Docker rotation
- по account/payment/referral/subscription кейсам уже можно разбирать инциденты через админку без прямого доступа в БД
- основное ограничение сейчас только в том, что нет внешнего error aggregation и alerting уровня `Sentry/Loki`

## Следующий приоритет после текущего baseline

- Phase 3: `Sentry` для exception monitoring
- централизованный log search (`Loki/Grafana` или аналог)
- расширение admin/audit views поверх `account_event_logs`
