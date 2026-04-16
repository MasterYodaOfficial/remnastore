from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.services.i18n import translate


class ApiError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        detail: str,
        error_code: str | None = None,
        error_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code
        self.error_params = error_params


def api_error(
    status_code: int,
    detail: str,
    *,
    error_code: str | None = None,
    error_params: dict[str, Any] | None = None,
) -> ApiError:
    return ApiError(
        status_code=status_code,
        detail=detail,
        error_code=error_code,
        error_params=error_params,
    )


def api_error_from_exception(
    status_code: int,
    exc: Exception,
    *,
    error_code: str | None = None,
    error_params: dict[str, Any] | None = None,
) -> ApiError:
    return api_error(
        status_code,
        str(exc),
        error_code=error_code or getattr(exc, "code", None),
        error_params=error_params,
    )


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    payload: dict[str, Any] = {"detail": exc.detail}
    if exc.error_code is not None:
        payload["error_code"] = exc.error_code
    if exc.error_params:
        payload["error_params"] = exc.error_params
    return JSONResponse(status_code=exc.status_code, content=payload)


def _validation_error_has_field(exc: RequestValidationError, field_name: str) -> bool:
    for item in exc.errors():
        loc = item.get("loc")
        if isinstance(loc, (list, tuple)) and loc and loc[-1] == field_name:
            return True
    return False


async def request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    path = request.url.path
    if not path.startswith("/api/v1/admin/"):
        return await request_validation_exception_handler(request, exc)

    if path == "/api/v1/admin/auth/login":
        return await api_error_handler(
            request,
            api_error(
                422,
                translate("api.admin.errors.missing_credentials"),
                error_code="admin_missing_credentials",
            ),
        )

    if _validation_error_has_field(exc, "comment"):
        return await api_error_handler(
            request,
            api_error(
                422,
                translate("api.admin.errors.comment_required"),
                error_code="admin_comment_required",
            ),
        )

    if path.startswith("/api/v1/admin/promos"):
        return await api_error_handler(
            request,
            api_error(
                422,
                translate("api.admin.errors.promo_validation_failed"),
                error_code="admin_promo_validation_failed",
            ),
        )

    if path.startswith("/api/v1/admin/broadcasts"):
        return await api_error_handler(
            request,
            api_error(
                422,
                translate("api.admin.errors.broadcast_validation_failed"),
                error_code="admin_broadcast_validation_failed",
            ),
        )

    if path.startswith("/api/v1/admin/plans"):
        return await api_error_handler(
            request,
            api_error(
                422,
                translate("api.admin.errors.plan_validation_failed"),
                error_code="admin_plan_validation_failed",
            ),
        )

    return await api_error_handler(
        request,
        api_error(
            422,
            translate("api.admin.errors.request_validation_failed"),
            error_code="admin_request_validation_failed",
        ),
    )
