from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Request


audit_logger = logging.getLogger("app.audit")
_RESERVED_LOG_RECORD_FIELDS = frozenset(
    {"message", "asctime", *logging.makeLogRecord({}).__dict__.keys()}
)

_OUTCOME_LEVELS = {
    "success": logging.INFO,
    "failure": logging.WARNING,
    "denied": logging.WARNING,
    "error": logging.ERROR,
}


def build_request_audit_context(request: Request) -> dict[str, Any]:
    return {
        "method": request.method,
        "path": request.url.path,
        "client_ip": request.client.host if request.client else "-",
    }


def _format_message_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    return str(value)


def log_audit_event(
    event: str,
    *,
    outcome: str = "success",
    category: str = "security",
    **fields: Any,
) -> None:
    sanitized_fields: dict[str, Any] = {}
    for key, value in fields.items():
        if value is None:
            continue

        sanitized_key = key
        if sanitized_key in _RESERVED_LOG_RECORD_FIELDS:
            sanitized_key = f"audit_{sanitized_key}"
            while (
                sanitized_key in _RESERVED_LOG_RECORD_FIELDS
                or sanitized_key in sanitized_fields
            ):
                sanitized_key = f"audit_{sanitized_key}"

        sanitized_fields[sanitized_key] = value

    payload = {
        "event": event,
        "outcome": outcome,
        "category": category,
    }
    payload.update(sanitized_fields)

    message = " ".join(
        [
            f"audit event={event}",
            f"outcome={outcome}",
            f"category={category}",
            *(
                f"{key}={_format_message_value(value)}"
                for key, value in sorted(fields.items())
                if value is not None
            ),
        ]
    )
    audit_logger.log(_OUTCOME_LEVELS.get(outcome, logging.INFO), message, extra=payload)
