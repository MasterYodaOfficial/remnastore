from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin
from app.db.models import Admin
from app.db.session import get_session
from app.schemas.admin import AdminDashboardSummaryResponse
from app.services.admin_dashboard import get_admin_dashboard_summary


router = APIRouter()


@router.get("/summary", response_model=AdminDashboardSummaryResponse)
async def read_admin_dashboard_summary(
    session: AsyncSession = Depends(get_session),
    _: Admin = Depends(get_current_admin),
) -> AdminDashboardSummaryResponse:
    return AdminDashboardSummaryResponse(**(await get_admin_dashboard_summary(session)))
