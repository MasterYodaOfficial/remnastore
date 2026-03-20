# Контракт frontend

Это единственный markdown-документ внутри `apps/web`, на который нужно опираться при дальнейшей frontend-разработке.

Все новые frontend-требования, ограничения, проверки и договоренности по API нужно добавлять только сюда.

## Назначение

`apps/web` — пользовательский клиент RemnaStore для:
- браузера
- мобильного браузера
- Telegram Mini App

Frontend отвечает за:
- browser login через `Supabase Auth`
- Telegram Mini App UI и получение backend JWT
- отображение профиля, баланса, подписки и реферального раздела
- обработку входных referral-ссылок вида `?ref=<referral_code>`
- запуск flow связки browser и Telegram аккаунтов
- пользовательские настройки, тему и навигацию

Frontend не является источником истины для:
- баланса
- trial
- подписки
- реферальных начислений
- выводов
- любых денежных состояний

Все эти состояния должны приходить из backend API из `apps/api`.

## Источники истины

Основной источник истины по frontend-контракту — этот файл.

Технические источники истины:
- код frontend: `apps/web/src/app`
- backend API и схемы: `apps/api/app`
- общая архитектура проекта: `docs/architecture.md`
- логика связки аккаунтов: `docs/account-linking.md`
- production env-контракт: `docs/production-env.md`

Если этот документ расходится с кодом, нужно исправить либо код, либо этот документ в том же изменении.

Из репозитория удалены старые demo-артефакты `Supabase Edge Functions`, `KV Store`, примерочный `ACCOUNT_LINKING_EXAMPLE.tsx` и runtime-fallback `utils/supabase/info.tsx`.
Они не должны возвращаться как источник истины или рабочий runtime-контур frontend.

## Текущая архитектура

- стек: `React`, `TypeScript`, `Vite`, `Tailwind`
- browser auth: `Supabase Auth`
- backend API: `FastAPI` из `apps/api`
- режимы интерфейса: browser app, mobile browser, Telegram Mini App
- оркестрация клиентских сценариев: `apps/web/src/app/App.tsx`

Ключевые файлы:
- `apps/web/src/app/App.tsx` — входная точка, загрузка профиля, routing по вкладкам, linking flows
- `apps/web/src/app/components/LoginPage.tsx` — browser auth, email auth, recovery flow
- `apps/web/src/app/components/PlansPage.tsx` — экран тарифов
- `apps/web/src/app/components/ReferralPage.tsx` — экран рефералов
- `apps/web/src/app/components/SettingsPage.tsx` — настройки, тема, account linking actions
- `apps/web/src/app/components/NotificationsPage.tsx` — notification center
- `apps/web/src/app/components/PendingPaymentsPage.tsx` — активные и resumable оплаты
- `apps/web/src/app/components/BalanceHistoryPage.tsx` — история баланса и ledger UI
- `apps/web/src/app/lib/api-errors.ts` — code-first маппинг `error_code -> translation key`
- `apps/web/utils/supabase/client.ts` — конфигурация Supabase клиента
- `apps/web/playwright.config.ts` и `apps/web/e2e/*.e2e.ts` — browser smoke и cross-surface проверки

## Денежный контракт

Денежные поля во frontend и backend трактуются так:
- `balance` — целое число рублей
- `referral_earnings` — целое число рублей
- отображение рублевых сумм должно идти через `formatRubles`
- frontend не должен показывать дробные значения для рублевых полей

Временная совместимость:
- frontend все еще умеет прочитать legacy-поле `referral_earnings_cents` как fallback
- это нужно только на переходный период
- новые изменения должны использовать только `referral_earnings`

## Контракт по Supabase env

- `VITE_SUPABASE_URL` обязателен
- `VITE_SUPABASE_ANON_KEY` обязателен
- frontend больше не должен использовать зашитый fallback `projectId` или встроенный `publicAnonKey`
- runtime-клиент Supabase должен собираться только из явных `VITE_*` переменных

## Актуальный backend API, который использует frontend

### Авторизация

Browser flow:
- browser login и signup идут через `Supabase Auth`
- после получения сессии frontend запрашивает единый bootstrap через `GET /api/v1/bootstrap/me`

