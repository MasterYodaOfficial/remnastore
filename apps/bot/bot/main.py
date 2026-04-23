import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from typing import Any

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, Update
from fastapi import FastAPI, HTTPException, Request, Response
from redis.asyncio import Redis
from uvicorn import Config, Server

from bot.core.config import settings
from bot.core.logging import configure_logging
from bot.handlers import admin, menu, payments, start, webapp
from bot.services.i18n import translate
from bot.services.media_registry import get_media_registry
from bot.services.session_store import close_menu_session_store

try:
    from aiogram.fsm.storage.redis import RedisStorage
except ImportError:  # pragma: no cover - fallback for minimal environments
    RedisStorage = None


logger = logging.getLogger(__name__)


class WebhookModeSetupError(RuntimeError):
    """Raised when webhook mode cannot be started safely."""


def create_dispatcher() -> Dispatcher:
    storage = MemoryStorage()
    if settings.redis_url.strip() and RedisStorage is not None:
        storage = RedisStorage(redis=Redis.from_url(settings.redis_url.strip()))

    dp = Dispatcher(storage=storage)
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(menu.router)
    dp.include_router(payments.router)
    dp.include_router(webapp.router)
    return dp


def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_runtime() -> tuple[Bot, Dispatcher]:
    bot = create_bot()
    dp = create_dispatcher()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    return bot, dp


async def on_startup(bot: Bot) -> None:
    await bot.set_my_commands(_build_default_commands())
    if not settings.bot_admin_id_list:
        return

    bot_info = await bot.get_me()
    if bot_info.id in settings.bot_admin_id_list:
        logger.warning(
            "BOT_ADMIN_IDS contains the current bot id; use Telegram user ids for admin access",
            extra={
                "bot_id": bot_info.id,
                "admin_ids_count": len(settings.bot_admin_id_list),
            },
        )

    admin_commands = _build_admin_commands()
    for admin_id in settings.bot_admin_id_list:
        await bot.set_my_commands(
            admin_commands,
            scope=BotCommandScopeChat(chat_id=admin_id),
        )
    logger.info(
        "Configured scoped admin commands",
        extra={"admin_ids_count": len(settings.bot_admin_id_list)},
    )


def _build_default_commands() -> list[BotCommand]:
    return [
        BotCommand(
            command="start",
            description=translate("bot.commands.start_description"),
        )
    ]


def _build_admin_commands() -> list[BotCommand]:
    return [
        BotCommand(
            command="start",
            description=translate("bot.commands.start_description"),
        ),
        BotCommand(
            command="master",
            description=translate("bot.commands.master_description"),
        ),
    ]


async def on_shutdown(bot: Bot) -> None:
    if settings.bot_use_webhook:
        await ensure_webhook_removed(bot, drop_pending_updates=True)
    await close_menu_session_store()
    await get_media_registry().close()
    await bot.session.close()


def get_webhook_target_url() -> str:
    base_url = settings.bot_webhook_base_url.strip().rstrip("/")
    webhook_path = settings.bot_webhook_path.strip() or "/bot/webhook"
    if not webhook_path.startswith("/"):
        webhook_path = f"/{webhook_path}"
    return f"{base_url}{webhook_path}"


def get_local_bot_healthcheck_url() -> str:
    host = settings.bot_web_server_host.strip() or "127.0.0.1"
    if host in {"0.0.0.0", "::", "[::]"}:
        host = "127.0.0.1"
    elif ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{settings.bot_web_server_port}/health"


async def ensure_webhook(bot: Bot, dp: Dispatcher) -> None:
    target_url = get_webhook_target_url()
    secret = settings.bot_webhook_secret or None
    ip_address = settings.bot_webhook_ip_address or None
    request_timeout = settings.bot_webhook_setup_timeout_seconds
    max_attempts = settings.bot_webhook_setup_max_attempts
    allowed_updates = dp.resolve_used_update_types()
    delay = 1
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            await bot.set_webhook(
                target_url,
                ip_address=ip_address,
                allowed_updates=allowed_updates,
                secret_token=secret,
                request_timeout=request_timeout,
            )
            logger.info(
                "Telegram webhook configured",
                extra={
                    "target_url": target_url,
                    "ip_address": ip_address or "-",
                    "allowed_updates_count": len(allowed_updates),
                },
            )
            return
        except TelegramRetryAfter as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            logger.warning(
                "Telegram asked to retry webhook setup later",
                extra={
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "retry_after": exc.retry_after,
                },
            )
            await asyncio.sleep(exc.retry_after + 0.5)
        except Exception as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            logger.warning(
                "Telegram webhook setup attempt failed",
                exc_info=exc,
                extra={"attempt": attempt, "max_attempts": max_attempts},
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10)

    webhook_info = None
    with suppress(Exception):
        webhook_info = await bot.get_webhook_info(request_timeout=request_timeout)

    raise RuntimeError(
        "Unable to configure Telegram webhook"
        + (
            f": {webhook_info.last_error_message}"
            if webhook_info is not None and webhook_info.last_error_message
            else ""
        )
    ) from last_error


