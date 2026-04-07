import re

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_WEBHOOK_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "remnastore-bot"
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_format: str = Field(default="text", validation_alias="LOG_FORMAT")
    log_to_file: bool = Field(default=False, validation_alias="LOG_TO_FILE")
    log_dir: str = Field(default="./.logs", validation_alias="LOG_DIR")
    log_file_max_bytes: int = Field(
        default=10 * 1024 * 1024, validation_alias="LOG_FILE_MAX_BYTES"
    )
    log_file_backup_count: int = Field(
        default=5, validation_alias="LOG_FILE_BACKUP_COUNT"
    )
    bot_token: str = ""
    bot_admin_ids: str = ""
    api_url: str = ""
    api_token: str = ""
    webapp_url: str = ""
    telegram_purchase_message_effect_id: str = Field(
        default="5159385139981059251",
        validation_alias="TELEGRAM_PURCHASE_MESSAGE_EFFECT_ID",
    )
    redis_url: str = Field(default="", validation_alias="REDIS_URL")
    bot_use_webhook: bool = False
    bot_webhook_base_url: str = ""
    bot_webhook_path: str = "/bot/webhook"
    bot_webhook_secret: str = ""
    bot_webhook_ip_address: str = ""
    bot_web_server_host: str = "0.0.0.0"
    bot_web_server_port: int = 8080
    bot_webhook_setup_max_attempts: int = 5
    bot_webhook_setup_timeout_seconds: int = 20
    bot_webhook_fallback_to_polling: bool = True
    bot_locales_dir: str = ""
    bot_assets_dir: str = ""
    bot_help_telegram_url: str = ""
    support_telegram_url: str = Field(
        default="", validation_alias="VITE_SUPPORT_TELEGRAM_URL"
    )
    bot_menu_session_ttl_seconds: int = 60 * 60 * 24 * 30
    bot_callback_lock_ttl_seconds: int = 5

    @field_validator("bot_webhook_base_url", mode="before")
    @classmethod
    def normalize_bot_webhook_base_url(cls, value: object) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip().rstrip("/")

    @field_validator("bot_webhook_path", mode="before")
    @classmethod
    def normalize_bot_webhook_path(cls, value: object) -> str:
        if not isinstance(value, str):
            return "/bot/webhook"
        normalized = value.strip()
        if not normalized:
            return "/bot/webhook"
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized

    @field_validator("bot_webhook_secret", mode="before")
    @classmethod
    def validate_bot_webhook_secret(cls, value: object) -> str:
        if not isinstance(value, str):
            return ""
        normalized = value.strip()
        if not normalized:
            return ""
        if not _WEBHOOK_SECRET_RE.fullmatch(normalized):
            raise ValueError(
                "BOT_WEBHOOK_SECRET must match Telegram requirements: "
                "1-256 chars, only letters, digits, underscores, hyphens"
            )
        return normalized

    @field_validator("bot_webhook_ip_address", mode="before")
    @classmethod
    def normalize_bot_webhook_ip_address(cls, value: object) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip()

    @field_validator("bot_webhook_setup_max_attempts")
    @classmethod
    def validate_bot_webhook_setup_max_attempts(cls, value: int) -> int:
        if value < 1:
            raise ValueError("BOT_WEBHOOK_SETUP_MAX_ATTEMPTS must be >= 1")
        return value

    @field_validator("bot_webhook_setup_timeout_seconds")
    @classmethod
    def validate_bot_webhook_setup_timeout_seconds(cls, value: int) -> int:
        if value < 1:
            raise ValueError("BOT_WEBHOOK_SETUP_TIMEOUT_SECONDS must be >= 1")
        return value

    @model_validator(mode="after")
    def validate_webhook_mode(self) -> "Settings":
        if self.bot_use_webhook:
            if not self.bot_webhook_base_url:
                raise ValueError(
                    "BOT_WEBHOOK_BASE_URL is required when BOT_USE_WEBHOOK=true"
                )
            if not self.bot_webhook_base_url.startswith("https://"):
                raise ValueError(
                    "BOT_WEBHOOK_BASE_URL must use https:// when BOT_USE_WEBHOOK=true"
                )
        return self


settings = Settings()
