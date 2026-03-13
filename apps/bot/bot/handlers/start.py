from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
import httpx

from bot.keyboards.main import main_menu
from bot.core.config import settings
from bot.services.api import ApiClient

router = Router()
REFERRAL_START_PREFIX = "ref_"


def build_api_headers() -> dict[str, str]:
    token = settings.api_token.strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    """Handle /start command with optional linking token parameter."""
    if message.from_user is not None:
        if await ApiClient().is_telegram_account_fully_blocked(telegram_id=message.from_user.id):
            return

    args = message.text.split(maxsplit=1)

    # Check if there's a linking token parameter
    if len(args) > 1:
        start_param = args[1].strip()

        # Handle browser linking token (from OAuth to Telegram)
        if start_param.startswith("link_") and "_BROWSER" in start_param:
            await handle_browser_link(message, start_param)
            return

        # Handle Telegram linking token (from Telegram to OAuth)
        if start_param.startswith("link_"):
            await handle_telegram_link(message, start_param)
            return

        if start_param.startswith(REFERRAL_START_PREFIX):
            referral_code = start_param.removeprefix(REFERRAL_START_PREFIX).strip()
            await handle_referral_start(message, referral_code)
            return

    # Regular start without parameters
    try:
        await message.answer(
            "Добро пожаловать! Откройте витрину через кнопку ниже.",
            reply_markup=main_menu(),
        )
    except TelegramBadRequest:
        await message.answer("Добро пожаловать! Кнопка недоступна, проверьте конфигурацию WebApp URL.")


async def handle_browser_link(message: Message, link_token: str) -> None:
    """Handle linking browser OAuth account to Telegram account."""
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
                "✅ Ваш Telegram аккаунт успешно привязан к браузер-аккаунту!\n\n"
                "Теперь вы можете использовать оба способа входа."
            )
        elif response.status_code == 400:
            error_data = response.json()
            await message.answer(
                f"❌ Ошибка: {error_data.get('detail', 'Неизвестная ошибка')}\n\n"
                "Проверьте ссылку или создайте новую."
            )
        else:
            await message.answer(
                "❌ Ошибка при привязке. Попробуйте снова позже."
            )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при привязке: {str(e)}"
        )


async def handle_telegram_link(message: Message, link_token: str) -> None:
    """Handle linking Telegram to browser OAuth account."""
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
                "✅ Ваш Telegram аккаунт успешно привязан к браузер-аккаунту!\n\n"
                "Теперь вы можете использовать оба способа входа."
            )
        elif response.status_code == 400:
            error_data = response.json()
            await message.answer(
                f"❌ Ошибка: {error_data.get('detail', 'Неизвестная ошибка')}\n\n"
                "Проверьте ссылку или создайте новую."
            )
        else:
            await message.answer(
                "❌ Ошибка при привязке. Попробуйте снова позже."
            )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при привязке: {str(e)}"
        )


async def handle_referral_start(message: Message, referral_code: str) -> None:
    """Handle referral deep link and preserve the code in the WebApp URL."""
    if not referral_code:
        await message.answer(
            "Ссылка приглашения повреждена. Откройте приложение через кнопку ниже.",
            reply_markup=main_menu(),
        )
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
            await message.answer("Реферальная ссылка недействительна. Попросите отправить новую.")
            return
    except Exception:
        pass

    try:
        await message.answer(
            "Вы открыли приглашение. Нажмите кнопку ниже, чтобы открыть витрину и завершить вход с сохранением реферальной ссылки.",
            reply_markup=main_menu(referral_code=referral_code),
        )
    except TelegramBadRequest:
        await message.answer(
            "Не удалось показать кнопку открытия приложения. Проверьте настройку WebApp URL."
        )
