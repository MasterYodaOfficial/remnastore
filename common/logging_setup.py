from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from logging.config import dictConfig
from pathlib import Path
from typing import Any


_REQUEST_ID_VAR: ContextVar[str] = ContextVar("request_id", default="-")
_REDACTED = "[REDACTED]"
_SENSITIVE_FIELD_NAMES = {
    "access_token",
    "api_key",
    "api_token",
    "authorization",
    "bot_token",
    "cookie",
    "credentials",
    "init_data",
    "link_token",
    "password",
    "password_hash",
    "refresh_token",
    "secret",
    "token",
    "webhook_secret",
}
_SENSITIVE_FIELD_SUFFIXES = (
    "_token",
    "_secret",
    "_password",
    "_init_data",
    "_cookie",
    "_authorization",
)
_INLINE_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?i)\b(authorization)\s*:\s*bearer\s+[^\s,;]+"),
        r"\1: Bearer [REDACTED]",
    ),
    (
        re.compile(
            r"(?i)\b(access_token|refresh_token|link_token|token|secret|password|init_data)\b([=:])([^\s&,]+)"
        ),
        r"\1\2[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)([?&])(access_token|refresh_token|link_token|token|secret|password|initData|init_data)=([^&\s]+)"
        ),
        r"\1\2=[REDACTED]",
    ),
)
_STANDARD_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
}
_BUILTIN_CONTEXT_FIELDS = {"service", "component", "request_id"}


def resolve_log_level(raw_level: object) -> int | str:
    if isinstance(raw_level, int):
        return raw_level

    if isinstance(raw_level, str):
        normalized = raw_level.strip()
        if not normalized:
            return logging.INFO
        if normalized.isdigit():
            return int(normalized)

        upper_level = normalized.upper()
        if upper_level in logging.getLevelNamesMapping():
            return upper_level

    raise ValueError(f"Unknown level: {raw_level!r}")


def resolve_log_format(raw_format: object) -> str:
    if not isinstance(raw_format, str):
        raise ValueError(f"Unknown log format: {raw_format!r}")

    normalized = raw_format.strip().lower()
    if not normalized:
        return "text"
    if normalized in {"text", "json"}:
        return normalized

    raise ValueError(f"Unknown log format: {raw_format!r}")


def get_request_id() -> str:
    return _REQUEST_ID_VAR.get()


def set_request_id(request_id: str) -> Token[str]:
    normalized = request_id.strip() if request_id else ""
    return _REQUEST_ID_VAR.set(normalized or "-")


def reset_request_id(token: Token[str]) -> None:
    _REQUEST_ID_VAR.reset(token)


def clear_request_id() -> None:
    _REQUEST_ID_VAR.set("-")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-")
    return slug or "application"


def _normalize_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _json_default(value: object) -> str:
    return str(value)


def _is_sensitive_field_name(field_name: str) -> bool:
    normalized = field_name.strip().lower()
    return normalized in _SENSITIVE_FIELD_NAMES or normalized.endswith(_SENSITIVE_FIELD_SUFFIXES)


def redact_sensitive_text(value: str) -> str:
    redacted = value
    for pattern, replacement in _INLINE_REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _sanitize_value(value: Any, *, field_name: str | None = None) -> Any:
    if field_name is not None and _is_sensitive_field_name(field_name):
        return _REDACTED

    if isinstance(value, str):
        return redact_sensitive_text(value)

    if isinstance(value, dict):
        return {
            item_key: _sanitize_value(item_value, field_name=str(item_key))
            for item_key, item_value in value.items()
        }

    if isinstance(value, tuple):
        return tuple(_sanitize_value(item) for item in value)

    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]

    if isinstance(value, set):
        return {_sanitize_value(item) for item in value}

    return value


class ContextFilter(logging.Filter):
    def __init__(self, service_name: str, component_name: str) -> None:
        super().__init__()
        self.service_name = service_name
        self.component_name = component_name

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = getattr(record, "service", None) or self.service_name
        record.component = getattr(record, "component", None) or self.component_name
        record.request_id = getattr(record, "request_id", None) or get_request_id()
        return True


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        original_msg = record.msg
        sanitized_msg = redact_sensitive_text(record.msg) if isinstance(record.msg, str) else record.msg
        sanitized_args = _sanitize_value(record.args)

        if isinstance(sanitized_msg, str) and sanitized_args:
            try:
                sanitized_msg % sanitized_args
            except Exception:
                if isinstance(original_msg, str):
                    try:
                        sanitized_msg = redact_sensitive_text(original_msg % sanitized_args)
                    except Exception:
                        sanitized_msg = redact_sensitive_text(original_msg)
                sanitized_args = ()

        record.msg = sanitized_msg
        record.args = sanitized_args

        for key, value in list(record.__dict__.items()):
            if key in _STANDARD_RECORD_FIELDS or key in _BUILTIN_CONTEXT_FIELDS or key.startswith("_"):
                continue
            record.__dict__[key] = _sanitize_value(value, field_name=key)

        return True


