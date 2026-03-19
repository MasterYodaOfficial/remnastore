from __future__ import annotations

import logging
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, Request

from common.logging_setup import reset_request_id, set_request_id


access_logger = logging.getLogger("app.access")


def register_request_context_middleware(
    app: FastAPI,
    *,
    emit_access_log: bool = True,
) -> None:
    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", "").strip() or uuid4().hex
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started_at = monotonic()
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "-"

        try:
            try:
                response = await call_next(request)
            except Exception:
                if emit_access_log:
                    duration_ms = round((monotonic() - started_at) * 1000, 2)
                    access_logger.exception(
                        "http access failed method=%s path=%s status_code=%s duration_ms=%s client_ip=%s",
                        method,
                        path,
                        500,
                        duration_ms,
                        client_ip,
                        extra={
                            "method": method,
                            "path": path,
                            "status_code": 500,
                            "duration_ms": duration_ms,
                            "client_ip": client_ip,
                        },
                    )
                raise

            response.headers["X-Request-ID"] = request_id

            if emit_access_log:
                duration_ms = round((monotonic() - started_at) * 1000, 2)
                access_logger.info(
                    "http access method=%s path=%s status_code=%s duration_ms=%s client_ip=%s",
                    method,
                    path,
                    response.status_code,
                    duration_ms,
                    client_ip,
                    extra={
                        "method": method,
                        "path": path,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                        "client_ip": client_ip,
                    },
                )

            return response
        finally:
            reset_request_id(token)
