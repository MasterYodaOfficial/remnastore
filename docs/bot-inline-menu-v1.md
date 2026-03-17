# Inline Bot Menu V1

## Цель

Перевести Telegram-бота на лаконичный inline-first сценарий:
- у пользователя остается одна основная команда: `/start`
- после `/start` бот показывает единое menu-message с inline-кнопками
- первая строка всегда отдает быстрый вход в WebApp
- в боте остаются только короткие, понятные сценарии
- все тяжелые и детальные user flows остаются в WebApp

## Зафиксированный продуктовый scope

### Входит в `v1`

- главное меню после `/start`
- постоянная верхняя кнопка `Открыть личный кабинет`
- экран `Подписка`
- экран `Тарифы`
- экран `Рефералы`
- экран `Помощь`
- активация trial из бота, если пользователь сейчас eligible
- покупка тарифа из бота через `Telegram Stars` и `YooKassa`
- переход в WebApp для остальных действий

### Не входит в `v1`

- отдельный экран уведомлений в боте
- отдельный экран истории платежей / pending-платежей в боте
- создание заявки на вывод в боте
- детальная история рефералов и выводов в боте
- пополнение баланса в боте
- длинные conversational flows с большим количеством текстового ввода

Причина:
- уведомления уже приходят пользователю обычными сообщениями от бота
- платежная детализация и история лучше живут в WebApp
- реферальный раздел в боте должен быть обзорным, а не заменять кабинет
- пополнение баланса не относится к короткому bot-first сценарию и остается в WebApp

## UX-модель

### Общий принцип

Бот держит одно активное сообщение меню и редактирует его по inline-callback'ам.
Чат не должен засоряться навигационными сообщениями.

Повторный `/start` всегда создает новое активное menu-message и обновляет ссылку на него в Redis.
Предыдущее menu-message остается в истории чата, но его inline-кнопки деактивируются.
Если Telegram не дает отредактировать активное меню-сообщение по callback'у, бот создает новое и обновляет ссылку на него в Redis.

### Медиа-формат меню

Основное меню и экранные сообщения должны отправляться не как plain text message, а как:

- `photo`
- `caption`
- `inline keyboard`

Практическое следствие:
- если экран остается на той же картинке, бот использует `editMessageCaption`
- если экран переключается на другую картинку, бот использует `editMessageMedia`
- навигация не должна пересоздавать сообщение без необходимости

`v1` использует два бренд-ассета:
- `welcome.jpg` / `welcome.png`
- `logo.jpg` / `logo.png`

Рекомендуемое распределение:
- `welcome` для root screen после `/start`
- `logo` для внутренних экранов `Подписка`, `Тарифы`, `Рефералы`, `Помощь`

### Главное меню

Пример стартового текста:

```text
Наш веб апп

Баланс: 540 ₽
Подписка: активна до 24.03
Рефералы: 3
Доступно к выводу: 820 ₽

Выберите нужный раздел ниже.
```

Клавиатура:

```text
[ Открыть личный кабинет ]
[ Подписка ] [ Тарифы ]
[ Рефералы ] [ Помощь ]
```

Медиа:
- `welcome`

### Экран `Подписка`

Показывает:
- статус подписки
- дата окончания
- тип периода: trial / paid
- есть ли конфиг
- доступен ли пробный период

Кнопки:

```text
[ Открыть личный кабинет ]
[ Получить конфиг ]
[ Активировать пробный период ]   <- только если eligible
[ Продлить подписку ]
[ Назад ]
```

Медиа:
- `logo`

Поведение:
- `Получить конфиг` открывает `subscription_url`, если он уже есть
- `Активировать пробный период` вызывает backend-action из бота
- `Продлить подписку` переводит на экран тарифов
- если конфиг или trial недоступны, кнопка либо не показывается, либо заменяется понятным статусом в тексте

### Экран `Тарифы`

Показывает:
- список доступных тарифов
- цену в рублях
- цену в `Stars`, если она есть
- популярный тариф, если такой флаг есть

Первая стадия экрана:

```text
Тарифы

1 месяц — 299 ₽ / 90 XTR
3 месяца — 799 ₽ / 239 XTR
12 месяцев — 2490 ₽ / 749 XTR

Выберите тариф.
```

Кнопки:

```text
[ Открыть личный кабинет ]
[ 1 месяц ] [ 3 месяца ]
[ 12 месяцев ]
[ Назад ]
```

После выбора тарифа:

```text
Тариф: 3 месяца
Цена: 799 ₽
Telegram Stars: 239 XTR

В боте доступна быстрая покупка через Telegram Stars или YooKassa.
Пополнение баланса и остальные финансовые сценарии остаются в WebApp.
```

Кнопки:

