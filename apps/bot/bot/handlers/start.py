from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart
from aiogram.types import Message
import httpx

from bot.core.config import settings
from bot.services.api import ApiClient
from bot.services.i18n import translate
from bot.services.menu_renderer import show_menu_for_message
from bot.states.menu import MenuState

router = Router()
REFERRAL_START_PREFIX = "ref_"


def build_api_headers() -> dict[str, str]:
    token = settings.api_token.strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    """Handle /start command with optional linking token parameter."""
    api_client = ApiClient()
    if message.from_user is not None:
        if await api_client.is_telegram_account_fully_blocked(telegram_id=message.from_user.id):
            return
        await api_client.mark_telegram_account_reachable(telegram_id=message.from_user.id)

    args = message.text.split(maxsplit=1)

    # Check if there's a linking token parameter
    if len(args) > 1:
        start_param = args[1].strip()

        # Handle browser linking token (from OAuth to Telegram)
        if start_param.startswith("link_") and "_BROWSER" in start_param:
            await handle_browser_link(message, start_param)
            await state.set_state(MenuState.idle)
            await show_menu_for_message(message)
            return

        # Handle Telegram linking token (from Telegram to OAuth)
        if start_param.startswith("link_"):
            await handle_telegram_link(message, start_param)
            await state.set_state(MenuState.idle)
            await show_menu_for_message(message)
            return

        if start_param.startswith(REFERRAL_START_PREFIX):
            referral_code = start_param.removeprefix(REFERRAL_START_PREFIX).strip()
            await handle_referral_start(message, referral_code)
            await state.set_state(MenuState.idle)
            return

    # Regular start without parameters
    await state.set_state(MenuState.idle)
    await show_menu_for_message(message)


async def handle_browser_link(message: Message, link_token: str) -> None:
    """Handle linking browser OAuth account to Telegram account."""
    locale = message.from_user.language_code if message.from_user is not None else None
    try:
        telegram_id = message.from_user.id

        # Call API to consume link token and bind accounts
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.api_url}/api/v1/accounts/link-browser-confirm",
                json={"link_token": link_token, "telegram_id": telegram_id},
                headers=build_api_headers(),
                timeout=10.0,
            )

        if response.status_code == 200:
            await message.answer(
                translate("bot.linking.success", locale=locale)
            )
        elif response.status_code == 400:
            error_data = response.json()
            await message.answer(
                translate(
                    "bot.linking.error_with_detail",
                    locale=locale,
                    detail=error_data.get("detail", translate("common.errors.unknown", locale=locale)),
                )
            )
        else:
            await message.answer(
                translate("bot.linking.generic_error", locale=locale)
            )
    except Exception as e:
        await message.answer(
            translate("bot.linking.exception_error", locale=locale, error=str(e))
        )


async def handle_telegram_link(message: Message, link_token: str) -> None:
    """Handle linking Telegram to browser OAuth account."""
    locale = message.from_user.language_code if message.from_user is not None else None
    try:
        telegram_id = message.from_user.id
        first_name = message.from_user.first_name or ""
        last_name = message.from_user.last_name or ""
        username = message.from_user.username or ""
        is_premium = message.from_user.is_premium or False

        # Call API to consume link token and bind accounts
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.api_url}/api/v1/accounts/link-telegram-confirm",
                json={
                    "link_token": link_token,
                    "telegram_id": telegram_id,
                    "first_name": first_name,
                    "last_name": last_name,
                    "username": username,
                    "is_premium": is_premium,
                },
                headers=build_api_headers(),
                timeout=10.0,
            )

        if response.status_code == 200:
            await message.answer(
                translate("bot.linking.success", locale=locale)
            )
        elif response.status_code == 400:
            error_data = response.json()
            await message.answer(
                translate(
                    "bot.linking.error_with_detail",
                    locale=locale,
                    detail=error_data.get("detail", translate("common.errors.unknown", locale=locale)),
                )
            )
        else:
            await message.answer(
                translate("bot.linking.generic_error", locale=locale)
            )
    except Exception as e:
        await message.answer(
            translate("bot.linking.exception_error", locale=locale, error=str(e))
        )


async def handle_referral_start(message: Message, referral_code: str) -> None:
    """Handle referral deep link and preserve the code in the WebApp URL."""
    locale = message.from_user.language_code if message.from_user is not None else None
    if not referral_code:
        await message.answer(translate("bot.referral.invalid_link", locale=locale))
        await show_menu_for_message(message)
        return

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.api_url}/api/v1/webhooks/referrals/telegram-start",
                json={
                    "telegram_id": message.from_user.id,
                    "referral_code": referral_code,
                },
                headers=build_api_headers(),
                timeout=10.0,
            )

        if response.status_code == 400:
            await message.answer(translate("bot.referral.invalid_code", locale=locale))
            await show_menu_for_message(message)
            return
    except Exception:
        pass

    await message.answer(translate("bot.referral.saved", locale=locale))
    await show_menu_for_message(message, referral_code=referral_code)