Telegram Mini App flow:
- frontend отправляет `init_data` в `POST /api/v1/auth/telegram/webapp`
- backend возвращает `{ access_token, account }`

### Bootstrap

`GET /api/v1/bootstrap/me`

Назначение:
- загрузить стартовый snapshot приложения одним запросом
- заменить стартовую последовательность `accounts/me + subscriptions/ + subscriptions/trial-eligibility`

Ожидаемые секции:
- `account`
- `subscription`
- `trial_ui`

`trial_ui` используется только для быстрой отрисовки CTA на старте.
Финальная строгая проверка eligibility всё равно происходит на `POST /api/v1/subscriptions/trial`.

### Аккаунт

`GET /api/v1/accounts/me`

Ожидаемые поля аккаунта:
- `id`
- `email`
- `display_name`
- `telegram_id`
- `username`
- `first_name`
- `last_name`
- `balance`
- `referral_code`
- `referral_earnings`
- `referrals_count`
- `referred_by_account_id`
- `has_used_trial`
- `subscription_status`
- `subscription_url`
- `subscription_expires_at`
- `subscription_is_trial`
- `trial_used_at`
- `trial_ends_at`
- `status`
- `last_login_source`

### Подписка

`GET /api/v1/subscriptions/`

Назначение:
- получить локальный snapshot текущего subscription state

Ожидаемые поля:
- `status`
- `expires_at`
- `is_active`
- `is_trial`
- `has_used_trial`
- `trial_used_at`
- `trial_ends_at`
- `days_left`
- `subscription_url`

`GET /api/v1/subscriptions/trial-eligibility`

Назначение:
- получить backend-решение, доступен ли trial сейчас
- не использовать как обязательный bootstrap-запрос на каждый старт приложения

Ожидаемые поля:
- `eligible`
- `reason`
- `has_used_trial`

`POST /api/v1/subscriptions/trial`

Назначение:
- активировать trial через backend и Remnawave

### Платежи и тарифы

`GET /api/v1/payments/plans`

Назначение:
- получить backend-каталог тарифов как источник истины

Ожидаемые поля плана:
- `code`
- `name`
- `price_rub`
- `price_stars`
- `duration_days`
- `features`
- `popular`

`POST /api/v1/payments/yookassa/topup`

Назначение:
- создать redirect payment intent YooKassa для пополнения баланса

`POST /api/v1/payments/yookassa/plans/{plan_code}`

Назначение:
- создать redirect payment intent YooKassa для прямой покупки тарифа
- backend сам определяет цену и длительность по `plan_code`

`POST /api/v1/payments/telegram-stars/plans/{plan_code}`

Назначение:
- создать invoice link Telegram Stars для прямой покупки тарифа внутри Mini App
- backend сам определяет цену в `XTR` и длительность по `plan_code`

`GET /api/v1/payments/status`

Назначение:
- получить актуальный статус уже созданной попытки оплаты для текущего аккаунта
- использовать перед повторным открытием сохраненной `confirmation_url`, чтобы не продолжать уже завершенную оплату

Query params:
- `provider`
- `provider_payment_id`

Ожидаемые поля ответа:
- `provider`
- `flow_type`
- `status`
- `amount`
- `currency`
- `provider_payment_id`
- `confirmation_url`
- `expires_at`
- `finalized_at`

`GET /api/v1/payments`

Назначение:
- получить список backend payment attempt для экрана активных оплат
- использовать с `active_only=true`, чтобы показывать только живые `created/pending/requires_action` попытки

Query params:
- `active_only`
- `limit`
- `offset`

Ожидаемые поля `items[*]`:
- `id`
- `provider`
- `flow_type`
- `status`
- `amount`
- `currency`
- `provider_payment_id`
- `plan_code`
- `description`
- `confirmation_url`
- `expires_at`
- `finalized_at`
- `created_at`

`POST /api/v1/subscriptions/wallet/plans/{plan_code}`

Назначение:
- купить тариф с внутреннего рублевого баланса без внешнего payment gateway
- backend сам проверяет достаточность баланса, идемпотентно списывает деньги и выдает подписку

