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
    trial_duration_days: int = 3
    yookassa_shop_id: str = Field(default="", validation_alias="YOOKASSA_SHOP_ID")
    yookassa_secret_key: str = Field(default="", validation_alias="YOOKASSA_SECRET_KEY")
    yookassa_api_url: str = Field(
        default="https://api.yookassa.ru/v3",
        validation_alias="YOOKASSA_API_URL",
    )
    yookassa_verify_tls: bool = Field(default=True, validation_alias="YOOKASSA_VERIFY_TLS")
    api_token: str = Field(default="", validation_alias="API_TOKEN")

    # Auth
    jwt_secret: str = "change-me"
    jwt_access_token_expires_seconds: int = 3600
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
