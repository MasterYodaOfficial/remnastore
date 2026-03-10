from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    bot_admin_ids: str = ""
    api_url: str = ""
    api_token: str = ""
    webapp_url: str = ""
    bot_use_webhook: bool = False
    bot_webhook_base_url: str = ""
    bot_webhook_path: str = "/bot/webhook"
    bot_webhook_secret: str = ""
    bot_web_server_host: str = "0.0.0.0"
    bot_web_server_port: int = 8080


settings = Settings()
