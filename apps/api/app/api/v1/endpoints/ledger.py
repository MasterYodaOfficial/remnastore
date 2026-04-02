from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_account
from app.db.models import Account
from app.db.session import get_session
from app.schemas.ledger import LedgerEntryResponse, LedgerHistoryResponse
from app.services.ledger import get_account_ledger_history


router = APIRouter()


@router.get("/entries", response_model=LedgerHistoryResponse)
async def read_ledger_entries(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> LedgerHistoryResponse:
    entries, total = await get_account_ledger_history(
        session,
        account_id=current_account.id,
        limit=limit,
        offset=offset,
    )
    return LedgerHistoryResponse(
        items=[LedgerEntryResponse.model_validate(entry) for entry in entries],
        total=total,
        limit=limit,
        offset=offset,
    )
