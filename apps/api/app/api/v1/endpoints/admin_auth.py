from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin
from app.core.config import settings
from app.core.security import create_access_token
from app.db.models import Admin
from app.db.session import get_session
from app.schemas.admin import AdminAuthResponse, AdminLoginRequest, AdminResponse
from app.services.admin_auth import AdminInvalidCredentialsError, authenticate_admin


router = APIRouter()


@router.post("/login", response_model=AdminAuthResponse)
async def admin_login(
    payload: AdminLoginRequest,
    session: AsyncSession = Depends(get_session),
) -> AdminAuthResponse:
    try:
        admin = await authenticate_admin(
            session,
            login=payload.login,
            password=payload.password,
        )
    except AdminInvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    admin.last_login_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(admin)

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
