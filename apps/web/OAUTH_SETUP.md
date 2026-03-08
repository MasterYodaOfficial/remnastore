# Настройка browser auth через Supabase

Документ описывает базовую настройку browser-аутентификации для web-приложения.

Текущий целевой сценарий:
- основной social provider: `Google`
- дополнительно может использоваться `email/password` или `magic link`, если это нужно продукту
- источник бизнес-состояния остается в локальном backend, а `Supabase Auth` используется только для login identity

## Google OAuth

1. Открой `Google Cloud Console`.
2. Создай проект или выбери существующий.
3. Перейди в `APIs & Services -> Credentials`.
4. Создай `OAuth client ID` типа `Web application`.
5. Добавь redirect URL:
   - `https://<SUPABASE_PROJECT_REF>.supabase.co/auth/v1/callback`
6. Скопируй `Client ID` и `Client Secret`.
7. В `Supabase Dashboard` открой `Authentication -> Providers -> Google`.
8. Включи Google provider.
9. Вставь `Client ID` и `Client Secret`.
10. Сохрани изменения.

Официальная документация:
- https://supabase.com/docs/guides/auth/social-login/auth-google

## Redirect URLs

В `Supabase` также нужно задать корректные redirect URL для приложения.

Для локальной разработки обычно достаточно:
- `http://localhost:5173`
- `http://localhost:5173/`

Для production:
- `https://app.domain.ru`
- `https://app.domain.ru/`

Если используется отдельный flow для связки аккаунтов, query-параметры вроде `link_token` должны сохраняться фронтом при возврате из OAuth.

## Что важно не делать

- не использовать `service_role` или `sb_secret_*` на фронте
- не считать `Supabase` источником баланса, подписок или рефералов
- не включать лишние auth providers без необходимости
- не оставлять слишком широкие wildcard redirect URL

## Проверка после настройки

1. Открой web-приложение в браузере.
2. Нажми вход через Google.
3. Убедись, что после логина фронт получает сессию `Supabase`.
4. Убедись, что backend endpoint `GET /api/v1/accounts/me` возвращает локальный аккаунт.
5. Если аккаунт уже связан с Telegram, проверь, что профиль остается единым.

## Связанные документы

- [`README.md`](README.md)
- [`../../docs/account-linking.md`](../../docs/account-linking.md)
- [`../../docs/security-checklist.md`](../../docs/security-checklist.md)