class JsonFormatter(logging.Formatter):
    def formatTime(
        self,
        record: logging.LogRecord,
        datefmt: str | None = None,
    ) -> str:
        del datefmt
        timestamp = datetime.fromtimestamp(record.created, UTC)
        return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_text(record.getMessage()),
            "service": getattr(record, "service", "-"),
            "component": getattr(record, "component", "-"),
            "request_id": getattr(record, "request_id", "-"),
        }

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_FIELDS and key not in _BUILTIN_CONTEXT_FIELDS and not key.startswith("_")
        }
        if extras:
            payload.update(
                {
                    key: _sanitize_value(value, field_name=key)
                    for key, value in extras.items()
                }
            )

        if record.exc_info:
            payload["exception"] = redact_sensitive_text(self.formatException(record.exc_info))
        if record.stack_info:
            payload["stack_info"] = redact_sensitive_text(self.formatStack(record.stack_info))

        return json.dumps(payload, ensure_ascii=True, default=_json_default)


class TextFormatter(logging.Formatter):
    default_time_format = "%Y-%m-%dT%H:%M:%S"
    default_msec_format = "%s.%03dZ"

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)s service=%(service)s component=%(component)s logger=%(name)s request_id=%(request_id)s %(message)s"
        )

    def formatTime(
        self,
        record: logging.LogRecord,
        datefmt: str | None = None,
    ) -> str:
        del datefmt
        timestamp = datetime.fromtimestamp(record.created, UTC)
        return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive_text(super().format(record))


def build_logging_config(
    *,
    service_name: str,
    component_name: str,
    log_level: object,
    log_format: object,
    log_to_file: bool,
    log_dir: str,
    log_file_max_bytes: int,
    log_file_backup_count: int,
) -> dict[str, Any]:
    resolved_level = resolve_log_level(log_level)
    resolved_format = resolve_log_format(log_format)
    formatter_name = "json" if resolved_format == "json" else "text"

    handlers: dict[str, dict[str, Any]] = {
        "stdout": {
            "class": "logging.StreamHandler",
            "level": resolved_level,
            "formatter": formatter_name,
            "filters": ["context", "redact"],
            "stream": "ext://sys.stdout",
        }
    }
    root_handlers = ["stdout"]

    if log_to_file:
        log_directory = _normalize_path(log_dir)
        log_directory.mkdir(parents=True, exist_ok=True)
        file_prefix = _slugify(component_name or service_name)
        max_bytes = max(1, int(log_file_max_bytes))
        backup_count = max(1, int(log_file_backup_count))

        handlers["app_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": resolved_level,
            "formatter": formatter_name,
            "filters": ["context", "redact"],
            "filename": str(log_directory / f"{file_prefix}.log"),
            "maxBytes": max_bytes,
            "backupCount": backup_count,
            "encoding": "utf-8",
        }
        handlers["error_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "ERROR",
            "formatter": formatter_name,
            "filters": ["context", "redact"],
            "filename": str(log_directory / f"{file_prefix}.error.log"),
            "maxBytes": max_bytes,
            "backupCount": backup_count,
            "encoding": "utf-8",
        }
        root_handlers.extend(["app_file", "error_file"])

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {
                "()": ContextFilter,
                "service_name": service_name,
                "component_name": component_name,
            },
            "redact": {"()": SensitiveDataFilter},
        },
        "formatters": {
            "text": {"()": TextFormatter},
            "json": {"()": JsonFormatter},
        },
        "handlers": handlers,
        "root": {
            "handlers": root_handlers,
            "level": resolved_level,
        },
        "loggers": {
            "uvicorn": {
                "handlers": root_handlers,
                "level": resolved_level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": root_handlers,
                "level": resolved_level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": root_handlers,
                "level": resolved_level,
                "propagate": False,
            },
            "app.access": {
                "handlers": root_handlers,
                "level": resolved_level,
                "propagate": False,
            },
            "app.audit": {
                "handlers": root_handlers,
                "level": resolved_level,
                "propagate": False,
            },
        },
    }


def configure_logging(
    *,
    service_name: str,
    component_name: str,
    log_level: object,
    log_format: object,
    log_to_file: bool,
    log_dir: str,
    log_file_max_bytes: int,
    log_file_backup_count: int,
) -> None:
    dictConfig(
        build_logging_config(
            service_name=service_name,
            component_name=component_name,
            log_level=log_level,
            log_format=log_format,
            log_to_file=log_to_file,
            log_dir=log_dir,
            log_file_max_bytes=log_file_max_bytes,
            log_file_backup_count=log_file_backup_count,
        )
    )
    logging.captureWarnings(True)
