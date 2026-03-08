import asyncio
from contextlib import asynccontextmanager
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, Update
from aiogram.exceptions import TelegramRetryAfter
from fastapi import FastAPI, HTTPException, Request, Response
from uvicorn import Config, Server

from bot.core.config import settings
from bot.core.logging import configure_logging
from bot.handlers import start, webapp


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(webapp.router)
    return dp


async def on_startup(bot: Bot) -> None:
    if settings.bot_use_webhook:
        if not settings.bot_webhook_base_url:
            raise RuntimeError("BOT_WEBHOOK_BASE_URL is required when BOT_USE_WEBHOOK=true")
        await ensure_webhook(bot)
    await bot.set_my_commands([BotCommand(command="start", description="Начать работу")])


async def on_shutdown(bot: Bot) -> None:
    if settings.bot_use_webhook:
        await bot.delete_webhook(drop_pending_updates=True)
    await bot.session.close()


async def ensure_webhook(bot: Bot, max_attempts: int = 5) -> None:
    target_url = f"{settings.bot_webhook_base_url}{settings.bot_webhook_path}"
    secret = settings.bot_webhook_secret or None

    info = await bot.get_webhook_info()
    if info.url == target_url and (not secret or info.has_custom_certificate or True):
        # URL уже установлен; не дёргаем API лишний раз
        return

    delay = 1
    for attempt in range(1, max_attempts + 1):
        try:
            await bot.set_webhook(target_url, secret_token=secret)
            return
        except TelegramRetryAfter as exc:
            if attempt == max_attempts:
                raise
            await asyncio.sleep(exc.retry_after + 0.5)
        except Exception:
            if attempt == max_attempts:
                raise
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10)


def create_fastapi_app(bot: Bot, dp: Dispatcher) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await dp.emit_startup(bot=bot)
        try:
            yield
        finally:
            await dp.emit_shutdown(bot=bot)

    app = FastAPI(title="Bot Webhook", lifespan=lifespan)

    @app.post(settings.bot_webhook_path)
    async def telegram_webhook(request: Request) -> Response:
        if settings.bot_webhook_secret:
            header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if header_secret != settings.bot_webhook_secret:
                raise HTTPException(status_code=401, detail="invalid secret token")

        data: Any = await request.json()
        update = Update.model_validate(data)
        await dp.feed_update(bot, update)
        return Response(status_code=200)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


async def main() -> None:
    configure_logging()
    bot = Bot(token=settings.bot_token)
    dp = create_dispatcher()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    if settings.bot_use_webhook:
        app = create_fastapi_app(bot, dp)
        config = Config(
            app=app,
            host=settings.bot_web_server_host,
            port=settings.bot_web_server_port,
            log_config=None,  # logging already configured
            loop="asyncio",
        )
        server = Server(config)
        await server.serve()
    else:
        try:
            await dp.start_polling(bot)
        finally:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
