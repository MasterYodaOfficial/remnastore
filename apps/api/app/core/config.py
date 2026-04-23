import re
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_BOT_ADMIN_IDS_SPLIT_RE = re.compile(r"[\s,]+")


def parse_bot_admin_ids(raw_value: str) -> tuple[int, ...]:
    normalized = raw_value.strip()
    if not normalized:
        return ()

    admin_ids: list[int] = []
    for token in _BOT_ADMIN_IDS_SPLIT_RE.split(normalized):
        if not token:
            continue
        if not token.isdigit():
            raise ValueError(
                "BOT_ADMIN_IDS must contain only positive integer Telegram IDs"
            )
        admin_id = int(token)
        if admin_id <= 0:
            raise ValueError("BOT_ADMIN_IDS must contain only positive Telegram IDs")
        if admin_id not in admin_ids:
            admin_ids.append(admin_id)
    return tuple(admin_ids)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "remnastore-api"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    log_format: str = Field(default="text", validation_alias="LOG_FORMAT")
    log_to_file: bool = Field(default=False, validation_alias="LOG_TO_FILE")
    log_dir: str = Field(default="./.logs", validation_alias="LOG_DIR")
    log_file_max_bytes: int = Field(
        default=10 * 1024 * 1024, validation_alias="LOG_FILE_MAX_BYTES"
    )
    log_file_backup_count: int = Field(
        default=5, validation_alias="LOG_FILE_BACKUP_COUNT"
    )
    access_log_enabled: bool = Field(
        default=True, validation_alias="ACCESS_LOG_ENABLED"
    )

    database_url: str = ""
    redis_url: str = ""

    remnawave_api_url: str = ""
    remnawave_api_token: str = ""
    remnawave_webhook_secret: str = ""
    remnawave_username_prefix: str = ""
    remnawave_user_label: str = ""
    remnawave_default_internal_squad_uuid: str = ""
    remnawave_default_internal_squad_name: str = ""
    trial_duration_days: int = Field(
        default=3,
        validation_alias="TRIAL_DURATION_DAYS",
    )
    trial_traffic_limit_gb: int = Field(
        default=10,
        validation_alias="TRIAL_TRAFFIC_LIMIT_GB",
        ge=0,
    )
    trial_traffic_limit_strategy: Literal[
        "NO_RESET", "DAY", "WEEK", "MONTH", "MONTH_ROLLING"
    ] = Field(
        default="WEEK",
        validation_alias="TRIAL_TRAFFIC_LIMIT_STRATEGY",
    )
    trial_device_limit: int = Field(
        default=3,
        validation_alias="TRIAL_DEVICE_LIMIT",
        ge=0,
    )
    default_subscription_device_limit: int = Field(
        default=3,
        validation_alias="DEFAULT_SUBSCRIPTION_DEVICE_LIMIT",
        ge=0,
    )
    default_referral_reward_rate: float = Field(
        default=20.0,
        validation_alias="DEFAULT_REFERRAL_REWARD_RATE",
    )
    referral_reward_payment_commission_rate_rub: float = Field(
        default=0.0,
        validation_alias="REFERRAL_REWARD_PAYMENT_COMMISSION_RATE_RUB",
        ge=0,
        le=100,
    )
    referral_reward_payment_commission_rate_xtr: float = Field(
        default=0.0,
        validation_alias="REFERRAL_REWARD_PAYMENT_COMMISSION_RATE_XTR",
        ge=0,
        le=100,
    )
    min_withdrawal_amount_rub: int = Field(
        default=300,
        validation_alias="MIN_WITHDRAWAL_AMOUNT_RUB",
    )
    yookassa_shop_id: str = Field(default="", validation_alias="YOOKASSA_SHOP_ID")
    yookassa_secret_key: str = Field(default="", validation_alias="YOOKASSA_SECRET_KEY")
    yookassa_api_url: str = Field(
        default="https://api.yookassa.ru/v3",
        validation_alias="YOOKASSA_API_URL",
    )
    yookassa_verify_tls: bool = Field(
        default=True, validation_alias="YOOKASSA_VERIFY_TLS"
    )
    api_token: str = Field(default="", validation_alias="API_TOKEN")
    payment_pending_ttl_seconds_yookassa: int = Field(
        default=3600,
        validation_alias="PAYMENT_PENDING_TTL_SECONDS_YOOKASSA",
    )
    payment_pending_ttl_seconds_telegram_stars: int = Field(
        default=900,
        validation_alias="PAYMENT_PENDING_TTL_SECONDS_TELEGRAM_STARS",
    )
    payment_expire_stale_interval_seconds: int = Field(
        default=60,
        validation_alias="PAYMENT_EXPIRE_STALE_INTERVAL_SECONDS",
    )
    payment_reconcile_yookassa_interval_seconds: int = Field(
        default=120,
        validation_alias="PAYMENT_RECONCILE_YOOKASSA_INTERVAL_SECONDS",
    )
    payment_reconcile_wallet_grants_interval_seconds: int = Field(
        default=60,
        validation_alias="PAYMENT_RECONCILE_WALLET_GRANTS_INTERVAL_SECONDS",
    )
    payment_reconcile_yookassa_min_age_seconds: int = Field(
        default=180,
        validation_alias="PAYMENT_RECONCILE_YOOKASSA_MIN_AGE_SECONDS",
    )
    payment_jobs_batch_size: int = Field(
        default=100,
        validation_alias="PAYMENT_JOBS_BATCH_SIZE",
    )
    payment_job_lock_ttl_seconds: int = Field(
        default=60,
        validation_alias="PAYMENT_JOB_LOCK_TTL_SECONDS",
    )
    notification_telegram_delivery_interval_seconds: int = Field(
        default=30,
        validation_alias="NOTIFICATION_TELEGRAM_DELIVERY_INTERVAL_SECONDS",
    )
    notification_jobs_batch_size: int = Field(
        default=100,
        validation_alias="NOTIFICATION_JOBS_BATCH_SIZE",
    )
    notification_job_lock_ttl_seconds: int = Field(
        default=60,
        validation_alias="NOTIFICATION_JOB_LOCK_TTL_SECONDS",
    )
    notification_telegram_max_attempts: int = Field(
        default=5,
        validation_alias="NOTIFICATION_TELEGRAM_MAX_ATTEMPTS",
    )
    notification_telegram_retry_base_seconds: int = Field(
        default=30,
        validation_alias="NOTIFICATION_TELEGRAM_RETRY_BASE_SECONDS",
    )
    notification_telegram_retry_max_seconds: int = Field(
        default=900,
        validation_alias="NOTIFICATION_TELEGRAM_RETRY_MAX_SECONDS",
    )
    subscription_activation_no_connection_grace_seconds: int = Field(
        default=900,
        validation_alias="SUBSCRIPTION_ACTIVATION_NO_CONNECTION_GRACE_SECONDS",
    )
    broadcast_timezone: str = Field(
        default="Europe/Moscow",
        validation_alias="BROADCAST_TIMEZONE",
    )
    broadcast_scheduler_interval_seconds: int = Field(
        default=15,
        validation_alias="BROADCAST_SCHEDULER_INTERVAL_SECONDS",
    )
    broadcast_delivery_interval_seconds: int = Field(
        default=5,
        validation_alias="BROADCAST_DELIVERY_INTERVAL_SECONDS",
    )
    broadcast_jobs_batch_size: int = Field(
        default=100,
        validation_alias="BROADCAST_JOBS_BATCH_SIZE",
    )
    broadcast_job_lock_ttl_seconds: int = Field(
        default=60,
        validation_alias="BROADCAST_JOB_LOCK_TTL_SECONDS",
    )
    broadcast_telegram_max_attempts: int = Field(
        default=3,
        validation_alias="BROADCAST_TELEGRAM_MAX_ATTEMPTS",
    )
    broadcast_telegram_retry_base_seconds: int = Field(
        default=30,
        validation_alias="BROADCAST_TELEGRAM_RETRY_BASE_SECONDS",
    )
    broadcast_telegram_retry_max_seconds: int = Field(
        default=900,
        validation_alias="BROADCAST_TELEGRAM_RETRY_MAX_SECONDS",
    )

    # Auth
    jwt_secret: str = "change-me"
    jwt_access_token_expires_seconds: int = 3600
    admin_jwt_access_token_expires_seconds: int = Field(
        default=43200,
        validation_alias="ADMIN_JWT_ACCESS_TOKEN_EXPIRES_SECONDS",
    )
    admin_bootstrap_username: str = Field(
        default="", validation_alias="ADMIN_BOOTSTRAP_USERNAME"
    )
    admin_bootstrap_password: str = Field(
        default="", validation_alias="ADMIN_BOOTSTRAP_PASSWORD"
    )
    admin_bootstrap_email: str = Field(
        default="", validation_alias="ADMIN_BOOTSTRAP_EMAIL"
    )
    admin_bootstrap_full_name: str = Field(
        default="", validation_alias="ADMIN_BOOTSTRAP_FULL_NAME"
    )
    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_anon_key: str = Field(default="", validation_alias="SUPABASE_ANON_KEY")
    supabase_user_cache_ttl_seconds: int = Field(
        default=300, validation_alias="SUPABASE_USER_CACHE_TTL_SECONDS"
    )
    auth_token_cache_ttl_seconds: int = Field(
        default=300, validation_alias="AUTH_TOKEN_CACHE_TTL_SECONDS"
    )
    account_response_cache_ttl_seconds: int = Field(
        default=60, validation_alias="ACCOUNT_RESPONSE_CACHE_TTL_SECONDS"
    )

    # Telegram
    telegram_bot_token: str = Field(
        default="",
        validation_alias="BOT_TOKEN",
    )
    telegram_bot_username: str = Field(
        default="",
        validation_alias="BOT_USERNAME",
    )
    telegram_purchase_message_effect_id: str = Field(
        default="5159385139981059251",
        validation_alias="TELEGRAM_PURCHASE_MESSAGE_EFFECT_ID",
    )
    support_telegram_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SUPPORT_TELEGRAM_URL", "VITE_SUPPORT_TELEGRAM_URL"
        ),
    )
    telegram_init_data_ttl_seconds: int = 600
    webapp_url: str = Field(default="", validation_alias="WEBAPP_URL")
    bot_admin_ids: str = Field(default="", validation_alias="BOT_ADMIN_IDS")

    @property
    def bot_admin_id_list(self) -> tuple[int, ...]:
        return parse_bot_admin_ids(self.bot_admin_ids)


settings = Settings()