```text
[ Открыть личный кабинет ]
[ Купить в Telegram ]
[ Оплатить картой ]
[ Открыть тарифы в ЛК ]
[ Назад ]
```

Медиа:
- `logo`

Правило `v1`:
- в боте поддерживается только покупка тарифа
- способы оплаты в боте:
  - `Telegram Stars`, если у тарифа есть `price_stars`
  - `YooKassa` redirect checkout
- пополнение баланса в боте не поддерживается
- если у тарифа нет `price_stars`, остается `YooKassa` и переход в WebApp

### Экран `Рефералы`

Показывает:
- реферальный код
- число приглашенных
- общие начисления
- доступно к выводу
- краткое объяснение механики

Пример текста:

```text
Рефералы

Код: ABC123
Приглашено: 3
Начислено: 1200 ₽
Доступно к выводу: 820 ₽

Награда начисляется после первой успешной платной покупки приглашенного пользователя.
Детальная статистика и вывод средств доступны в WebApp.
```

Кнопки:

```text
[ Открыть личный кабинет ]
[ Поделиться ссылкой ]
[ Открыть рефералы в ЛК ]
[ Назад ]
```

Медиа:
- `logo`

`Поделиться ссылкой`:
- бот отправляет короткое отдельное сообщение с реферальной ссылкой
- в этом сообщении можно дать кнопки `Открыть ЛК` и `Назад в меню`

### Экран `Помощь`

Показывает:
- что инструкции доступны в Telegram-канале
- что support находится в отдельной Telegram-группе / чате
- что FAQ и детали доступны в WebApp

Кнопки:

```text
[ Открыть личный кабинет ]
[ Канал с инструкциями ]
[ Поддержка ]
[ FAQ в ЛК ]
[ Назад ]
```

Медиа:
- `logo`

Требуемые ссылки:
- `BOT_HELP_TELEGRAM_URL` — канал / чат с инструкциями
- `VITE_SUPPORT_TELEGRAM_URL` — поддержка
- `WEBAPP_URL` — FAQ и остальной кабинет

## Навигационные правила

- верхняя строка клавиатуры во всех экранах: `Открыть личный кабинет`
- все экраны возвращаются к одному root-menu
- все короткие действия подтверждаются через `answerCallbackQuery`
- все тяжелые сценарии уводятся в WebApp отдельной кнопкой
- `Уведомления` и `Платежи` из меню удаляются

## Техническая архитектура

### Bot runtime

- стек: `aiogram`
- режим: polling или webhook, как и сейчас
- основной вход: `CommandStart`
- навигация: `CallbackQuery`
- хранение состояния: `Redis`

### Bot assets

Картинки должны лежать внутри bot package, чтобы одинаково работать в dev и в Docker image.

Рекомендуемый путь:

```text
apps/bot/bot/assets/menu/welcome.jpg
apps/bot/bot/assets/menu/logo.jpg
```

Почему так:
- `ops/docker/bot.Dockerfile` уже копирует весь каталог `apps/bot/bot`
- dev overlay тоже монтирует именно `apps/bot/bot`
- не нужен отдельный volume или внешний файловый сервер для двух статичных изображений

### Почему Redis нужен с первого этапа

Даже при коротком меню Redis нужен для production-уровня:
- хранить `message_id` активного menu-message
- переживать рестарт процесса бота
- защищаться от повторных callback-click'ов
- держать короткие session payload'ы между экранами
- иметь задел под FSM и более сложные flows без переписывания хранения

### Что хранится в Redis

#### Session

Ключ:

```text
bot:menu:v1:session:{telegram_id}
```

Пример payload:

```json
{
  "chat_id": 123456789,
  "menu_message_id": 321,
  "screen": "home",
  "screen_params": {},
  "updated_at": "2026-03-16T12:00:00Z"
}
```

TTL:
- `30d`
- обновляется при каждом успешном callback или `/start`

#### Lock

Ключ:

```text
bot:menu:v1:lock:{telegram_id}
```

Назначение:
- короткий lock на обработку callback
- защита от double-tap и параллельных edit-message операций

TTL:
- `3-5s`

#### Optional flow state

Ключ:

```text
bot:menu:v1:flow:{telegram_id}
```

В `v1` почти не нужен, но структура резервируется с первого дня.
Она пригодится, если позже появятся support flows, подтверждения или ввод данных.

#### Media cache

Ключ:

```text
bot:menu:v1:media:{asset_name}:{asset_hash}
```

Примеры:

```text
bot:menu:v1:media:welcome:3f8d1c2a
bot:menu:v1:media:logo:a0b51d44
```

Значение:
- `file_id` изображения в Telegram

Назначение:
- не отправлять один и тот же файл из локальной файловой системы на каждый экран
- использовать Telegram-side cached media через `file_id`
- автоматически инвалидировать кэш при замене файла

