from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_account
from app.core.audit import build_request_audit_context, log_audit_event
from app.db.models import Account
from app.db.session import get_session
from app.schemas.referral import (
    ReferralClaimRequest,
    ReferralClaimResponse,
    ReferralSummaryResponse,
)
from app.services.ledger import clear_account_cache
from app.services.referrals import (
    ReferralAlreadyAttributedError,
    ReferralAttributionWindowClosedError,
    ReferralCodeNotFoundError,
    ReferralSelfAttributionError,
    claim_referral_code,
    get_referral_summary,
)


router = APIRouter()


@router.get("/summary", response_model=ReferralSummaryResponse)
async def read_referral_summary(
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> ReferralSummaryResponse:
    summary = await get_referral_summary(session, account_id=current_account.id)
    return ReferralSummaryResponse.model_validate(summary, from_attributes=True)


@router.post("/claim", response_model=ReferralClaimResponse)
async def claim_referral(
    payload: ReferralClaimRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
) -> ReferralClaimResponse:
    request_context = build_request_audit_context(request)
    try:
        result = await claim_referral_code(
            session,
            account_id=current_account.id,
            referral_code=payload.referral_code,
        )
    except ReferralCodeNotFoundError as exc:
        log_audit_event(
            "referral.claim",
            outcome="failure",
            category="business",
            reason="referral_code_not_found",
            account_id=current_account.id,
            referral_code=payload.referral_code,
            **request_context,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ReferralSelfAttributionError as exc:
        log_audit_event(
            "referral.claim",
            outcome="failure",
            category="business",
            reason="self_referral",
            account_id=current_account.id,
            referral_code=payload.referral_code,
            **request_context,
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ReferralAlreadyAttributedError as exc:
        log_audit_event(
            "referral.claim",
            outcome="failure",
            category="business",
            reason="already_claimed",
            account_id=current_account.id,
            referral_code=payload.referral_code,
            **request_context,
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ReferralAttributionWindowClosedError as exc:
        log_audit_event(
            "referral.claim",
            outcome="failure",
            category="business",
            reason="window_closed",
            account_id=current_account.id,
            referral_code=payload.referral_code,
            **request_context,
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await session.commit()
    await clear_account_cache(current_account.id)
    await clear_account_cache(result.attribution.referrer_account_id)
    log_audit_event(
        "referral.claim",
        outcome="success",
        category="business",
        account_id=current_account.id,
        referrer_account_id=result.attribution.referrer_account_id,
        referral_code=result.attribution.referral_code,
        created=result.created,
        **request_context,
    )
    return ReferralClaimResponse(
        created=result.created,
        referred_by_account_id=result.attribution.referrer_account_id,
    )
