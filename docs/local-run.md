# Локальный запуск

## Вариант 1. Обычный localhost

Подходит, если не нужен внешний HTTPS.

В `.env` обычно ставят:

```env
BOT_USE_WEBHOOK=false
WEBAPP_URL=http://localhost:5173
VITE_API_BASE_URL=http://localhost:8000
VITE_TELEGRAM_BOT_URL=https://t.me/your_bot_username
VITE_SUPPORT_TELEGRAM_URL=https://t.me/your_support
```

Запуск текущей ветки из исходников:

```bash
docker compose --env-file .env \
  -f ops/docker/compose.yml \
  -f ops/docker/compose.local.yml \
  up -d --build
```

Остановка:

```bash
docker compose --env-file .env \
  -f ops/docker/compose.yml \
  -f ops/docker/compose.local.yml \
  down
```

## Вариант 2. Локально через CloudPub

Подходит, если нужны:

- внешний HTTPS
- Google OAuth redirect
- Supabase email redirect
- Telegram webhook
- проверка на телефоне

CloudPub просто проксирует локальный порт в публичный HTTPS-домен.

### Рекомендуемая схема

| Сервис | Локальный порт | Публичный адрес |
| --- | --- | --- |
| `api` | `8000` | `https://api-xxx.cloudpub.ru` |
| `web` | `5173` | `https://web-xxx.cloudpub.ru` |
| `admin` | `5174` | `https://admin-xxx.cloudpub.ru` |
| `bot` | `8080` | `https://bot-xxx.cloudpub.ru` |

### Что поставить в `.env`

```env
WEBAPP_URL=https://web-xxx.cloudpub.ru
VITE_API_BASE_URL=https://api-xxx.cloudpub.ru
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_public_key
VITE_TELEGRAM_BOT_URL=https://t.me/your_bot_username
VITE_SUPPORT_TELEGRAM_URL=https://t.me/your_support

BOT_USE_WEBHOOK=true
BOT_WEBHOOK_BASE_URL=https://bot-xxx.cloudpub.ru
BOT_WEBHOOK_PATH=/bot/webhook
```

### Как запускать

Для текущей ветки:

```bash
docker compose --env-file .env \
  -f ops/docker/compose.yml \
  -f ops/docker/compose.local.yml \
  up -d --build
```

Для опубликованных образов:

```bash
./scripts/stack.sh pull
./scripts/stack.sh up
```

### Что важно

- домены CloudPub должны быть добавлены в `Supabase Auth -> Redirect URLs`
- `web` и `admin` читают `VITE_*` из `.env` контейнера при старте
- если используете CloudPub, отдельный nginx с сертификатами для локального стенда не нужен
