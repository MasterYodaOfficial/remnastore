# Withdrawals Runbook

## Когда открывать

- пользователь не может создать заявку на вывод
- сумма зарезервировалась странно или не совпадает с доступным к выводу
- заявка зависла в `pending` / `in_progress`
- admin status change не применился или применился неверно
- пользователь говорит, что выплата/отклонение не отражены в интерфейсе

## Где смотреть

- `./scripts/dev.sh logs api`
- `./scripts/dev.sh logs notifications-worker`
- admin UI:
  - карточка аккаунта
  - блок `withdrawals`
  - account timeline
  - admin list `withdrawals`

## Что должно быть в данных

- создание заявки идет через `POST /api/v1/withdrawals`
- список пользователя идет через `GET /api/v1/withdrawals`
- ручная обработка admin flow идет через:
  - `GET /api/v1/admin/withdrawals`
  - `POST /api/v1/admin/withdrawals/{withdrawal_id}/status`
- при создании заявки должен появиться `withdrawal.created`
- при обработке админом должен быть audit trail `admin.withdrawal.status_change`

## Денежная логика, которую нельзя ломать

- при создании заявки деньги резервируются через `withdrawal_reserve`
- при отклонении делается compensating flow через `withdrawal_release`
- при выплате нельзя списывать деньги второй раз вручную
- пользовательский UI не должен повторно показывать полный номер карты после создания заявки

## Быстрый разбор

### 1. Создалась ли заявка

- если нет `withdrawal.created`, смотреть validation/API error
- если пользователь жалуется на “не хватает средств”, сверять не общий баланс, а доступный referral amount

### 2. Есть ли резерв

- если заявка есть, но резерв не сошелся, смотреть `ledger` и timeline аккаунта
- ручная правка баланса до разбора причины запрещена

### 3. Отработала ли admin-обработка

- если status change не применился, смотреть `api` logs и `admin_action_log`-related события
- если заявка обработана, а пользователь не видит обновление, дополнительно смотреть `notifications-worker`

## Безопасные действия

- можно повторно открывать admin list и account timeline для той же withdrawal id
- можно перезапустить `notifications-worker`, если сломан только delivery path
- нельзя вручную двигать заявку между статусами в БД
- нельзя вручную компенсировать резерв без понимания ledger последствий

## Когда эскалировать

- payout/reject уже применился, но ledger не соответствует статусу withdrawal
- есть подозрение на двойную выплату или потерянный резерв
- account timeline и admin list противоречат друг другу