Примечание:
- frontend checkout flow должен использовать эти endpoint'ы как источник истины
- frontend не должен заново хардкодить каталог тарифов в runtime
- если для сценария доступен только один шлюз, frontend должен сразу открывать его без дополнительного окна выбора
- если у пользователя хватает баланса, frontend должен добавлять способ `С баланса`
- в браузере покупка тарифа идет через `С баланса` или YooKassa, в зависимости от доступных методов
- в Telegram Mini App покупка тарифа должна показывать выбор способа оплаты:
  - `С баланса`, если рублевого баланса хватает на покупку
  - `Telegram Stars`, если у плана заполнен `price_stars`
  - `YooKassa` через внешний переход в браузер
- если `price_stars` не задан, в Mini App для тарифа остаются `С баланса` и/или `YooKassa`
- пополнение баланса в браузере и в Mini App сейчас идет через YooKassa; в Mini App это внешний переход в браузер
- frontend может локально сохранять активную попытку оплаты, но перед повторным открытием должен сверять ее через `GET /api/v1/payments/status`
- `expires_at`, `cancelled`, `expired` и `failed` считаются dead-state: такую попытку нельзя продолжать, нужно создавать новую
- если backend уже видит `succeeded`, frontend не должен создавать дублирующую оплату; сначала нужно обновить bootstrap/account state
- для `Telegram Stars` callback `openInvoice` можно использовать как быстрый клиентский сигнал, но источником истины по финальному статусу остается backend

`POST /api/v1/subscriptions/sync`

Назначение:
- вручную подтянуть актуальное состояние подписки из Remnawave

Кнопка `Получить конфиг`:
- frontend больше не рендерит собственный экран выдачи конфигов
- нужно использовать уже доступный `subscription_url` из bootstrap/subscription state
- в обычном браузере кнопка должна открывать `subscription_url` в новом окне
- в Telegram Mini App кнопка должна делать переход в этом же окне через `window.location.assign(subscription_url)`
- если `subscription_url` пустой, кнопка должна быть disabled или показывать понятную ошибку

### История баланса

`GET /api/v1/ledger/entries`

Назначение:
- получить историю денежных операций для отдельного `ledger` / `balance history` экрана

Query params:
- `limit`
- `offset`

Ожидаемые поля ответа:
- `items`
- `total`
- `limit`
- `offset`

Ожидаемые поля `items[*]`:
- `id`
- `entry_type`
- `amount`
- `currency`
- `balance_before`
- `balance_after`
- `reference_type`
- `reference_id`
- `comment`
- `created_at`

### Рефералы

`POST /api/v1/referrals/claim`

Назначение:
- привязать входной `referral_code` к текущему аккаунту
- endpoint вызывается только после авторизации, если frontend ранее зафиксировал `?ref=<code>`

Тело запроса:
- `referral_code`

Семантика:
- `created=true` означает новую успешную атрибуцию
- `created=false` означает безопасный повтор того же claim
- self-referral должен блокироваться
- после первой успешной платной покупки claim должен блокироваться

`GET /api/v1/referrals/summary`

Назначение:
- получить реальный referral summary для вкладки рефералов

Ожидаемые поля:
- `referral_code`
- `referrals_count`
- `referral_earnings`
- `available_for_withdraw`
- `effective_reward_rate`
- `items`

Ожидаемые поля `items[*]`:
- `referred_account_id`
- `display_name`
- `created_at`
- `reward_amount`
- `status`

Примечание:
- `available_for_withdraw` должен трактоваться как backend-рассчитанный остаток для заявки на вывод
- frontend не должен пытаться вычислять его сам из `referral_earnings`

### Выводы

`POST /api/v1/withdrawals`

Назначение:
- создать пользовательскую заявку на вывод реферальных средств

Тело запроса:
- `amount`
- `destination_type` (`card` или `sbp`)
- `destination_value`
- `user_comment` опционально

Семантика:
- backend сам проверяет минимальную сумму вывода
- backend сам проверяет реальный `available_for_withdraw`
- при успешном создании заявки backend сразу резервирует сумму и уменьшает доступный баланс

`GET /api/v1/withdrawals`

Назначение:
- получить список текущих и прошлых заявок на вывод