Где `asset_hash`:
- `sha256` содержимого файла или короткий hex-префикс этого хеша

Поведение:
1. бот вычисляет `asset_hash` для `welcome` или `logo`
2. ищет `file_id` в Redis
3. если `file_id` найден, использует его в `sendPhoto` / `editMessageMedia`
4. если `file_id` не найден, отправляет локальный `FSInputFile`
5. после успешной отправки сохраняет новый `file_id` в Redis

## FSM и состояния

`v1` не строится вокруг тяжелого conversational FSM, но storage должен быть Redis-backed сразу.

Практический подход:
- `MenuState` для текущего экранного контекста
- `Idle` как базовое состояние
- отдельные transient confirm states не требуются, если подтверждение можно сделать inline-кнопкой

Итого:
- FSM infrastructure включаем сразу
- реальные state transitions в `v1` остаются минимальными
- источником истины по деньгам, trial и подписке остается API, не FSM

## Media strategy

### Что принято делать “по-взрослому”

Для небольшого числа статичных брендовых изображений стандартный и практичный подход такой:

- source of truth: локальные файлы в репозитории
- runtime transport: Telegram `file_id`
- cache store: Redis
- invalidation: по `asset_hash`

Это лучше, чем сразу тащить внешний URL, потому что:
- нет лишней зависимости от CDN / object storage
- меньше сетевых hop'ов при первом рендере
- после получения `file_id` Telegram сам кэширует медиа на своей стороне
- повторные отправки и `editMessageMedia` становятся заметно дешевле

### Когда нужен URL

Внешний URL имеет смысл только если:
- картинки должны обновляться без деплоя бота
- их должен загружать не разработчик, а контент-менеджер
- нужен внешний origin вроде S3 / CDN

Для `v1` это избыточно.
Рекомендуемый вариант:
- использовать локальные ассеты
- кешировать `file_id`
- при необходимости позже вынести origin в CDN без смены экранной логики

### Требования к ассетам

Чтобы сообщения отправлялись быстро:
- предпочитать `jpg/jpeg`, если прозрачность не нужна
- держать размер файла в пределах `200-500 KB`
- не хранить оригиналы на несколько мегабайт
- держать ширину в разумных пределах, например `1280px`

Для brand-only меню:
- `welcome.jpg` — более атмосферная картинка для первого экрана
- `logo.jpg` — более легкая и универсальная для внутренних экранов

## Inline callback protocol

Нужен короткий и версионированный namespace.

Примеры:

```text
m1:nav:home
m1:nav:sub
m1:nav:plans
m1:nav:ref
m1:nav:help
m1:sub:trial
m1:sub:config
m1:plan:list
m1:plan:open:plan_1m
m1:plan:buy:plan_1m
m1:ref:share
m1:help:support
```

Правила:
- префикс `m1` фиксирует версию протокола
- callback должен укладываться в лимит Telegram `64 bytes`
- длинные данные в callback не кладем
- если экрану нужен payload, он либо короткий, либо лежит в Redis session

## Menu message lifecycle

### `/start`

1. бот валидирует пользователя и помечает его reachable
2. бот обрабатывает `link_*` и `ref_*`, если они есть
3. бот строит root screen
4. бот определяет нужный asset (`welcome`)
5. бот отправляет новое photo-message и сохраняет `message_id` в Redis
6. если предыдущее активное menu-message известно, бот снимает с него inline-клавиатуру

### Callback navigation

1. `answerCallbackQuery`
2. взять per-user lock в Redis
3. запросить свежий snapshot из API
4. определить asset для целевого экрана
5. отрендерить caption + keyboard
6. если asset тот же, обновить `caption`
7. если asset другой, обновить `media`
8. обновить session в Redis

## API-контур для бота

Бот не должен собирать меню из публичных user-JWT endpoint'ов.
Нужен отдельный internal bot contract через `API_TOKEN`.

### Минимальный набор internal endpoints

#### Dashboard snapshot

```text
GET /api/v1/internal/bot/dashboard/{telegram_id}
```

Должен вернуть агрегированный snapshot:
- account summary
- subscription summary
- referral summary
- trial eligibility summary

Этот endpoint нужен для root menu и большинства экранов.

#### Plans

```text
GET /api/v1/internal/bot/plans/{telegram_id}
```

Возвращает:
- список планов
- `price_rub`
- `price_stars`
- признаки `popular`

#### Activate trial

```text
POST /api/v1/internal/bot/subscriptions/trial
```

Payload:

```json
{
  "telegram_id": 123456789
}
```

Нужен, чтобы trial можно было запускать из бота без WebApp.

#### Create Telegram Stars invoice for plan

