from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "remnastore-bot"
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_format: str = Field(default="text", validation_alias="LOG_FORMAT")
    log_to_file: bool = Field(default=False, validation_alias="LOG_TO_FILE")
    log_dir: str = Field(default="./.logs", validation_alias="LOG_DIR")
    log_file_max_bytes: int = Field(default=10 * 1024 * 1024, validation_alias="LOG_FILE_MAX_BYTES")
    log_file_backup_count: int = Field(default=5, validation_alias="LOG_FILE_BACKUP_COUNT")
    bot_token: str = ""
    bot_admin_ids: str = ""
    api_url: str = ""
    api_token: str = ""
    webapp_url: str = ""
    redis_url: str = Field(default="", validation_alias="REDIS_URL")
    bot_use_webhook: bool = False
    bot_webhook_base_url: str = ""
    bot_webhook_path: str = "/bot/webhook"
    bot_webhook_secret: str = ""
    bot_web_server_host: str = "0.0.0.0"
    bot_web_server_port: int = 8080
    bot_locales_dir: str = ""
    bot_assets_dir: str = ""
    bot_help_telegram_url: str = ""
    support_telegram_url: str = Field(default="", validation_alias="VITE_SUPPORT_TELEGRAM_URL")
    bot_menu_session_ttl_seconds: int = 60 * 60 * 24 * 30
    bot_callback_lock_ttl_seconds: int = 5


settings = Settings()
