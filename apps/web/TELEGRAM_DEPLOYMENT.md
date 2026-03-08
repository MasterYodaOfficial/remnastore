# Подключение Telegram Mini App

Документ описывает базовую схему подключения web-приложения к Telegram-боту и webhook backend.

## Целевая схема

- пользователь открывает бота в Telegram
- бот отдает кнопку или menu button для открытия Mini App
- Mini App загружается с `app.domain.ru`
- backend API доступен на `api.domain.ru`
- webhook бота обслуживается на `api.domain.ru/bot/webhook`

## Что нужно подготовить

- Telegram-бот через `@BotFather`
- публичный HTTPS URL для web-приложения
- публичный HTTPS URL для API
- корректные env-переменные для bot и api

## BotFather

### Создание бота

1. Открой `@BotFather`.
2. Выполни `/newbot`.
3. Задай имя и `username`.
4. Сохрани `BOT_TOKEN`.

### Настройка Mini App

1. Выполни `/newapp`.
2. Выбери нужного бота.
3. Укажи название приложения.
4. Укажи описание.
5. Задай URL web-приложения, например `https://app.domain.ru`.
6. При необходимости настрой menu button на этот же URL.

## Что должно быть в backend

- endpoint авторизации Telegram Mini App
- валидация `Telegram.WebApp.initData`
- выдача backend JWT после успешной проверки
- webhook endpoint для бота

## Что проверить после подключения

1. Mini App открывается из бота.
2. Авторизация проходит без ручного логина.
3. Темы Telegram корректно применяются.
4. Browser-link flow из Mini App открывает браузерный сценарий связки.
5. Пользовательский профиль после входа совпадает с локальным аккаунтом backend.

## Важно для production

- Telegram Mini App должен работать только по `HTTPS`
- нельзя доверять `initDataUnsafe` как источнику истины
- проверка подписи `initData` должна происходить на backend
- raw `initData` нельзя без необходимости писать в production-логи

## Полезные ссылки

- Telegram Mini Apps: https://core.telegram.org/bots/webapps
- BotFather: https://t.me/botfather
- Telegram Bot API: https://core.telegram.org/bots/api
