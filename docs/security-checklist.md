# Чеклист безопасности

Дата актуализации: 2026-03-08

Документ фиксирует базовый security baseline для проекта `RemnaStore` с текущей архитектурой:

- `Supabase Auth` для browser auth
- `FastAPI` как основной backend бизнес-логики
- локальная БД проекта как source of truth для аккаунтов, баланса, подписок и рефералов
- `Telegram Mini App` + bot
- `Redis` как внутренний cache/auxiliary слой

## 1. Нормально ли, что `https://<project-ref>.supabase.co/auth/v1/user` отвечает JSON-ошибкой

Да. Это штатное поведение.

- `Supabase Auth` endpoint является публичным API endpoint, а не web-страницей
- он не обязан отдавать HTML-заглушку или `404`
- корректная защита строится не на сокрытии URL, а на:
  - `apikey`
  - user JWT
  - `RLS`
  - rate limits
  - captcha / anti-abuse

Что не нужно делать:

- пытаться маскировать hosted `Supabase` auth endpoints под `404`
- считать безопасность достигнутой только потому, что URL "неочевидный"

Что нужно делать:

- держать бизнес-эндпоинты только на своем backend
- не светить `service_role` / secret keys
- включить `RLS` и ограничители на auth flow

## 2. Критично сделать сейчас

### 2.1 Ключи и секреты

- Использовать на фронте только `publishable` key или legacy `anon` key
- Не использовать `service_role` или `sb_secret_*` в браузере ни при каких условиях
- Хранить backend secrets только в серверных env
- Удалить захардкоженные ключи из кода, если они где-либо остались
- Настроить регулярную ротацию:
  - `JWT_SECRET`
  - bot token
  - SMTP credentials
  - Supabase server-side keys

### 2.2 Supabase Auth

- Оставить в `Supabase` только реально используемые auth providers
- Выключить неиспользуемые providers
- Настроить точные `Redirect URLs`, без широких wildcard-исключений без необходимости
- Включить `Confirm email`, если продукт допускает подтверждение почты
- Настроить разумную password policy:
  - minimum length
  - required character classes при необходимости
- Включить captcha / bot protection для signup, password reset, magic link, если auth открыт в интернет
- Настроить rate limits в Auth config:
  - email sent
  - verify
  - otp
  - token refresh

### 2.3 Своя БД и backend

- Все чувствительные бизнес-операции выполнять только через `FastAPI`
- Не держать критичную логику в публично доступных browser-side запросах к сторонним endpoints
- Не доверять данным, пришедшим с фронта, если они влияют на:
  - баланс
  - trial
  - подписку
  - реферальные начисления
  - вывод средств
- Проверять user identity на backend по валидному `Supabase` access token
- Среднесрочно перевести проверку user token с удаленного `auth/v1/user` на локальную проверку JWT через `JWKS`

### 2.4 Row Level Security

- Включить `RLS` на всех таблицах, доступных через Supabase
- Проверить, что политики для `anon` и `authenticated` минимальны
- Не выдавать таблицам “широкий read/write” только потому, что проект “пока внутренний”
- Для административных действий использовать только server-side доступ

### 2.5 Telegram Mini App

- Принимать на backend только `Telegram.WebApp.initData`
- Никогда не доверять `initDataUnsafe` как источнику истины
- Валидировать подпись `initData` на backend
- Ограничить TTL для `initData`
- Применять referral/start параметр только один раз при первом создании аккаунта
- Не логировать сырое `initData` целиком в production

### 2.6 Почта и recovery flow

- Подключить свой SMTP, не полагаться на дефолтную отправку для production
- Настроить SPF / DKIM / DMARC для домена отправителя
- Проверить шаблоны:
  - signup confirmation
  - password recovery
  - email change
- Проверить, что recovery links работают только на разрешенных `Redirect URLs`
- Не логировать recovery links, token hashes и полные query strings

### 2.7 Логи и observability

- Не писать в логи:
  - access tokens
  - refresh tokens
  - `service_role` / secret keys
  - `initData`
  - recovery links
  - email verification links
- Добавить audit logging на:
  - login success/fail
  - password reset request
  - password changed
  - provider link/unlink
  - trial activation
  - balance mutation
  - referral application

## 3. Важно для production

### 3.1 Browser security

