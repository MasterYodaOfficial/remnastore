# Прогресс запуска

Этот файл нужен как рабочий трекер выполнения по фазам из [`docs/launch-roadmap.md`](launch-roadmap.md).

## Как использовать

- закрывай пункты только после фактической реализации и проверки
- если фаза начата, но не закончена, помечай ее как `В работе`
- если по ходу меняется состав задач, обновляй этот файл, а не создавай новый summary-документ

## Статус на сейчас

- Фаза 0: `Завершена`
- Фаза 1: `В работе`
- Фаза 2: `Не начато`
- Фаза 3: `Не начато`
- Фаза 4: `Не начато`
- Фаза 5: `Не начато`
- Фаза 6: `Не начато`
- Фаза 7: `Не начато`
- Фаза 8: `Не начато`

## Очередность работы

1. Закрыть Фазу 0
2. Перейти к Фазе 1
3. Не начинать платежи до появления ledger
4. Не начинать migration старой БД до стабилизации новых моделей
5. Не деплоить в production до закрытия критичных пунктов Фазы 8

## Фаза 0. Стабилизация текущей базы
Статус: `Завершена`

### Технический долг и выравнивание текущего состояния
- [x] Убрать старые рублевые/копеечные названия вроде `referral_earnings_cents`
- [x] Проверить, что во frontend баланс и реферальные суммы отображаются в рублях без плавающих дробей
- [x] Проверить, что backend и frontend используют одну и ту же семантику денежных полей

Закрыто 2026-03-09:
- backend переведен на поле `referral_earnings`, добавлена миграция хранения реферальных начислений в рублях.
- frontend показывает `balance` и реферальные суммы через целочисленный рублевый формат без дробной части.
- backend schema и frontend contract выровнены по рублевой семантике; старое поле читается только как временный fallback для совместимости.

### Account linking
- [x] Прогнать `Browser -> Telegram`
- [x] Прогнать `Telegram -> Browser`
- [x] Проверить merge уже существующих аккаунтов
- [x] Проверить повторное использование link token
- [x] Проверить истечение link token

Проверено 2026-03-09:
- добавлен интеграционный suite `apps/api/tests/test_account_linking.py` с проверкой обоих flow через HTTP endpoints.
- `Browser -> Telegram` и `Telegram -> Browser` проходят успешно, включая merge уже существующих аккаунтов.
- повторное использование `link_token` и истечение `link_token` возвращают ожидаемые ошибки.

### Базовая надежность
- [x] Добавить интеграционные тесты на account linking
- [x] Добавить проверки eligibility для trial
- [x] Проверить subscription sync с Remnawave
- [x] Зафиксировать production env-переменные в документации

Закрыто 2026-03-09:
- создан `docs/production-env.md` как единый production-контракт по env-переменным для `api`, `bot`, `web` и локального Docker Compose.
- `.env.example` переведен в production-style шаблон с актуальными переменными и без неиспользуемого мусора.
- добавлены backend endpoint'ы `GET /api/v1/subscriptions/`, `GET /api/v1/subscriptions/trial-eligibility`, `POST /api/v1/subscriptions/trial`, `POST /api/v1/subscriptions/sync`.
- eligibility для trial теперь проверяется по локальному статусу аккаунта, факту уже использованного trial и конфликтам identity в Remnawave по `email/telegram_id`.
- Remnawave sync проверен тестами на ручной sync endpoint и webhook `POST /api/v1/webhooks/remnawave` с HMAC-подписью `X-Remnawave-Signature`.
- покрытие: `tests.test_subscriptions` и `tests.test_account_linking`, суммарно `Ran 11 tests ... OK`.

### Что делать завтра первым
- [x] Просмотреть модели `accounts` и `schemas/account.py` на остатки старых денежных именований
- [x] Определить целевую naming scheme для referral earnings и payout-остатков
- [x] Подготовить первую миграцию на выравнивание именований

## Фаза 1. Биллинг и ledger
Статус: `В работе`

- [x] Спроектировать таблицу `ledger`
- [x] Добавить миграцию `ledger`
- [x] Реализовать `ledger service`
- [x] Перевести изменение баланса на ledger-backed операции
- [x] Добавить endpoint истории операций пользователя
- [ ] Добавить admin flow корректировки баланса с обязательным комментарием
- [x] Покрыть credit/debit операции тестами

Утверждено 2026-03-10:
- вводим одну append-only таблицу `ledger_entries` как источник истины для всех денежных движений
- поле `accounts.balance` пока сохраняем как быстрый snapshot, но менять его разрешено только внутри ledger-backed транзакций
- все денежные суммы в `ledger` храним в целых рублях без дробной части
- каждая запись `ledger_entries` обязана хранить `balance_before` и `balance_after`, чтобы история оставалась самодостаточной без пересчета по всему хвосту
- удаление и редактирование ledger-записей прикладным кодом запрещено; корректировки делаются только новыми compensating entries

Целевая таблица `ledger_entries`:
- `id`
- `account_id`
- `entry_type`
- `amount`
- `currency`
- `balance_before`
- `balance_after`
- `reference_type`
- `reference_id`
- `comment`
- `idempotency_key`
- `created_at`
- `created_by_account_id`
- `created_by_admin_id`

