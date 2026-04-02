from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import (
    ApiError,
    api_error_handler,
    request_validation_error_handler,
)
from app.api.v1.endpoints.webhooks import router as public_webhooks_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import SessionLocal
from app.middleware.request_context import register_request_context_middleware
from app.services.admin_auth import ensure_bootstrap_admin
from app.services.cache import get_cache


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        cache = get_cache()
        await cache.ping()
        async with SessionLocal() as session:
            await ensure_bootstrap_admin(session)
        yield
        await cache.close()

    app = FastAPI(
        title=settings.app_name, version=settings.app_version, lifespan=lifespan
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    register_request_context_middleware(
        app, emit_access_log=settings.access_log_enabled
    )
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(public_webhooks_router, prefix="/webhooks")
    return app


app = create_app()
