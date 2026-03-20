# Контракт Broadcasts V1

## Цель

`broadcasts` это отдельный админский домен для массовых кампаний.
Он не смешивается с событийными `notifications`.

Следующий согласованный этап развития `broadcasts` зафиксирован в этом документе.

В `v1` входит:
- создание и редактирование черновика из админки
- оценка аудитории до запуска без сохранения черновика
- реальный `test send` по явному списку получателей
- единый контент-контракт для `in_app` и `telegram`
- схема данных с запасом под будущие scheduler, worker и delivery stats

В `v1` пока не входит:
- отложенный запуск
- реальный fan-out worker доставки
- pause / resume
- email-канал доставки

## Доменная модель

### `broadcasts`

Одна кампания в статусе черновика или запущенной рассылки.

Основные поля:
- `name`: внутреннее название для операторов
- `title`: пользовательский заголовок для in-app и Telegram
- `body_html`: Telegram-compatible HTML subset, общий для обоих каналов
- `content_type`: `text` или `photo`
- `image_url`: обязателен для `photo`
- `channels`: любое сочетание `in_app`, `telegram`
- `buttons`: до 3 URL-кнопок для Telegram
- `audience`: текущее правило аудитории
- `status`: `draft`, `scheduled`, `running`, `paused`, `completed`, `failed`, `cancelled`

Операционные поля:
- `estimated_total_accounts`
- `estimated_in_app_recipients`
- `estimated_telegram_recipients`
- `scheduled_at`, `launched_at`, `completed_at`, `cancelled_at`
- `last_error`

### `broadcast_deliveries`

Строка доставки на аккаунт и канал для уже запущенной кампании.

В `v1` таблица создается заранее, чтобы следующий этап мог использовать ее без новой перекройки модели.

## Контракт контента

Канонический формат текста: Telegram HTML subset.

Разрешенные теги в `v1`:
- `b`, `strong`
- `i`, `em`
- `u`, `ins`
- `s`, `strike`, `del`
- `code`
- `pre`
- `blockquote`
- `tg-spoiler`
- `a href="..."`

Примечания:
- emoji хранятся как обычный Unicode
- произвольный HTML запрещен
- кнопки хранятся отдельно от `body_html`
- в `v1` кнопки только URL-based, без callback buttons

## Контракт аудитории

Значения `audience.segment`:
- `all`
- `active`
- `with_telegram`
- `paid`
- `expired`

Поле `audience.exclude_blocked`:
- по умолчанию `true`
- полностью заблокированные аккаунты должны исключаться из большинства кампаний

На стадии черновика аудитория остается динамической и используется только для estimate.
На стадии запуска worker обязан сделать неизменяемый snapshot получателей на момент старта.

## API-контракт

Админские endpoint'ы:
- `GET /api/v1/admin/broadcasts`
- `POST /api/v1/admin/broadcasts`
- `GET /api/v1/admin/broadcasts/{broadcast_id}`
- `PUT /api/v1/admin/broadcasts/{broadcast_id}`
- `POST /api/v1/admin/broadcasts/estimate`
- `POST /api/v1/admin/broadcasts/{broadcast_id}/test-send`

`POST /api/v1/admin/broadcasts/estimate` нужен для live estimate в редакторе.
Он не создает запись в `broadcasts` и не пишет audit log.

`POST /api/v1/admin/broadcasts/{broadcast_id}/test-send` делает реальную отправку
по последней сохраненной версии черновика и пишет `admin_action_log`.

Payload создания и обновления:
- `name`
- `title`
- `body_html`
- `content_type`
- `image_url`
- `channels`
- `buttons`
- `audience`

Payload live estimate:
- `channels`
- `audience`

Payload test send:
- `emails`
- `telegram_ids`
- `comment`
- `idempotency_key`

Правила test send:
- нужен уже сохраненный `broadcast_id`
- `email` используется только как ключ поиска существующего локального аккаунта
- если email не резолвится в локальный аккаунт, такой target помечается как `unresolved`
- `telegram_id` может принадлежать локальному аккаунту или быть внешним Telegram-only адресатом вне БД
- для внешнего `telegram_id` доступна только Telegram-доставка
- несохраненные правки из редактора в test send не участвуют

Ответы создания и обновления включают:
- нормализованный broadcast payload
- текущий статус
- estimates аудитории по каналам
- timestamps
- `created_by_admin_id` и `updated_by_admin_id`

Ответ live estimate включает:
- нормализованные `channels`
- нормализованную `audience`
- `estimated_total_accounts`
- `estimated_in_app_recipients`
- `estimated_telegram_recipients`

Ответ test send включает:
- агрегированные счетчики `sent / partial / failed / skipped`
- число резолвленных локальных аккаунтов
- число прямых Telegram-only адресатов
- число созданных `in_app notifications`
- число успешных Telegram target'ов
- детальный результат по каждому target

## Стратегия доставки

Что уже работает в test send:
- для локального аккаунта канал `in_app` создает обычный `notification`
- для локального аккаунта канал `telegram` отправляется ботом напрямую на `account.telegram_id`
- для внешнего `telegram_id` вне БД отправка идет напрямую в Telegram без создания аккаунта и без `in_app`
- результат пишется в `admin_action_log` и идемпотентен по `idempotency_key`

Когда появится launch:
- `in_app` доставка должна разворачиваться в обычные `notifications`
- `telegram` доставка должна идти через отдельный `broadcast worker`
- каждый получатель и канал должны трекаться в `broadcast_deliveries`
- launch обязан зафиксировать snapshot аудитории на момент запуска

## UX-контракт админки

Экран `v1` должен давать:
- список кампаний
- редактор черновика
- выбор каналов
- выбор аудитории
- редактор Telegram URL-кнопок
- визуальный preview для `telegram` и `in_app`
- live recipient estimates без сохранения черновика
- реальный test send по списку `email` и `telegram_id`

Будущий UX:
- отправить сейчас / запланировать
- pause / resume
- progress stats и drill-down по ошибкам
