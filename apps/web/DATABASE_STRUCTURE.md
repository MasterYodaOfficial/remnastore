# Текущее состояние структуры данных

Этот документ больше не описывает старую схему `KV Store`. Для нового контура источником истины является PostgreSQL в `apps/api`.

## Уже существующие ключевые таблицы

### `accounts`
Хранит локальный аккаунт пользователя.

Основные поля:
- `id`
- `email`
- `display_name`
- `telegram_id`
- `username`
- `first_name`
- `last_name`
- `is_premium`
- `locale`
- `remnawave_user_uuid`
- `subscription_url`
- `balance`
- `referral_code`
- `referral_earnings_cents` - старое имя, требует приведения к рублевой семантике
- `referrals_count`
- `referral_reward_rate`
- `referred_by_account_id`
- `status`
- `last_login_source`
- `last_seen_at`
- `created_at`
- `updated_at`

### `auth_accounts`
Хранит внешние auth identity, привязанные к локальному аккаунту.

Основные поля:
- `id`
- `account_id`
- `provider`
- `provider_uid`
- `email`
- `display_name`
- `linked_at`

### `auth_link_tokens`
Хранит одноразовые токены для связки аккаунтов.

Основные поля:
- `id`
- `account_id`
- `link_token`
- `provider`
- `provider_uid`
- `email`
- `display_name`
- `expires_at`
- `consumed_at`
- `telegram_id`
- `link_type`
- `created_at`

## Планируемые таблицы по roadmap

Следующим этапом должны появиться:
- `ledger`
- `payments`
- `withdrawals`
- `notifications`
- `admins`
- дополнительные referral-сущности для partner overrides и reward records

## Где смотреть актуальную схему

- модели: `apps/api/app/db/models/`
- миграции: `apps/api/alembic/versions/`
- дорожная карта: [`../../docs/launch-roadmap.md`](../../docs/launch-roadmap.md)
- трекер выполнения: [`../../docs/launch-progress.md`](../../docs/launch-progress.md)
