from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import api_error_from_exception
from app.api.dependencies import get_current_admin
from app.core.audit import build_request_audit_context, log_audit_event
from app.core.config import settings
from app.core.security import create_access_token
from app.db.models import Admin
from app.db.session import get_session
from app.schemas.admin import AdminAuthResponse, AdminLoginRequest, AdminResponse
from app.services.admin_auth import AdminInvalidCredentialsError, authenticate_admin
from app.services.i18n import translate


router = APIRouter()


@router.post("/login", response_model=AdminAuthResponse)
async def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AdminAuthResponse:
    request_context = build_request_audit_context(request)
    normalized_login = payload.login.strip().lower()
    try:
        admin = await authenticate_admin(
            session,
            login=payload.login,
            password=payload.password,
        )
    except AdminInvalidCredentialsError as exc:
        log_audit_event(
            "admin.login",
            outcome="failure",
            category="security",
            reason="invalid_credentials",
            login=normalized_login,
            **request_context,
        )
        exc.args = (translate("api.admin.errors.invalid_credentials"),)
        raise api_error_from_exception(status.HTTP_401_UNAUTHORIZED, exc) from exc

    admin.last_login_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(admin)
    log_audit_event(
        "admin.login",
        outcome="success",
        category="security",
        admin_id=admin.id,
        username=admin.username,
        login=normalized_login,
        **request_context,
    )

    token = create_access_token(
        {"sub": str(admin.id), "scope": "admin"},
        secret=settings.jwt_secret,
        expires_in_seconds=settings.admin_jwt_access_token_expires_seconds,
    )
    return AdminAuthResponse(
        access_token=token,
        admin=AdminResponse.model_validate(admin, from_attributes=True),
    )


@router.get("/me", response_model=AdminResponse)
async def read_current_admin(
    current_admin: Admin = Depends(get_current_admin),
) -> AdminResponse:
    return AdminResponse.model_validate(current_admin, from_attributes=True)