async def ensure_webhook_removed(bot: Bot, *, drop_pending_updates: bool) -> bool:
    request_timeout = settings.bot_webhook_setup_timeout_seconds
    max_attempts = settings.bot_webhook_setup_max_attempts
    delay = 1

    for attempt in range(1, max_attempts + 1):
        try:
            await bot.delete_webhook(
                drop_pending_updates=drop_pending_updates,
                request_timeout=request_timeout,
            )
            return True
        except TelegramRetryAfter as exc:
            if attempt == max_attempts:
                break
            await asyncio.sleep(exc.retry_after + 0.5)
        except Exception as exc:
            if attempt == max_attempts:
                logger.warning(
                    "Unable to remove Telegram webhook cleanly",
                    exc_info=exc,
                    extra={
                        "drop_pending_updates": drop_pending_updates,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                    },
                )
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10)

    logger.warning(
        "Telegram webhook removal was not confirmed",
        extra={"drop_pending_updates": drop_pending_updates},
    )
    return False


async def wait_for_bot_health(server_task: asyncio.Task[None]) -> None:
    health_url = get_local_bot_healthcheck_url()
    timeout_seconds = settings.bot_webhook_setup_timeout_seconds
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last_error: Exception | None = None

    while asyncio.get_running_loop().time() < deadline:
        if server_task.done():
            try:
                await server_task
            except Exception as exc:  # pragma: no cover - surfaced to caller
                raise RuntimeError(
                    "Bot webhook server exited before passing health checks"
                ) from exc
            raise RuntimeError("Bot webhook server stopped before becoming healthy")

        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(health_url)
            if response.status_code == 200:
                return
            last_error = RuntimeError(
                f"Unexpected bot health status: {response.status_code}"
            )
        except httpx.HTTPError as exc:
            last_error = exc

        await asyncio.sleep(0.5)

    raise RuntimeError(
        f"Bot webhook server did not become healthy within {timeout_seconds}s"
    ) from last_error


async def stop_webhook_server(server: Server, server_task: asyncio.Task[None]) -> None:
    if not server_task.done():
        server.should_exit = True
    with suppress(Exception):
        await server_task


async def run_polling_mode(
    bot: Bot, dp: Dispatcher, *, clear_existing_webhook: bool
) -> None:
    if clear_existing_webhook:
        webhook_removed = await ensure_webhook_removed(bot, drop_pending_updates=False)
        if not webhook_removed:
            logger.warning(
                "Starting polling without confirmed webhook removal",
            )

    logger.info(
        "Starting bot in polling mode",
        extra={"webhook_fallback": clear_existing_webhook},
    )
    await dp.start_polling(bot, close_bot_session=False)


async def run_webhook_mode(bot: Bot, dp: Dispatcher) -> None:
    server: Server | None = None
    server_task: asyncio.Task[None] | None = None

    try:
        app = create_fastapi_app(bot, dp)
        config = Config(
            app=app,
            host=settings.bot_web_server_host,
            port=settings.bot_web_server_port,
            log_config=None,  # logging already configured
            loop="asyncio",
        )
        server = Server(config)
        server_task = asyncio.create_task(server.serve())
        await wait_for_bot_health(server_task)
        await ensure_webhook(bot, dp)
    except Exception as exc:
        if server is not None and server_task is not None:
            await stop_webhook_server(server, server_task)
        raise WebhookModeSetupError("Webhook mode startup failed") from exc

    logger.info(
        "Starting bot in webhook mode",
        extra={"webhook_url": get_webhook_target_url()},
    )
    assert server_task is not None
    await server_task


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


async def run_bot() -> str:
    if settings.bot_use_webhook:
        bot, dp = build_runtime()
        try:
            await run_webhook_mode(bot, dp)
            return "webhook"
        except WebhookModeSetupError as exc:
            if not settings.bot_webhook_fallback_to_polling:
                raise
            logger.warning(
                "Webhook mode setup failed, switching bot to polling",
                extra={"reason": str(exc)},
            )

    bot, dp = build_runtime()
    await run_polling_mode(
        bot,
        dp,
        clear_existing_webhook=settings.bot_use_webhook,
    )
    return "polling"


async def main() -> None:
    configure_logging(component_name="bot")
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