- Принудительный `HTTPS` на основном домене
- `HSTS` на reverse proxy / CDN
- Жесткая `CSP`, особенно если SPA хранит auth state в browser storage
- Не использовать `dangerouslySetInnerHTML`, если нет сильной причины и sanitation
- Минимизировать сторонние скрипты
- Включить `Referrer-Policy`, `X-Content-Type-Options`, `Permissions-Policy`

Примечание:

- в текущем SPA-теке XSS особенно опасен, потому что browser auth state живет в клиенте
- значит XSS hardening здесь обязателен, а не “nice to have”

### 3.2 Redis

- Не публиковать `Redis` наружу в интернет
- Держать `Redis` только во внутренней сети
- Если Redis не локальный, включить auth/TLS
- Хранить в Redis только краткоживущие данные
- Использовать короткие TTL для кэша auth/account mappings
- Не превращать Redis в source of truth для денег, подписок и рефералов

### 3.3 Docker и инфраструктура

- Не экспонировать `Postgres` и `Redis` наружу без необходимости
- Разделить dev/staging/prod secrets
- Проверить, что `.env` не попадает в публичные артефакты и репозиторий
- Ограничить доступ к Docker host и CI secrets
- Настроить backup/restore для БД и регулярно проверять восстановление

### 3.4 Админские доступы

- Ограничить круг людей с доступом к:
  - Supabase project settings
  - production env
  - SMTP
  - bot token
  - payment settings
- Включить MFA для админских аккаунтов везде, где возможно
- Разделять обычный доступ разработчика и production-admin доступ

## 4. Что стоит сделать следующим этапом

### 4.1 Auth hardening

- Перейти с legacy `anon` / `service_role` на `publishable` / `secret` keys, если hosted Supabase это уже позволяет в вашем окружении
- Включить `security_update_password_require_reauthentication`, если UX это допускает
- Рассмотреть `sessions_inactivity_timeout`
- Рассмотреть `sessions_single_per_user`, если нужен строгий контроль сессий
- Рассмотреть MFA хотя бы для административных сценариев

### 4.2 Abuse protection

- Rate limit на backend endpoints:
  - `/auth/telegram/webapp`
  - `/accounts/me`
  - email login
  - forgot password
  - trial activation
  - top-up / withdraw
- Bot protection на signup и reset flows
- Alerting на аномалии:
  - всплеск password reset
  - всплеск failed login
  - всплеск account creation
  - много trial activation с одного IP / device fingerprint

### 4.3 Account linking

- Не делать auto-merge аккаунтов только по email
- Привязку `Telegram <-> browser auth` делать только через явный подтвержденный flow
- Любое слияние аккаунтов делать идемпотентно и с audit trail

## 5. Чек перед запуском в production

- [ ] На фронте нет `service_role` / `sb_secret_*`
- [ ] На backend нет лишнего логирования токенов
- [ ] `RLS` включен везде, где данные доступны через Supabase APIs
- [ ] Неиспользуемые auth providers выключены
- [ ] Настроены точные `Redirect URLs`
- [ ] Настроен свой SMTP
- [ ] Проверены email templates
- [ ] Telegram `initData` валидируется на backend
- [ ] Реферальный код применяется только один раз
- [ ] `Redis` не торчит наружу
- [ ] `Postgres` не торчит наружу
- [ ] Включен HTTPS
- [ ] Настроены rate limits
- [ ] Настроены backup и проверка restore
- [ ] Есть журнал security-sensitive событий
- [ ] Доступ к Supabase/SMTP/prod env ограничен по ролям

## 6. Рекомендуемый порядок работ для этого проекта

1. Довести перенос бизнес-эндпоинтов со старых Supabase Functions на `FastAPI`
2. Перейти на локальную валидацию `Supabase JWT` по `JWKS`
3. Проверить и ужесточить `RLS`
4. Включить captcha и auth rate limits
5. Подключить production SMTP и доменную почту
6. Внедрить audit log для auth/balance/referral событий
7. Сделать формальный production review по secrets, ports и backups

## 7. Официальные ссылки

- Supabase API keys: https://supabase.com/docs/guides/api/api-keys
- Supabase Auth overview: https://supabase.com/docs/guides/auth
- Supabase RLS: https://supabase.com/docs/guides/database/postgres/row-level-security
- Supabase client session initialization: https://supabase.com/docs/reference/javascript/auth-initialize
- Supabase auth config fields and rate limits: https://supabase.com/docs/reference/api/updates-a-projects-auth-config
- Telegram Mini Apps: https://core.telegram.org/bots/webapps
