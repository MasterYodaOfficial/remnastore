from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": settings.app_version,
        "revision": settings.app_revision,
    }
