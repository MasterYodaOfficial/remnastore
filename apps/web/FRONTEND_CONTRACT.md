# Контракт frontend

Это единственный markdown-документ внутри `apps/web`, на который нужно опираться при дальнейшей frontend-разработке.

Все новые frontend-требования, ограничения, проверки, договоренности по API и прогресс нужно добавлять только сюда.

## Назначение

`apps/web` — пользовательский клиент RemnaStore для:
- браузера
- мобильного браузера
- Telegram Mini App

Frontend отвечает за:
- browser login через `Supabase Auth`
- Telegram Mini App UI и получение backend JWT
- отображение профиля, баланса, подписки и реферального раздела
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
- общая дорожная карта запуска: `docs/launch-roadmap.md`
- общий трекер запуска: `docs/launch-progress.md`
- логика связки аккаунтов: `docs/account-linking.md`

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
- `apps/web/utils/supabase/client.ts` — конфигурация Supabase клиента

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

Примечание:
- frontend checkout flow должен использовать эти endpoint'ы как источник истины
- frontend не должен заново хардкодить каталог тарифов в runtime
- если для сценария доступен только один шлюз, frontend должен сразу открывать его без дополнительного окна выбора
- в браузере покупка тарифа идет через YooKassa
- в Telegram Mini App покупка тарифа должна показывать выбор способа оплаты:
  - `Telegram Stars`, если у плана заполнен `price_stars`
  - `YooKassa` через внешний переход в браузер
- если `price_stars` не задан, в Mini App для тарифа остается только `YooKassa`
- пополнение баланса в браузере и в Mini App сейчас идет через YooKassa; в Mini App это внешний переход в браузер

`POST /api/v1/subscriptions/sync`

Назначение:
- вручную подтянуть актуальное состояние подписки из Remnawave

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

## Текущие пользовательские flow

### Browser login

- Google OAuth через `Supabase Auth`
- email/password sign in
- signup
- password reset

### Telegram Mini App login

- открытие в Telegram
- чтение `Telegram.WebApp.initData`
- backend verification
- получение backend JWT
- загрузка локального аккаунта

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

На сегодня frontend еще не переведен полностью на новый коммерческий backend flow.

Сейчас в интерфейсе заглушками остаются:
- пополнение баланса
- покупка тарифа
- вывод средств
- детальный backend-список рефералов

Если действие еще не перенесено на новый API, UI должен явно это показывать и не симулировать успешную бизнес-операцию.

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
- проверить `Browser -> Telegram`
- открыть Mini App в Telegram
- проверить Telegram login
- проверить `Telegram -> Browser`
- проверить mobile layout, safe areas и нижнюю навигацию

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

### Еще не сделано

- [ ] Реальное пополнение баланса через новый API
- [ ] Реальная покупка тарифа через новый API
- [x] Реальная активация trial через новый API
- [ ] Реальный вывод средств через новый API
- [ ] Детальный список рефералов из backend
- [ ] Экран истории операций и ledger UI
- [ ] Центр уведомлений
- [ ] FAQ и policy pages с реальным контентом
- [ ] Отдельный frontend smoke-suite или web e2e tests

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