Первый набор `entry_type`:
- `topup_manual`
- `topup_payment`
- `subscription_debit`
- `referral_reward`
- `promo_credit`
- `refund`
- `admin_credit`
- `admin_debit`
- `merge_credit`
- `merge_debit`

Инварианты Фазы 1:
- ни одно изменение `accounts.balance` не должно происходить мимо `ledger service`
- стандартный `debit` не может уводить баланс в минус
- `admin_credit` и `admin_debit` требуют обязательный комментарий
- операции с внешними callback и повторяемыми запросами должны использовать `idempotency_key`
- merge аккаунтов должен оформляться парой записей `merge_debit` на source и `merge_credit` на target с общим `reference_id`
- промокоды пока не реализованы отдельной системой; когда появятся, они должны создавать только `promo_credit` entries, без прямой записи в `accounts.balance`

Реализовано 2026-03-10:
- добавлена миграция `apps/api/alembic/versions/20260310_add_ledger_entries.py` с таблицей `ledger_entries`, индексами и constraint'ами на ненулевую сумму и консистентность `balance_after`
- добавлена модель `LedgerEntry` и enum `LedgerEntryType`
- реализован `apps/api/app/services/ledger.py` с `credit_balance`, `debit_balance`, `admin_adjust_balance`, idempotency и history-query
- добавлен пользовательский endpoint `GET /api/v1/ledger/entries`
- merge аккаунтов в `apps/api/app/services/account_linking.py` переведен с прямой мутации `target.balance += source.balance` на ledger-backed перенос через `merge_debit` и `merge_credit`
- direct writes в `accounts.balance` теперь сосредоточены только внутри `ledger service`
- покрытие расширено тестами `tests.test_ledger`; суммарно `Ran 21 tests ... OK`

Остается до закрытия Фазы 1:
- вынести admin correction в отдельный защищенный HTTP flow; доменный метод `admin_adjust_balance` уже есть, но endpoint не добавлен, пока не утверждена схема admin-auth

## Фаза 2. Платежи: YooKassa и Telegram Stars
Статус: `В работе`

- [x] Спроектировать payment abstraction layer
- [x] Добавить модели платежей и историю статусов
- [x] Реализовать `YooKassaGateway`
- [ ] Реализовать `TelegramStarsGateway`
- [x] Реализовать webhook/callback обработку с идемпотентностью
- [x] Поддержать `wallet_topup`
- [ ] Поддержать `direct_plan_purchase`
- [ ] Добавить frontend checkout flow
- [x] Проверить защиту от двойных callback

Утверждено 2026-03-10:
- все платежные провайдеры должны быть нормализованы через один внутренний контракт `PaymentGateway`
- provider-специфичные payload, подписи и статусы не должны утекать в API routes и purchase flow
- оба пользовательских сценария Фазы 2 идут через два `flow_type`: `wallet_topup` и `direct_plan_purchase`
- результат создания платежа должен возвращаться как единый `payment intent` snapshot, независимо от провайдера
- webhook/callback от провайдера должен нормализоваться в единый `payment event` snapshot с provider event id для идемпотентности
- фактическое изменение баланса или выдача подписки не должны происходить внутри gateway; gateway только создает intent и нормализует внешние события

Нормализованные сущности payment abstraction:
- `PaymentProvider`: `yookassa`, `telegram_stars`
- `PaymentFlowType`: `wallet_topup`, `direct_plan_purchase`
- `PaymentStatus`: `created`, `pending`, `requires_action`, `succeeded`, `failed`, `cancelled`, `expired`
- `PaymentIntent`: внутренний snapshot созданного платежа с `provider_payment_id`, `status`, `amount`, `currency`, `confirmation_url`, `external_reference`
- `PaymentWebhookEvent`: внутренний snapshot callback/webhook события с `provider_event_id`, `provider_payment_id`, `status`, `amount`, `currency`, `flow_type`, `account_id`

Инварианты Фазы 2:
- один и тот же provider callback не должен финализировать платеж дважды
- `wallet_topup` и `direct_plan_purchase` обязаны использовать один payment abstraction layer, даже если дальше расходятся в business flow
- provider gateway не имеет права писать в `ledger` напрямую
- provider gateway не имеет права создавать/продлевать подписку в Remnawave напрямую
- raw provider payload должен сохраняться в платежной истории для аудита и отладки

Утверждено 2026-03-10 по моделям:
- `payments` хранит текущий нормализованный snapshot intent/invoice: провайдер, flow type, status, amount, currency, provider ids, confirmation URL, idempotency key, ссылки возврата и raw payload
- `payment_events` хранит append-only историю внешних callback/status событий и является точкой webhook-идемпотентности через уникальный `(provider, provider_event_id)`
- `payments` и `payment_events` не должны полагаться на cascade delete аккаунта; merge-логика при необходимости будет переносить бизнес-связь отдельно, audit должен сохраняться

