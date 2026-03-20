# Webhooks Runbook

## Когда открывать

- внешний webhook “не пришел”
- API отвечает `401/403/400` на callback
- webhook приходит повторно, а продукт ведет себя странно
- Remnawave, YooKassa или Telegram Stars не вызывают ожидаемый side effect

## Какие входы покрывает runbook

- `POST /api/v1/webhooks/payments/yookassa`
- `POST /api/v1/webhooks/payments/telegram-stars/pre-checkout`
- `POST /api/v1/webhooks/payments/telegram-stars`
- `POST /api/v1/webhooks/remnawave`

## Где смотреть

- `./scripts/dev.sh logs api`
- `./scripts/dev.sh logs bot`
  - нужен для Telegram Stars transport flow
- `./scripts/dev.sh logs worker`
  - нужен, если webhook не дошел, а reconcile path должен догнать состояние
- admin UI:
  - account timeline
  - глобальная вкладка `События`

## Что проверить первым

### YooKassa

- endpoint отвечает без `5xx`
- provider payload содержит ожидаемый `payment.id` и metadata
- после webhook появляется локальный `payment.finalized` или понятная ошибка в `api`

### Telegram Stars

- `API_TOKEN` совпадает в `bot` и `api`
- pre-checkout проходит через internal callback без auth mismatch
- финальный callback доходит до API и не ломается на валидации payload

### Remnawave

- `REMNAWAVE_WEBHOOK_SECRET` совпадает с тем, что настроено в панели
- запрос приходит с `X-Remnawave-Signature`
- в timeline аккаунта появляется `subscription.remnawave.webhook`, если событие относится к известному аккаунту

## Типовые причины

- неверный secret / shared token
- provider шлет webhook не на тот URL
- payload пришел, но не проходит валидацию
- транспорт дошел, но downstream side effect уже ломается внутри business logic

## Безопасные действия

- сохранить время, headers и provider entity id до любых повторов
- для payment webhook не делать ручное “зачисление вместо webhook”
- повтор webhook допустим только при сохраненном исходном payload и понимании идемпотентности
- если подозрение на secret mismatch, сначала чинить конфиг, а не replay'ить старые запросы вслепую

## Когда эскалировать

- повтор webhook дает разные результаты для одной и той же provider entity
- есть признаки сломанной идемпотентности
- Remnawave webhook проходит transport, но локальный subscription snapshot расходится с ожидаемым состоянием
- Telegram Stars callback ломает деньги или подписку, а не только уведомления
