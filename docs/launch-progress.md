# Прогресс запуска

Этот файл нужен как рабочий трекер выполнения по фазам из [`docs/launch-roadmap.md`](launch-roadmap.md).

## Как использовать

- закрывай пункты только после фактической реализации и проверки
- если фаза начата, но не закончена, помечай ее как `В работе`
- если по ходу меняется состав задач, обновляй этот файл, а не создавай новый summary-документ

## Статус на сейчас

- Фаза 0: `Завершена`
- Фаза 1: `В работе`
- Фаза 2: `Завершена`
- Фаза 3: `Завершена`
- Фаза 4: `В работе`
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
Статус: `Завершена`

- [x] Спроектировать payment abstraction layer
- [x] Добавить модели платежей и историю статусов
- [x] Реализовать `YooKassaGateway`
- [x] Реализовать `TelegramStarsGateway`
- [x] Реализовать webhook/callback обработку с идемпотентностью
- [x] Поддержать `wallet_topup`
- [x] Поддержать `direct_plan_purchase`
- [x] Добавить frontend checkout flow
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
- backend-каталог тарифов теперь читается из `apps/api/app/config/subscription-plans.json`, отдается через `GET /api/v1/payments/plans` и является источником истины для `direct_plan_purchase`
- платная покупка тарифа через YooKassa создается endpoint `POST /api/v1/payments/yookassa/plans/{plan_code}` и сохраняет plan metadata в локальном `payments` snapshot
- платная покупка тарифа через Telegram Stars создается endpoint `POST /api/v1/payments/telegram-stars/plans/{plan_code}` и доступна только для `direct_plan_purchase`
- Telegram Stars не используются для `wallet_topup`; этот flow остается только за YooKassa, чтобы не смешивать `RUB` и `XTR` в кошельке
- для Telegram Stars введены внутренние bot -> api callbacks:
  - `POST /api/v1/webhooks/payments/telegram-stars/pre-checkout`
  - `POST /api/v1/webhooks/payments/telegram-stars`
  оба защищены `API_TOKEN`
- в `subscription-plans.json` тариф теперь может содержать `price_stars`; если поле не заполнено, Mini App не предлагает оплату этого тарифа через Stars
- для rollback-safe выдачи paid subscription добавлена таблица `subscription_grants`: сначала webhook фиксирует `target_expires_at`, потом отдельно финализирует продление в Remnawave по этому зафиксированному значению
- повторный callback с тем же `provider_event_id` больше не может продлить подписку второй раз; если первый проход успел только зафиксировать event/grant, повторный webhook безопасно завершит незакрытую финализацию
- frontend checkout flow теперь использует реальные endpoints `GET /api/v1/payments/plans`, `POST /api/v1/payments/yookassa/topup`, `POST /api/v1/payments/yookassa/plans/{plan_code}` и `POST /api/v1/payments/telegram-stars/plans/{plan_code}` вместо заглушек

## Фаза 3. Единый purchase flow и Remnawave
Статус: `Завершена`

- [x] Спроектировать единый `purchase service`
- [x] Объединить trial, wallet purchase и direct purchase в один flow
- [x] Определить правила продления действующей подписки
- [x] Реализовать rollback-safe обработку ошибок покупки
- [x] Проверить стабильную выдачу `subscription_url`
- [x] Проверить сценарии продления и повторной покупки

Утверждено 2026-03-11:
- вводим один доменный `purchase service` как единственную точку финализации подписки независимо от источника покупки
- `purchase service` не создает платежи и не валидирует provider callbacks; он работает только с уже подтвержденным основанием покупки
- источники покупки в Фазе 3:
  - `trial`
  - `wallet`
  - `direct_payment`
- `wallet_topup` остается отдельным billing flow и не идет через `purchase service`, потому что не выдает подписку сам по себе
- trial, покупка с баланса и прямая покупка обязаны сходиться в один путь расчета `target_expires_at`, провижининга в Remnawave и обновления локального snapshot

Целевой контракт `purchase service`:
- вход:
  - `account_id`
  - `purchase_source`
  - `plan_code` или `duration_days`
  - `reference_type`
  - `reference_id`
  - `idempotency_key`
- выход:
  - обновленный локальный subscription snapshot
  - рабочий `subscription_url`
- `target_expires_at`
- признак, был ли применен денежный side effect (`ledger debit`)

Инварианты Фазы 3:
- ни один flow выдачи платной подписки не должен обновлять `subscription_expires_at` и `subscription_url` мимо `purchase service`
- `trial` не трогает `ledger`, но обязан проходить тот же путь расчета окна действия и sync локального snapshot
- `wallet purchase` обязан сначала идемпотентно списать деньги через `ledger`, затем вызвать тот же путь выдачи подписки
- `direct purchase` обязан приходить в `purchase service` только после подтвержденного платежа и не иметь второго параллельного write path в Remnawave
- если провижининг в Remnawave не завершился, billing state не должен остаться в полупримененном состоянии без возможности безопасного повтора
- все сценарии продления должны использовать одну формулу расчета целевого окна подписки