Утверждено 2026-03-10 по YooKassa:
- используется официальный Python SDK `yookassa==3.10.0`
- создание платежа идет через `Payment.create(..., idempotency_key)` с `capture=true`, `confirmation.type=redirect` и `return_url`
- gateway нормализует статусы `pending`, `waiting_for_capture`, `succeeded`, `canceled` в общий `PaymentStatus`
- webhook ЮKassa не дает отдельного подписанного event id, поэтому внутри payment abstraction используется синтетический `provider_event_id = "<event>:<payment_id>"`
- webhook flow в backend уже реализован через `POST /api/v1/webhooks/payments/yookassa`; provider payload сначала нормализуется gateway, затем пишется в `payment_events` и идемпотентно финализирует локальный `payments` record
- для проверки подлинности webhook gateway дополнительно перечитывает платеж через API ЮKassa по `payment.id` и использует именно верифицированный provider state/metadata
- `wallet_topup` уже реализован через `POST /api/v1/payments/yookassa/topup`; успешный callback создает один `payment_event` и один ledger credit с idempotency key `payment:yookassa:<provider_payment_id>:credit`

## Фаза 3. Единый purchase flow и Remnawave
Статус: `Не начато`

- [ ] Спроектировать единый `purchase service`
- [ ] Объединить trial, wallet purchase и direct purchase в один flow
- [ ] Определить правила продления действующей подписки
- [ ] Реализовать rollback-safe обработку ошибок покупки
- [ ] Проверить стабильную выдачу `subscription_url`
- [ ] Проверить сценарии продления и повторной покупки

## Фаза 4. Рефералка и выводы
Статус: `Не начато`

- [ ] Вынести referral logic в отдельные backend services
- [ ] Реализовать атрибуцию реферала один раз на пользователя
- [ ] Поддержать индивидуальную ставку для партнеров и блогеров
- [ ] Реализовать reward только на первую успешную оплату
- [ ] Завести ledger entries для referral rewards
- [ ] Реализовать модель `withdrawals`
- [ ] Реализовать user flow подачи заявки на вывод
- [ ] Реализовать admin flow обработки выводов
- [ ] Поддержать статусы `new`, `in_progress`, `paid`, `rejected`, `cancelled`
- [ ] Добавить минимальную сумму вывода как настройку

## Фаза 5. Уведомления, поддержка и FAQ
Статус: `Не начато`

- [ ] Спроектировать модель `notifications`
- [ ] Сделать центр уведомлений в user app
- [ ] Сделать Telegram notification service
- [ ] Добавить уведомление об успешной оплате
- [ ] Добавить уведомление об ошибке оплаты
- [ ] Добавить уведомление о скором окончании подписки
- [ ] Добавить уведомление об окончании подписки
- [ ] Добавить уведомление о реферальном начислении
- [ ] Добавить уведомления по заявкам на вывод
- [ ] Добавить кнопку поддержки на Telegram-группу
- [ ] Добавить FAQ страницу
- [ ] Добавить `Privacy Policy` и `Terms`

## Фаза 6. Отдельная админка
Статус: `Не начато`

- [ ] Создать `apps/admin`
- [ ] Добавить таблицу `admins`
- [ ] Реализовать admin login
- [ ] Сделать dashboard
- [ ] Сделать user search по `telegram_id / email / username`
- [ ] Сделать карточку пользователя
- [ ] Добавить просмотр баланса и истории операций
- [ ] Добавить ручную корректировку баланса
- [ ] Добавить ручную выдачу подписки
- [ ] Добавить блокировку пользователя
- [ ] Добавить очередь выводов
- [ ] Добавить рассылки
- [ ] Добавить базовую статистику
- [ ] Добавить просмотр referral chain

## Фаза 7. Миграция из старого бота
Статус: `Не начато`

- [ ] Получить схему старой БД
- [ ] Описать mapping старых таблиц в новые модели
- [ ] Подготовить dry-run migration script
- [ ] Перенести пользователей
- [ ] Перенести балансы
- [ ] Перенести рефералов
- [ ] Перенести подписки
- [ ] Сверить данные с Remnawave
- [ ] Подготовить verification report после миграции

## Фаза 8. Production deployment и запуск
Статус: `Не начато`

- [ ] Подготовить production `.env`
- [ ] Подготовить production `docker compose`
- [ ] Настроить Nginx для `app.domain.ru`
- [ ] Настроить Nginx для `api.domain.ru`
- [ ] Настроить `api.domain.ru/bot/webhook`
- [ ] Выпустить TLS сертификаты
- [ ] Проверить backup и restore Postgres
- [ ] Подготовить release checklist
- [ ] Подготовить rollback steps
- [ ] Сделать первый production deploy

## Критические правила перед запуском

- [ ] Нет прямых изменений баланса мимо ledger
- [ ] Нет неподтвержденных merge аккаунтов по косвенным признакам
- [ ] Нет двойного начисления по повторным callback
- [ ] Нет возможности вывести обычный баланс кошелька вместо реферальных начислений
- [ ] Все admin actions пишут audit trail
- [ ] Все ключевые пользовательские сценарии покрыты ручным smoke test

## Короткий шаблон ежедневной отметки

```text
Дата:
Фаза:
Что сделано:
Что сломалось:
Что дальше:
```
