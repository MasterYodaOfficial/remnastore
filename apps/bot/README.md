# Telegram-бот

`apps/bot` - Telegram-бот на `aiogram`.

Он отвечает за:
- вход пользователя в продукт через Telegram
- запуск Mini App
- подтверждение сценариев связки аккаунтов
- уведомления и вспомогательные user flows

Основная логика находится в каталоге `bot/`.

Полезные документы:
- [`docs/account-linking.md`](../../docs/account-linking.md) - сценарии связки Telegram и browser-аккаунтов
- [`docs/architecture.md`](../../docs/architecture.md) - общая архитектура проекта
