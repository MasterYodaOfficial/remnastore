# Telegram-бот

`apps/bot` — бот на `aiogram`.

Отвечает за:

- вход пользователя через Telegram
- запуск Mini App
- webhook Telegram
- пользовательские уведомления
- вспомогательные сценарии связки Telegram и браузерного аккаунта

Основной docker-сервис: `bot`  
Порт внутри стека: `8080`

Полезные документы:

- [`docs/architecture.md`](../../docs/architecture.md)
- [`docs/local-run.md`](../../docs/local-run.md)
- [`docs/deploy-vds.md`](../../docs/deploy-vds.md)
