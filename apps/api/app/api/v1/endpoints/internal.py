from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_internal_api_token
from app.db.models import AccountStatus
from app.db.session import get_session
from app.schemas.internal import TelegramAccountAccessResponse
from app.services.accounts import get_account_by_telegram_id

router = APIRouter()


@router.get("/telegram-accounts/{telegram_id}/access", response_model=TelegramAccountAccessResponse)
async def read_telegram_account_access(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> TelegramAccountAccessResponse:
    verify_internal_api_token(authorization)
    account = await get_account_by_telegram_id(session, telegram_id=telegram_id)
    if account is None:
        return TelegramAccountAccessResponse(
            telegram_id=telegram_id,
            exists=False,
            status=None,
            fully_blocked=False,
        )

    return TelegramAccountAccessResponse(
        telegram_id=telegram_id,
        exists=True,
        status=account.status,
        fully_blocked=account.status == AccountStatus.BLOCKED,
    )
