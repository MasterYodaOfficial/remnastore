from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import api_error, api_error_from_exception
from app.api.dependencies import get_current_admin
from app.db.models import Admin, Withdrawal
from app.db.models.withdrawal import WithdrawalStatus
from app.db.session import get_session
from app.schemas.admin import (
    AdminWithdrawalQueueItemResponse,
    AdminWithdrawalQueueResponse,
    AdminWithdrawalStatusChangeRequest,
    AdminWithdrawalStatusChangeResponse,
)
from app.services.admin_withdrawals import (
    AdminWithdrawalCommentRequiredError,
    AdminWithdrawalConflictError,
    AdminWithdrawalInvalidStatusError,
    change_admin_withdrawal_status,
    list_admin_withdrawals,
)
from app.services.i18n import translate

router = APIRouter()


@router.get("", response_model=AdminWithdrawalQueueResponse)
async def read_admin_withdrawals(
    status_filter: list[WithdrawalStatus] | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminWithdrawalQueueResponse:
    items, total = await list_admin_withdrawals(
        session,
        limit=limit,
        offset=offset,
        statuses=tuple(status_filter or ()),
    )
    return AdminWithdrawalQueueResponse(
        items=[
            AdminWithdrawalQueueItemResponse.model_validate(item, from_attributes=True)
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{withdrawal_id}/status", response_model=AdminWithdrawalStatusChangeResponse
)
async def change_withdrawal_status(
    withdrawal_id: int,
    payload: AdminWithdrawalStatusChangeRequest,
    session: AsyncSession = Depends(get_session),
    current_admin: Admin = Depends(get_current_admin),
) -> AdminWithdrawalStatusChangeResponse:
    withdrawal = await session.get(Withdrawal, withdrawal_id)
    if withdrawal is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            translate("api.admin.errors.withdrawal_not_found"),
            error_code="admin_withdrawal_not_found",
        )

    try:
        result = await change_admin_withdrawal_status(
            session,
            withdrawal_id=withdrawal_id,
            admin_id=current_admin.id,
            target_status=payload.status,
            comment=payload.comment,
            idempotency_key=payload.idempotency_key,
        )
    except AdminWithdrawalCommentRequiredError as exc:
        exc.args = (translate("api.admin.errors.withdrawal_comment_required"),)
        raise api_error_from_exception(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            exc,
        ) from exc
    except AdminWithdrawalInvalidStatusError as exc:
        exc.args = (translate("api.admin.errors.withdrawal_invalid_status"),)
        raise api_error_from_exception(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            exc,
        ) from exc
    except AdminWithdrawalConflictError as exc:
        exc.args = (translate("api.admin.errors.withdrawal_conflict"),)
        raise api_error_from_exception(
            status.HTTP_409_CONFLICT,
            exc,
        ) from exc

    return AdminWithdrawalStatusChangeResponse(
        withdrawal_id=result.withdrawal.id,
        account_id=result.withdrawal.account_id,
        previous_status=result.previous_status,
        status=result.withdrawal.status,
        admin_comment=result.withdrawal.admin_comment,
        processed_at=result.withdrawal.processed_at,
        released_ledger_entry_id=result.withdrawal.released_ledger_entry_id,
        audit_log_id=result.audit_log.id,
    )
