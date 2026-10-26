# VK ID через Supabase

## Состояние

Разработка ведётся локально в `feature/vk-id` от обновлённого `dev`
после слияния Яндекс ID (26 октября 2026 года). Подготовлены OAuth-мост,
кнопка входа, сопоставление identity, конфигурация и автоматические проверки.
Приложение VK ID и production-провайдер не настраивались; настоящий вход
ещё не проверен. По умолчанию кнопка скрыта. Владелец разрешил публикацию ветки
и PR в `dev` 26 октября 2026 года. Production-деплой остаётся отдельной командой.
Инструкция входит во вложения будущего выпуска 1.1.0.

## Почему нужен мост

Актуальный VK ID требует `device_id` из callback при обмене кода, а профиль
возвращает через POST `/oauth2/user_info`. Generic OAuth2 provider Supabase
получает профиль через GET и не передаёт произвольные параметры callback
в token endpoint. Поэтому между Supabase и VK находится небольшой OAuth-мост
в API; отдельный сервис авторизации и собственные пользовательские JWT
для браузера не добавляются.

Основание: [официальный VK ID Web SDK](https://github.com/VKCOM/vkid-web-sdk/blob/master/src/auth/auth.ts)
и [реализация custom OAuth в используемом GoTrue v2.197.0](https://github.com/supabase/auth/blob/v2.197.0/internal/api/provider/custom_oauth.go).
Регистрация custom-провайдера описана в
[документации Supabase](https://supabase.com/docs/guides/auth/custom-oauth-providers).

## Поток входа

1. Кнопка вызывает `supabase.auth.signInWithOAuth({provider: 'custom:vk'})`.
   Supabase сохраняет собственные state и PKCE verifier.
2. Supabase направляет браузер в `GET /api/v1/auth/vk/authorize` с challenge
   S256. Мост проверяет точные client ID и Supabase callback, создаёт отдельный
   случайный state VK и перенаправляет в `https://id.vk.ru/authorize`.
3. VK возвращает браузер в `GET /api/v1/auth/vk/callback` с code и device_id.
   Мост атомарно погашает state и возвращает Supabase короткоживущий собственный
   код вместо кода VK. Исходный state Supabase сохраняется.
4. Supabase вызывает `POST /api/v1/auth/vk/token`, предъявляя отдельный секрет
   моста и PKCE verifier. Мост проверяет challenge, атомарно погашает код,
   обменивает код VK и получает профиль. Проверяет state ответа и совпадение
   user_id профиля с token response.
5. Supabase получает случайный непрозрачный токен профиля, затем вызывает
   `GET /api/v1/auth/vk/userinfo`. Ответ содержит только `sub`, имя,
   необязательный email и `email_verified=false`. Обычную сессию выдаёт Supabase.

Токены VK и refresh token не сохраняются и не передаются Supabase или браузеру.
В Redis временно хранятся state (300 секунд), код моста с кодом VK и device_id
(120 секунд), токен с минимальным профилем (60 секунд). Коды и state одноразовые;
ключи Redis содержат SHA-256 случайных идентификаторов. Для погашения используется
`GETDEL`, нужен Redis 6.2+ (штатный Compose использует Redis 7).
При отсутствии или сбое Redis вход закрывается с 503, без локального fallback.

## Настройки для будущего включения

Настройки API (добавлены в оба `.env.example`):

| Переменная | Значение |
| --- | --- |
| `VK_OAUTH_CLIENT_ID` | ID зарегистрированного веб-приложения VK ID |
| `VK_OAUTH_BRIDGE_SECRET` | Отдельный случайный секрет не короче 32 символов, общий только для API и Supabase |
| `VK_OAUTH_CALLBACK_URL` | Публичный HTTPS URL API, заканчивающийся на `/api/v1/auth/vk/callback` |
| `VK_OAUTH_SUPABASE_CALLBACK_URL` | Точный callback custom-провайдера Supabase, например `https://auth.example.com/auth/v1/callback` |
| `REDIS_URL` | Общий Redis для всех экземпляров API |

Client Secret приложения VK не используется этим PKCE-потоком. Секрет моста
не является секретом VK, Supabase service role key или JWT secret.
Не передавать его через VITE-переменные, URL или диагностические дампы.
Пустая или неполная конфигурация API даёт 503, а не открытый redirect.

1. Зарегистрировать веб-приложение в [кабинете VK ID](https://id.vk.ru/about/business/go/).
   Указать домен и redirect URI **API-моста** (`VK_OAUTH_CALLBACK_URL`),
   запросить минимальное разрешение `email`. Проверить доступность приложения
   и разрешений для реальных пользователей согласно настройкам VK.
2. Подготовить окружение API и Redis. У reverse proxy отключить запись query
   string для OAuth callback: code, state и device_id не должны попадать
   в access/error логи. Фильтр Python маскирует эти параметры, но он не защищает
   журналы внешнего proxy и инфраструктуры.
3. В Supabase создать **OAuth2**, не OIDC, провайдер с такими полями:

   ```json
   {
     "provider_type": "oauth2",
     "identifier": "custom:vk",
     "name": "VK ID",
     "client_id": "<VK_OAUTH_CLIENT_ID>",
     "client_secret": "<VK_OAUTH_BRIDGE_SECRET>",
     "authorization_url": "https://api.example.com/api/v1/auth/vk/authorize",
     "token_url": "https://api.example.com/api/v1/auth/vk/token",
     "userinfo_url": "https://api.example.com/api/v1/auth/vk/userinfo",
     "scopes": [],
     "pkce_enabled": true,
     "email_optional": true,
     "enabled": false
   }
   ```

   На self-hosted GoTrue v2.197.0 это тело POST `/admin/custom-providers`
   с авторизацией service role; при PUT `/admin/custom-providers/custom:vk`
   убрать неизменяемые `provider_type` и `identifier`. Запрос выполнять
   на защищённом хосте без вывода тела и секретов в консоль.
   `scopes` пуст: мост сам задаёт scope VK; дополнительный `openid` не нужен.
   Сначала оставить провайдер выключенным, затем включить на тестовом окружении.
4. На self-hosted Auth проверить `GOTRUE_CUSTOM_OAUTH_EXTERNAL_URL`:
   существующая настройка из [Яндекс ID](yandex-id.md) используется совместно.
   В v2.197.0 Auth добавляет к ней `/callback`; итог обязан точно совпасть
   с `VK_OAUTH_SUPABASE_CALLBACK_URL`. Существующий Google callback не менять.
5. На тестовом frontend включить `VITE_VK_AUTH_ENABLED=true` и пройти сценарии
   ниже. В Docker флаг входит в `runtime-config.js` при старте контейнера;
   локальный Vite читает `apps/web/.env` или окружение процесса, а не корневой
   `.env`. Значения и секреты production пока не изменять.

VK может не вернуть email. `email_optional=true` позволяет сохранить identity
по стабильному `sub` без выдуманного адреса. Если email есть, он не считается
подтверждённым: при `GOTRUE_MAILER_AUTOCONFIRM=false` Supabase может потребовать
письмо с подтверждением. Интерфейс уже показывает соответствующее сообщение.
Не включать общее автоподтверждение почты ради обхода проверки.

Backend сопоставляет только `custom:vk` с `AuthProvider.VK`. Повторный вход
ищет существующий аккаунт по identity, сохраняя привязку Telegram. Слияние
разных аккаунтов и новый механизм привязки VK в настройках не добавлялись;
используются существующие правила аккаунтов и конфликтов проекта.

## Проверки перед production

- Первый и повторный вход с реальным VK, отсутствие email, подтверждение
  письмом при необходимости; в исходном аккаунте сохраняются баланс и подписка.
- Отмена, истечение state/кода, повторный callback, сбой Redis/VK и неверный
  verifier не открывают кабинет и не показывают внутренние ошибки.
- Конфликт уже занятой identity, существующая привязка Telegram, referral intent.
- Desktop и мобильный браузер, возврат из внешнего браузера, выход и обновление
  сессии Supabase. Вызовы refresh VK мост не реализует: сессией управляет Supabase.
- Google, Яндекс, email/password и recovery работают после настройки
  общего custom callback; секретов и callback query нет в логах proxy/API/Auth.

Автоматические тесты используют подменённые ответы VK и Supabase. Они проверяют
протокол моста и запуск браузерного OAuth, но не заменяют реальный вход,
настройку redirect URI, разрешений VK и доставку писем.

Локально 26 октября 2026 года прошли 100 профильных API-тестов (VK, cache,
logging, аккаунты, существующий auth, Supabase, Яндекс и привязка Telegram),
61 unit-тест frontend и все 21 браузерный тест. Прошли Ruff, frontend lint,
TypeScript и production-сборка. Покрытие новых endpoint/service VK — 94%.
Это не полный прогон всех API-тестов и не проверка реальных провайдеров.
