from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "remnastore-api"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    database_url: str = ""
    redis_url: str = ""

    remnawave_api_url: str = ""
    remnawave_api_token: str = ""
    remnawave_webhook_secret: str = ""
    remnawave_username_prefix: str = ""
    remnawave_user_label: str = ""
    remnawave_default_internal_squad_uuid: str = ""
    remnawave_default_internal_squad_name: str = ""
    trial_duration_days: int = 3
    default_referral_reward_rate: float = 20.0
    min_withdrawal_amount_rub: int = 300
    yookassa_shop_id: str = Field(default="", validation_alias="YOOKASSA_SHOP_ID")
    yookassa_secret_key: str = Field(default="", validation_alias="YOOKASSA_SECRET_KEY")
    yookassa_api_url: str = Field(
        default="https://api.yookassa.ru/v3",
        validation_alias="YOOKASSA_API_URL",
    )
    yookassa_verify_tls: bool = Field(default=True, validation_alias="YOOKASSA_VERIFY_TLS")
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
    admin_bootstrap_username: str = Field(default="", validation_alias="ADMIN_BOOTSTRAP_USERNAME")
    admin_bootstrap_password: str = Field(default="", validation_alias="ADMIN_BOOTSTRAP_PASSWORD")
    admin_bootstrap_email: str = Field(default="", validation_alias="ADMIN_BOOTSTRAP_EMAIL")
    admin_bootstrap_full_name: str = Field(default="", validation_alias="ADMIN_BOOTSTRAP_FULL_NAME")
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
    telegram_init_data_ttl_seconds: int = 600
    webapp_url: str = Field(default="", validation_alias="WEBAPP_URL")


settings = Settings()
