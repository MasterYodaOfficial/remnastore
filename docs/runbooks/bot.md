# Bot Runbook

## Когда открывать

- бот не отвечает на `/start`
- сломалось главное меню
- не работает deep-link `ref_*`
- кнопка открытия Mini App не ведет в рабочий flow
- Telegram Stars сценарий ломается до API или не вызывает expected callback

## Где смотреть

- `./scripts/dev.sh logs bot`
- `./scripts/dev.sh logs api`
- при payment-related кейсе дополнительно `./scripts/dev.sh logs worker`

## Что проверить первым

- `BOT_TOKEN`
- `BOT_USERNAME`
- `BOT_USE_WEBHOOK`
- `BOT_WEBHOOK_BASE_URL`
- `BOT_WEBHOOK_PATH`
- `BOT_WEBHOOK_SECRET`
- `API_URL`
- `API_TOKEN`

## Быстрый разбор

### 1. Бот жив как transport

- `/start` должен отвечать
- если в webhook mode тишина полная, проверять webhook URL/secret и логи `bot`
- если polling/dev mode, проверять старт процесса и ошибки при boot

### 2. Работает ли deep-link

- если сломан `ref_*`, смотреть `/start` payload и дальнейший referral intent flow
- если открытие Mini App теряет контекст, смотреть bot-generated URL и frontend query params

### 3. Доходит ли internal callback до API

- для Telegram Stars и внутренних bot -> api вызовов проверять `API_TOKEN`
- искать 401/403/5xx в связке `bot` + `api`

## Что подтверждает здоровый flow

- `/start` отрабатывает без traceback
- bot menu / кнопки открываются
- Mini App button ведет на ожидаемый `WEBAPP_URL`
- payment-related callbacks доходят до API

## Безопасные действия

- безопасно перезапустить `bot`
- при конфиг-проблеме сначала исправить env, потом перезапускать
- не подменять вручную internal callback payload, если не зафиксированы исходные входные данные

## Когда эскалировать

- bot transport жив, но теряются только отдельные callback/deep-link сценарии
- после restart проблема воспроизводится сразу
- инцидент затрагивает платежи, auth или account linking, а не только тексты/кнопки
