# ADR: Broadcast Runtime и UX для коммерческой админки

Дата: 2026-03-14
Статус: `Принято`

## Контекст

На текущий момент в проекте уже реализован `broadcasts v1`:
- черновики кампаний
- live estimate аудитории
- preview для `telegram` и `in_app`
- `test send` по явному списку `email` и `telegram_id`

Этого достаточно для редактора и ручной проверки, но недостаточно для коммерческой эксплуатации.
Нужен полноценный runtime контур рассылок:
- `send now`
- `schedule`
- отдельный `broadcast worker`
- `pause / resume`
- `cancel`
- журнал запусков и delivery-статусов
- аккуратный UX в web-уведомлениях

Email-канал доставки в этот этап не входит.

## Что уже считается реализованным

- `draft`-редактор и CRUD черновика
- Telegram HTML subset validation
- аудитория по сегментам
- live estimate без сохранения
- `test send` по явному списку получателей
- audit trail для `test send`

## Целевой scope следующего этапа

Следующий этап должен закрыть:
- реальный `send now`
- `scheduled launch`
- snapshot аудитории в момент фактического старта
- `fan-out worker` с доставкой по `broadcast_deliveries`
- `pause / resume`
- `cancel`
- журнал кампаний и запусков по всем рассылкам
- drill-down по delivery-статусам
- branded broadcast-card в web-списке уведомлений
- single-message photo broadcast в Telegram

## Принятые решения

### 1. Режимы запуска

Должны поддерживаться:
- `test send`
- `send now`
- `schedule`

`test send` остается отдельным контуром и не смешивается с боевыми запусками.

### 2. Таймзона

Вся логика расписания и отображения времени для broadcast runtime живет в `Europe/Moscow`.

Практическое следствие:
- scheduler считает время по Москве
- админка показывает кампании и запуски по Москве
- контейнеры можно запускать с московской таймзоной, но бизнес-логика не должна зависеть только от системного `TZ`

### 3. Snapshot аудитории

Snapshot получателей фиксируется в момент фактического старта кампании:
- для `send now` сразу при запуске
- для `schedule` в момент наступления времени запуска

Причина:
- estimate аудитории на черновике остается динамическим
- реальная доставка должна идти по неизменяемому набору получателей

### 4. Редактирование кампаний

Редактируется только `draft`.

После `schedule` или `launch` контент замораживается.
Если нужно изменить кампанию:
- создается новый черновик через `duplicate as draft`

### 5. Статусы и действия

Ожидаемые статусы:
- `draft`
- `scheduled`
- `running`
- `paused`
- `completed`
- `failed`
- `cancelled`

Правила действий:
- `draft`: доступно редактирование, `test send`, `send now`, `schedule`, отдельное удаление черновика
- `scheduled`: доступны `pause` и `cancel`
- `running`: доступны `pause` и `cancel`
- `paused`: доступны `resume` и `cancel`
- `completed`, `failed`, `cancelled`: только read-only просмотр

`cancel` не должен подменять собой удаление черновика.

### 6. Поведение pause / resume

`pause`:
- останавливает новые отправки
- не откатывает уже отправленные delivery
- `resume` продолжает с места остановки

### 7. Retry policy

Для Telegram-доставки используется:
- до 3 попыток
- backoff между попытками
- после исчерпания лимита delivery помечается как `failed`

### 8. Права доступа

Боевые действия с кампанией:
- `send now`
- `schedule`
- `pause`
- `resume`
- `cancel`

разрешены только `superuser`.

Обычный админ может:
- просматривать кампании
- работать с черновиком
- делать `test send`

### 9. Worker-модель

Должен быть отдельный сервис `broadcast-worker` в compose и production-стеке.

Worker работает в той же операционной модели, что и текущие `payments-worker` и `notifications-worker`:
- отдельный процесс
- redis lock
- периодический polling loop
- безопасная идемпотентная обработка

### 10. Журнал кампаний и запусков

Нужен отдельный журнал в админке по всем кампаниям.

Минимальный уровень:
- таблица кампаний с текущим статусом
- counters по доставке
- detail view по конкретной кампании
- drill-down по delivery-строкам

`test send` должен храниться и показываться отдельно от боевых запусков как отдельный тип run.

### 11. UX web-уведомлений

Для `broadcast` в web нужен отдельный компактный rich-card прямо внутри списка уведомлений.

Требования:
- стиль должен быть близок к Telegram
- карточка должна лаконично помещаться в общий список уведомлений
- в списке показывается одна главная CTA-кнопка
- по клику открывается detail modal
- в modal показываются фото, полный текст и все кнопки

### 12. Поведение Telegram для photo broadcast

Если `broadcast.content_type = photo`, рассылка должна уходить одним Telegram-сообщением:
- фото
- caption
- кнопки

Если текст не помещается в лимит caption, отправка должна быть отклонена заранее с ошибкой валидации.

Авто-разбиение на два сообщения не допускается.

## Технические следствия

### Данные и модель

Помимо `broadcasts` и `broadcast_deliveries`, runtime-слой должен явно хранить запуски кампаний.

Рекомендуемая сущность:
- `broadcast_runs`

Минимальная роль `broadcast_runs`:
- отделять боевые запуски от `test send`
- хранить тип запуска (`test`, `launch_now`, `scheduled_launch`)
- фиксировать snapshot и counters на уровне запуска
- давать основу для общего журнала

Без этого общий журнал и корректный audit runtime будут слишком хрупкими.

### Web notifications

Текущего plain `Notification.body` недостаточно для нормального broadcast UX.

Для `NotificationType.BROADCAST` в `payload` нужно хранить структурированные данные карточки:
- `broadcast_id`
- `content_type`
- `image_url`
- `body_html`
- `buttons`

При этом список уведомлений в web должен:
- рендерить compact preview
- использовать сокращенный текст в карточке
- открывать detail modal по structured payload

### Telegram delivery

Для `photo`-рассылок нужно перейти с паттерна:
- `sendPhoto`
- потом `sendMessage`

на паттерн:
- один `sendPhoto` с `caption`, `parse_mode` и `reply_markup`

## Что не входит в этот этап

- email-канал доставки
- повторяющиеся recurring campaigns
- A/B кампании
- callback buttons в Telegram
- сложная RBAC-модель beyond `superuser`

## Финальные уточнения от 2026-03-14

Дополнительно зафиксировано:
- боевые кампании работают только по аудитории из БД; явный список получателей остается только для `test send`
- `draft` удаляется обычным `delete` без soft-delete и архива
- в журнале первой версии сразу есть фильтры по `status`, `run type`, `channel`

## План реализации

### Шаг 1. Runtime backend
- добавить `broadcast_runs`
- добавить API для `send now`, `schedule`, `pause`, `resume`, `cancel`
- добавить snapshot получателей на старт
- добавить counters и статус-агрегации

### Шаг 2. Worker
- поднять отдельный `broadcast-worker`
- сделать scheduler loop и delivery loop
- реализовать retry/backoff и финализацию статусов

### Шаг 3. Admin UX
- переработать экран кампаний
- добавить отдельный журнал запусков
- добавить polling активных кампаний
- отделить `test send` историю от боевых запусков

### Шаг 4. Web UX
- добавить compact rich-card в списке уведомлений
- добавить detail modal
- поддержать preview фото и structured payload

### Шаг 5. Telegram quality
- отправлять `photo` broadcast одним сообщением
- валидировать caption size до запуска
