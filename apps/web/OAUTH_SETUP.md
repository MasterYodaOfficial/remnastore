# Настройка OAuth провайдеров

Для работы авторизации через Google, Yandex и VK необходимо настроить OAuth провайдеры в Supabase.

## Google OAuth

1. Откройте [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте новый проект или выберите существующий
3. Перейдите в "APIs & Services" > "Credentials"
4. Нажмите "Create Credentials" > "OAuth client ID"
5. Выберите "Web application"
6. Добавьте Authorized redirect URIs:
   - `https://YOUR_PROJECT_ID.supabase.co/auth/v1/callback`
7. Скопируйте Client ID и Client Secret
8. В Supabase Dashboard:
   - Перейдите в Authentication > Providers > Google
   - Включите Google provider
   - Вставьте Client ID и Client Secret
   - Сохраните изменения

Подробная инструкция: https://supabase.com/docs/guides/auth/social-login/auth-google

## Yandex OAuth

1. Откройте [Yandex OAuth](https://oauth.yandex.ru/)
2. Создайте новое приложение
3. Добавьте Callback URI:
   - `https://YOUR_PROJECT_ID.supabase.co/auth/v1/callback`
4. Скопируйте Client ID и Client Secret
5. В Supabase Dashboard:
   - Перейдите в Authentication > Providers > Yandex (если доступен)
   - Включите Yandex provider
   - Вставьте Client ID и Client Secret

## VK OAuth

1. Откройте [VK Developers](https://vk.com/dev)
2. Создайте новое приложение
3. Настройте Authorized redirect URI:
   - `https://YOUR_PROJECT_ID.supabase.co/auth/v1/callback`
4. Скопируйте App ID и Secure key
5. В Supabase Dashboard:
   - Перейдите в Authentication > Providers
   - Найдите VK (если доступен) или настройте через Generic OAuth

## Важно

После настройки всех провайдеров приложение будет работать как в браузере (с OAuth), так и в Telegram WebApp (с автоматической авторизацией через Telegram ID).

## Тестирование без OAuth

Для тестирования без настройки OAuth:
- Откройте приложение в Telegram WebApp - авторизация произойдет автоматически
- В браузере можно временно использовать email/password регистрацию (добавьте соответствующий функционал)
