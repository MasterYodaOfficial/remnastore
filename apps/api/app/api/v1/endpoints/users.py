from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_account
from app.db.models import Account

router = APIRouter()


@router.get("/me")
async def me(current_account: Account = Depends(get_current_account)) -> dict:
    return {"id": str(current_account.id), "telegram_id": current_account.telegram_id}