```text
POST /api/v1/internal/bot/payments/telegram-stars/plans/{plan_code}
```

Payload:

```json
{
  "telegram_id": 123456789
}
```

Возвращает:
- `invoice_link`
- plan summary
- amount in `XTR`

#### Create YooKassa tariff payment

```text
POST /api/v1/internal/bot/payments/yookassa/plans/{plan_code}
```

Payload:

```json
{
  "telegram_id": 123456789
}
```

Возвращает:
- `provider_payment_id`
- `confirmation_url`
- plan summary
- amount in `RUB`

Правило:
- этот endpoint создает только оплату тарифа
- top-up через YooKassa бот не создает

#### Referrals summary

Можно либо отдельным endpoint, либо частью `dashboard`.

Если отдельный:

```text
GET /api/v1/internal/bot/referrals/{telegram_id}
```

#### Help links

Это не backend-state, можно собрать на стороне бота из env.

## Источник истины по действиям

- подписка, trial, доступность trial: API
- планы и цены: API
- Telegram Stars purchase creation: API
- YooKassa tariff payment creation: API
- реферальная статистика: API
- support / help links: env/config
- session/menu state: Redis
- menu media `file_id`: Redis

## Изменения по конфигурации

### Bot env

Нужно добавить:

- `REDIS_URL`
- `BOT_MENU_SESSION_TTL_SECONDS`
- `BOT_CALLBACK_LOCK_TTL_SECONDS`
- `BOT_HELP_TELEGRAM_URL`

Опционально:

- `BOT_MENU_BUTTON_WEBAPP_ENABLED`
  - если захотим дополнительно включить постоянную Telegram `MenuButtonWebApp`

### API env

Новых обязательных env для API на этом этапе не требуется, если bot internal endpoints используют уже существующий `API_TOKEN`.

## План реализации

### Этап 1. Infra

- подключить `RedisStorage` в боте
- завести `session_store`
- завести `media_registry` / `media_cache`
- завести callback namespace
- добавить router для menu/callback flows
- реализовать единое `photo + caption + keyboard` menu-message

### Этап 2. Read-only screens

- root menu
- subscription screen
- plans list / plan detail
- referrals summary
- help screen
- переключение `welcome -> logo` через `editMessageMedia`

### Этап 3. Bot actions

- trial activation from bot
- open config from bot
- Telegram Stars invoice creation from tariff screen
- YooKassa tariff payment creation from tariff screen
- referral share message
- help links and support links

### Этап 4. Hardening

- callback dedupe
- structured logging по `telegram_id`, `screen`, `action`
- graceful recovery, если menu-message удалено
- idempotent screen refresh
- rate limit на быстрые повторные callback'и

## Ожидаемые изменения по файлам

### Bot

- `apps/bot/bot/main.py`
- `apps/bot/bot/assets/menu/welcome.jpg`
- `apps/bot/bot/assets/menu/logo.jpg`
- `apps/bot/bot/handlers/start.py`
- `apps/bot/bot/handlers/menu.py`
- `apps/bot/bot/keyboards/main.py`
- `apps/bot/bot/callbacks/menu.py`
- `apps/bot/bot/services/api.py`
- `apps/bot/bot/services/media_registry.py`
- `apps/bot/bot/services/menu_renderer.py`
- `apps/bot/bot/services/session_store.py`
- `apps/bot/bot/states/menu.py`
- `apps/bot/bot/core/config.py`

### API

- `apps/api/app/api/v1/endpoints/internal.py`
- bot-specific internal schemas
- bot-specific service layer for aggregated snapshots

### Docs

- `docs/production-env.md`
- `apps/bot/README.md`

## Open points before coding

### 1. Help channel URL

Сейчас в проекте уже есть `VITE_SUPPORT_TELEGRAM_URL`, но нет отдельной переменной для канала с инструкциями.
Для `Помощь` нужен отдельный `BOT_HELP_TELEGRAM_URL`.

### 2. Покупка из бота

Для `v1` зафиксировано:
- в боте поддерживаем только покупку тарифа
- способы оплаты тарифа в боте: `Telegram Stars` и `YooKassa`
- пополнение баланса остается только в WebApp

Это сохраняет бота компактным и не тащит в него лишние финансовые сценарии.

### 3. Реферальный раздел

Для `v1` в боте показываем только summary:
- код
- приглашенные
- начисления
- доступно к выводу

История рефералов и выводов остается в WebApp.

### 4. Media cache

Для `v1` фиксируем такой подход:
- меню живет в `photo + caption + inline keyboard`
- ассеты лежат локально в `apps/bot/bot/assets/menu`
- Telegram `file_id` кешируется в Redis по хешу файла
- URL-origin для изображений в `v1` не нужен