Ожидаемые поля ответа:
- `items`
- `total`
- `limit`
- `offset`
- `available_for_withdraw`
- `minimum_amount_rub`

Ожидаемые поля `items[*]`:
- `id`
- `amount`
- `destination_type`
- `destination_value`
- `user_comment`
- `admin_comment`
- `status`
- `reserved_ledger_entry_id`
- `released_ledger_entry_id`
- `processed_at`
- `created_at`
- `updated_at`

### Уведомления

`GET /api/v1/notifications`

Назначение:
- получить список уведомлений для user notification center

Query params:
- `limit`
- `offset`
- `unread_only`

Ожидаемые поля ответа:
- `items`
- `total`
- `limit`
- `offset`
- `unread_count`

Ожидаемые поля `items[*]`:
- `id`
- `type`
- `title`
- `body`
- `priority`
- `payload`
- `action_label`
- `action_url`
- `read_at`
- `is_read`
- `created_at`

Текущие типы уведомлений, которые уже может вернуть backend:
- `payment_succeeded`
- `payment_failed`
- `subscription_expiring`
- `subscription_expired`
- `referral_reward_received`
- `withdrawal_created`

Текущие payload-варианты:
- `payment_succeeded`:
  - `payment_id`
  - `amount`
  - `currency`
  - `provider`
  - `plan_code`
  - `flow_type`
- `payment_failed`:
  - `payment_id`
  - `amount`
  - `currency`
  - `provider`
  - `plan_code`
  - `flow_type`
  - `status`
- `referral_reward_received`:
  - `reward_id`
  - `reward_amount`
  - `currency`
  - `referred_account_id`
  - `subscription_grant_id`
- `subscription_expiring`:
  - `days_left`
  - `expires_at`
  - `remnawave_event`
  - `remnawave_user_uuid`
- `subscription_expired`:
  - `expires_at`
  - `remnawave_event`
  - `remnawave_user_uuid`
- `withdrawal_created`:
  - `withdrawal_id`
  - `amount`
  - `destination_type`

`GET /api/v1/notifications/unread-count`

Назначение:
- получить число непрочитанных уведомлений отдельно от полного списка

Ожидаемые поля ответа:
- `unread_count`

`POST /api/v1/notifications/{id}/read`

Назначение:
- пометить одно уведомление как прочитанное

Семантика:
- повторный вызов безопасен
- backend должен возвращать уже обновленное уведомление

`POST /api/v1/notifications/read-all`

Назначение:
- пометить все непрочитанные уведомления текущего аккаунта как прочитанные

Ожидаемые поля ответа:
- `updated_count`

### Связка аккаунтов

`POST /api/v1/accounts/link-telegram`

Назначение:
- запуск flow `Browser -> Telegram`

Ожидаемый ответ:
- `link_url`
- `link_token`
- `expires_in_seconds`

`POST /api/v1/accounts/link-browser`

Назначение:
- запуск flow `Telegram -> Browser`

Ожидаемый ответ:
- `link_url`
- `link_token`
- `expires_in_seconds`

`POST /api/v1/accounts/link-browser-complete`

Назначение:
- завершение flow `Telegram -> Browser` после OAuth login в браузере

Тело запроса:
- `link_token`

### Ошибки и transport contract

Для user-facing business endpoint-ов frontend ожидает backend-ответ вида:
- `detail`
- `error_code`
- `error_params` опционально

Текущий обязательный code-first contract уже действует для критичных `web` flow:
- `POST /api/v1/auth/telegram/webapp`
- `POST /api/v1/subscriptions/trial`
- `POST /api/v1/promos/quote`
- `POST /api/v1/promos/redeem`
- `POST /api/v1/payments/yookassa/topup`
- `POST /api/v1/payments/yookassa/plans/{plan_code}`
- `POST /api/v1/payments/telegram-stars/plans/{plan_code}`
- `POST /api/v1/subscriptions/wallet/plans/{plan_code}`
- `POST /api/v1/referrals/claim`
- `POST /api/v1/notifications/{id}/read`
- `POST /api/v1/withdrawals`
- `POST /api/v1/accounts/link-telegram`
- `POST /api/v1/accounts/link-browser`
- `POST /api/v1/accounts/link-browser-complete`

