from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_account
from app.db.models import Account
from app.db.session import get_session
from app.schemas.withdrawal import (
    WithdrawalCreateRequest,
    WithdrawalListResponse,
    WithdrawalResponse,
)
from app.services.ledger import clear_account_cache
from app.services.withdrawals import (
    WithdrawalAccountBlockedError,
    WithdrawalAmountTooLowError,
    WithdrawalDestinationRequiredError,
    WithdrawalInvalidCardError,
    WithdrawalInsufficientAvailableError,
    create_withdrawal_request,
    get_account_withdrawals,
    get_minimum_withdrawal_amount_rub,
    get_withdrawal_availability,
    mask_withdrawal_destination_value,
)


router = APIRouter()


def _build_withdrawal_response(item) -> WithdrawalResponse:
    return WithdrawalResponse(
        id=item.id,
        amount=item.amount,
        destination_type=item.destination_type,
        destination_value=mask_withdrawal_destination_value(
            destination_type=item.destination_type,
            destination_value=item.destination_value,
        ),
        user_comment=item.user_comment,
        admin_comment=item.admin_comment,
        status=item.status,
        reserved_ledger_entry_id=item.reserved_ledger_entry_id,
        released_ledger_entry_id=item.released_ledger_entry_id,
        processed_at=item.processed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=WithdrawalListResponse)
async def read_withdrawals(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> WithdrawalListResponse:
    items, total = await get_account_withdrawals(
        session,
        account_id=current_account.id,
        limit=limit,
        offset=offset,
    )
    availability = await get_withdrawal_availability(session, account=current_account)
    return WithdrawalListResponse(
        items=[_build_withdrawal_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        available_for_withdraw=availability.available_for_withdraw,
        minimum_amount_rub=get_minimum_withdrawal_amount_rub(),
    )


@router.post("", response_model=WithdrawalResponse, status_code=status.HTTP_201_CREATED)
async def create_withdrawal(
    payload: WithdrawalCreateRequest,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> WithdrawalResponse:
    try:
        withdrawal = await create_withdrawal_request(
            session,
            account_id=current_account.id,
            amount=payload.amount,
            destination_type=payload.destination_type,
            destination_value=payload.destination_value,
            user_comment=payload.user_comment,
        )
    except WithdrawalDestinationRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except WithdrawalInvalidCardError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except WithdrawalAmountTooLowError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except WithdrawalInsufficientAvailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except WithdrawalAccountBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    await session.commit()
    await session.refresh(withdrawal)
    await clear_account_cache(current_account.id)
    return _build_withdrawal_response(withdrawal)
