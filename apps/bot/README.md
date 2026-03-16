# Telegram-бот

`apps/bot` - Telegram-бот на `aiogram`.

Он отвечает за:
- вход пользователя в продукт через Telegram
- запуск Mini App
- подтверждение сценариев связки аккаунтов
- уведомления и вспомогательные user flows

Основная логика находится в каталоге `bot/`.

Полезные документы:
- [`docs/bot-inline-menu-v1.md`](../../docs/bot-inline-menu-v1.md) - согласованный scope и архитектура inline-бота `v1`