Правила frontend:
- сначала парсить `error_code/error_params` через `parseApiErrorPayload`
- потом маппить `error_code -> translation key`
- `detail` использовать только как fallback для legacy или пока не покрытых endpoint-ов
- для параметризованных ошибок вроде `minimum_amount` использовать `error_params`, а не парсинг строки

## Текущие пользовательские flow

### Browser login

- Google OAuth через `Supabase Auth`
- email/password sign in
- signup
- password reset
- если URL содержит `?ref=<code>`, frontend должен сохранить код локально до завершения авторизации
- если пользователь с сохраненным `?ref=<code>` жмет `Войти через Telegram`, ссылка на бота должна строиться как `VITE_TELEGRAM_BOT_URL?start=ref_<code>`
- после успешной авторизации frontend должен попытаться вызвать `POST /api/v1/referrals/claim`

### Telegram Mini App login

- открытие в Telegram
- чтение `Telegram.WebApp.initData`
- backend verification
- получение backend JWT
- загрузка локального аккаунта
- если пользователь пришел в бота по deep-link `start=ref_<code>`, bot должен:
  - сохранить pending referral intent на backend по `telegram_id`
  - показать WebApp-кнопку с URL вида `WEBAPP_URL?ref=<code>`
- если при входе был входной `?ref=<code>`, после получения токена frontend должен так же вызвать `POST /api/v1/referrals/claim`
- backend `POST /api/v1/auth/telegram/webapp` должен также пытаться автоприменить pending referral intent, если он был сохранен ранее

### Referral sharing UI

- в интерфейсе должны быть две отдельные user action:
  - `Скопировать ссылку` -> копирует browser link вида `https://app...?ref=<code>`
  - `Поделиться в Telegram` -> открывает Telegram share flow c bot deep-link `t.me/<bot>?start=ref_<code>`
- frontend не должен смешивать эти два transport в одну кнопку

### Browser -> Telegram

- browser-пользователь жмет привязку Telegram
- frontend вызывает `POST /api/v1/accounts/link-telegram`
- пользователь уходит в бота по `link_url`
- bot/backend завершает связку через confirm endpoint

### Telegram -> Browser

- пользователь в Telegram Mini App жмет привязку browser account
- frontend вызывает `POST /api/v1/accounts/link-browser`
- пользователь проходит browser OAuth
- frontend завершает flow через `POST /api/v1/accounts/link-browser-complete`

## Ограничения текущего состояния

На сегодня frontend уже переведен на новый backend flow для browser auth, Telegram auth, trial, promo, topup, plan purchase, notifications, withdrawals и account linking.

Главные текущие ограничения уже другие:
- `apps/web/src/app/App.tsx` все еще остается крупным orchestration-файлом и требует дальнейшей декомпозиции
- новый `error_code/error_params` contract гарантирован для критичных `web` flow, но еще не для всех backend endpoint-ов
- `POST /api/v1/notifications/read-all` по-прежнему не рассматривается как отдельный code-first endpoint и живет на общем fallback transport
- единый верхнеуровневый `LocaleProvider` / locale-state contract пока не оформлен
- Telegram Mini App dependency stack все еще живет на `@telegram-apps/*`; отдельная миграция на более стабильный maintenance track не входит в runtime-contract этого файла

## Локальные правила разработки

- по умолчанию делай адаптивную верстку через `flex` и `grid`
- абсолютное позиционирование используй только там, где без него нельзя
- не держи критичную бизнес-логику во frontend
- если компонент разрастается, выноси helper-логику и подкомпоненты отдельно
- mobile browser и Telegram Mini App должны выглядеть согласованно
- все цвета должны идти через CSS-переменные темы
- при переключении темы должен обновляться весь интерфейс, а не отдельные блоки
- избегай жестко захардкоженных цветов без необходимости
- учитывай `safe-area` на мобильных устройствах
- нижняя навигация не должна перекрывать контент
- header и footer в мобильном shell должны оставаться закрепленными
- основной скролл должен происходить внутри контентной области
- кнопки должны иметь понятные action-oriented подписи
- если действие имеет финансовые последствия, его состояние и результат должны приходить с backend