Правила продления:
- если у пользователя есть активная подписка и `subscription_expires_at > now`, продление считается от `subscription_expires_at`
- если подписка истекла или отсутствует, продление считается от `now`
- целевая формула: `target_expires_at = max(now, current_expires_at) + duration`
- повторная покупка того же тарифа до истечения должна продлевать существующее окно, а не обнулять его
- trial нельзя запускать после уже использованного trial или после наличия платной истории

Точки объединения текущих flow:
- текущий `activate_trial` в `apps/api/app/services/subscriptions.py` должен стать thin-wrapper над `purchase service`
- финализация `direct_plan_purchase` из `apps/api/app/services/payments.py` должна перестать напрямую вызывать paid provisioning и перейти на `purchase service`
- новый `wallet purchase` должен строиться не как отдельная ветка подписки, а как `ledger debit + purchase service`

Ожидаемый итог Фазы 3:
- один code path для `trial`, `wallet purchase`, `direct purchase`
- единое правило продления и повторной покупки
- стабильная выдача `subscription_url` после каждого успешного purchase flow
- возможность безопасно ретраить незавершенную покупку без двойного продления и двойного списания

Закрыто 2026-03-11:
- `purchase service` теперь считает ответ Remnawave невалидным, если после provisioning пришел пустой `subscription_url`; такой кейс поднимается как `RemnawaveSyncError` до записи локального subscription snapshot
- добавлены тесты на отказ и повторный ретрай для `trial` и `wallet purchase`, а также unit-тесты общего paid/trial purchase path
- успешный wallet flow теперь явно проверяется на наличие непустого `subscription_url` в response и в локальном snapshot

Сделано 2026-03-11:
- добавлен единый backend-сервис `apps/api/app/services/purchases.py`
- `activate_trial` в `apps/api/app/services/subscriptions.py` больше не провижинит подписку напрямую и вызывает `purchase service`
- финализация `direct_plan_purchase` в `apps/api/app/services/payments.py` больше не вызывает paid provisioning напрямую и тоже идет через `purchase service`
- правило продления `max(now, current_expires_at) + duration` теперь живет в одном месте и покрыто тестами `tests.test_purchases`
- `wallet purchase` теперь идет через staged `subscription_grant` + idempotent `ledger debit` + тот же `purchase service`
- добавлен endpoint `POST /api/v1/subscriptions/wallet/plans/{plan_code}` для покупки тарифа с баланса
- повтор с тем же `idempotency_key` больше не списывает баланс и не продлевает подписку второй раз
- если Remnawave недоступен после списания, повтор с тем же `idempotency_key` безопасно завершает незакрытую покупку
- сценарии повторной покупки и продления теперь покрыты тестами `tests.test_subscriptions` и `tests.test_payments`

## Фаза 4. Рефералка и выводы
Статус: `В работе`

- [x] Вынести referral logic в отдельные backend services
- [x] Реализовать атрибуцию реферала один раз на пользователя
- [x] Поддержать индивидуальную ставку для партнеров и блогеров
- [x] Реализовать reward только на первую успешную оплату
- [x] Завести ledger entries для referral rewards
- [x] Реализовать модель `withdrawals`
- [x] Реализовать user flow подачи заявки на вывод
- [ ] Реализовать admin flow обработки выводов
- [x] Поддержать статусы `new`, `in_progress`, `paid`, `rejected`, `cancelled`
- [x] Добавить минимальную сумму вывода как настройку

Сделано 2026-03-11:
- добавлены модели `ReferralAttribution` и `ReferralReward`, а также миграция `20260311_add_referrals.py`
- вынесен отдельный доменный сервис `apps/api/app/services/referrals.py`
- атрибуция теперь идет через `POST /api/v1/referrals/claim` и допускается только один раз на аккаунт, с запретом self-referral и блокировкой после первой успешной платной покупки
- реферальная награда начисляется только на первую успешную paid purchase, независимо от того, была это `wallet purchase` или `direct purchase`
- награда пишет отдельный `ledger entry` типа `referral_reward`, а агрегаты `accounts.referral_earnings` и `accounts.referrals_count` обновляются только через доменный flow
- effective referral rate теперь берется как `account.referral_reward_rate` override или `settings.default_referral_reward_rate`
- добавлен `GET /api/v1/referrals/summary` для списка рефералов и текущих агрегатов
- frontend теперь захватывает `?ref=...`, выполняет deferred claim после авторизации и подгружает реальный referral summary во вкладке рефералов
- добавлена модель `Withdrawal`, миграция `20260311_add_withdrawals.py` и доменный сервис `apps/api/app/services/withdrawals.py`
- добавлены пользовательские endpoint'ы `POST /api/v1/withdrawals` и `GET /api/v1/withdrawals`
- при создании заявки сумма сразу резервируется через `ledger entry` типа `withdrawal_reserve`, чтобы ее нельзя было потратить повторно до ручной обработки
- `available_for_withdraw` больше не равен просто `referral_earnings`; теперь он считается как реально доступный остаток с учетом текущего баланса, уже выплаченных сумм и pending/in_progress заявок
- минимальная сумма вывода вынесена в `settings.min_withdrawal_amount_rub`

Проверено 2026-03-11:
- `tests.test_referrals`
- `tests.test_withdrawals`
- `tests.test_subscriptions`
- `tests.test_payments`
- `tests.test_account_linking`
- `tests.test_purchases`
- `apps/web: npm run build`

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
