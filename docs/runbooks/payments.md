# Payments Runbook

## Когда открывать

- пользователь говорит, что оплатил, но баланс или подписка не обновились
- платеж завис в `pending`
- pending top-up не возобновляется
- провайдер подтвердил оплату, а локальная система нет
- после оплаты не сработали referral reward или notification side effects

## Что собрать сразу

- account id / email / telegram id
- provider: `yookassa` или `telegram_stars`
- local payment id, если он уже виден в admin UI
- время попытки платежа
- `request_id`, если есть из API-ответа

## Где смотреть

- `./scripts/dev.sh logs api`
- `./scripts/dev.sh logs worker`
- `./scripts/dev.sh logs bot`
  - нужен для Telegram Stars pre-checkout / callback сценариев
- admin UI:
  - карточка аккаунта
  - блоки `payments`, `ledger`, `notifications`
  - timeline событий аккаунта

## Что должно подтверждать нормальный flow

- в timeline есть `payment.intent.created`
- при успешном завершении есть `payment.finalized`
- для top-up есть `payment.topup.applied`
- для покупки тарифа есть `subscription.wallet_purchase.*` или `subscription.direct_payment.*`
- при первой оплаченной referral-конверсии может появиться `referral.reward.granted`

## Быстрый разбор

### 1. Был ли создан payment intent

- если нет `payment.intent.created`, проблема обычно в frontend/API до провайдера
- проверить запросы на создание платежа и локальные ошибки в `api`

### 2. Подтвердил ли провайдер оплату

- если это `yookassa`, проверить webhook path и логи `api`, потом `worker`
- если это `telegram_stars`, проверить `bot` и `api` для internal callback flow
- если у провайдера успех есть, а `payment.finalized` нет, обычно проблема в webhook/callback обработке или worker reconcile

### 3. Финализировался ли локальный payment

- если `payment.finalized` есть, но баланс/подписка не отражены в UI, смотреть:
  - `ledger`
  - `subscription snapshot`
  - account timeline
  - `notifications`

### 4. Не залип ли recovery path

- для YooKassa возможно отсутствие webhook при живом provider state
- в таком случае приоритетно смотреть `worker`, потому что reconcile path должен безопасно дотянуть незавершенный payment

## Безопасные действия

- можно безопасно перезапустить `worker`, если есть признаки зависшего reconcile path
- можно повторно разбирать один и тот же payment по `payment id` и account timeline
- нельзя вручную править `ledger`, `payments` и баланс аккаунта до понимания root cause
- нельзя “докидывать” подписку вручную мимо audit trail и ledger-backed flow

## Когда эскалировать

- провайдер говорит `succeeded`, а локально нет ни webhook, ни reconcile эффекта
- есть `payment.finalized`, но баланс/подписка противоречат ledger или account timeline
- подозрение на двойное применение одного платежа
- платеж затронул деньги, но вручную восстановить картину по логам и timeline уже нельзя