## Конфигурация окружения

Frontend использует такие переменные:
- `VITE_API_BASE_URL` — base URL backend API
- `VITE_SUPABASE_URL` — URL проекта Supabase
- `VITE_SUPABASE_ANON_KEY` — публичный anon key Supabase
- `VITE_TELEGRAM_BOT_URL` — ссылка на Telegram-бота для browser login entrypoint
- `VITE_SUPPORT_TELEGRAM_URL` — ссылка на support chat / support contact action

## OAuth и Telegram setup

### Browser auth через Supabase

- основной social provider: `Google`
- можно использовать email/password и password reset
- нельзя использовать `service_role` или `sb_secret_*` на фронте
- redirect URL должны быть явно перечислены без лишних wildcard

Для локальной разработки обычно нужны:
- `http://localhost:5173`
- `http://localhost:5173/`

### Telegram Mini App

- Mini App должен открываться по `HTTPS`
- нельзя доверять `initDataUnsafe` как источнику истины
- валидация `initData` должна идти на backend
- backend JWT после Telegram login должен приходить только из backend

## Запуск и ручная проверка

Локальный запуск frontend:

```bash
cd apps/web
npm install
npm run dev
```

Сборка:

```bash
cd apps/web
npm run build
```

Минимальный ручной smoke test:
- открыть browser app
- пройти login через Google или email
- проверить загрузку `GET /api/v1/bootstrap/me`
- проверить баланс, профиль и настройки
- проверить `notifications`, `pending payments` и `balance history`
- проверить topup через YooKassa redirect
- проверить покупку тарифа через `wallet` и/или payment provider
- проверить создание `withdrawal request`
- проверить promo apply / redeem
- проверить `Browser -> Telegram`
- открыть Mini App в Telegram
- проверить Telegram login
- проверить `Telegram -> Browser`
- проверить mobile layout, safe areas и нижнюю навигацию

Автоматический baseline smoke:

```bash
cd apps/web
npm run lint
npm run test
npm run typecheck
npm run test:e2e
```

Текущий `Playwright` smoke покрывает:
- browser auth
- notifications
- promo deep link
- topup redirect flow
- withdrawal request flow
- `Browser -> Telegram`
- `Telegram -> Browser`
- cross-surface linking sanity check

## Frontend progress

### Уже сделано

- [x] Browser login через `Supabase Auth`
- [x] Email/password auth и password reset UI
- [x] Telegram Mini App auth через backend
- [x] Flow `Browser -> Telegram`
- [x] Flow `Telegram -> Browser`
- [x] Отображение `balance` в рублях без дробной части
- [x] Отображение `referral_earnings` в рублях без дробной части
- [x] Светлая и темная тема
- [x] Mobile shell с фиксированными header и bottom navigation
- [x] Базовые экраны: профиль, тарифы, рефералы, настройки
- [x] Реальное пополнение баланса через новый API
- [x] Реальная покупка тарифа через новый API
- [x] Реальная активация trial через новый API
- [x] Реальный вывод средств через новый API
- [x] Детальный referral summary из backend
- [x] Центр уведомлений
- [x] Экран активных оплат
- [x] Экран истории операций и ledger UI
- [x] FAQ и policy pages с реальным контентом
- [x] Экран выдачи подписки и конфигов через `subscription_url`
- [x] Отдельный frontend smoke-suite / `Playwright` e2e tests
- [x] Code-first обработка `error_code/error_params` для критичных `web` flow

### Еще не сделано

- [ ] Явный `LocaleProvider` / единый locale-state contract
- [ ] Дальнейшая декомпозиция `App.tsx` на более узкие runtime-модули

## Атрибуция и внешние материалы

Во frontend могли использоваться материалы и подходы из:
- `shadcn/ui`
- `Unsplash`

Перед production-публикацией нужно отдельно проверить лицензии, удалить лишние демонстрационные материалы и не тащить в релиз временные ассеты.

## Правило обновления

Если меняется:
- API-контракт
- naming денежных полей
- auth flow
- linking flow
- список обязательных экранов
- правила верстки и темы
- статус frontend-задач

нужно обновлять этот файл в том же изменении.
