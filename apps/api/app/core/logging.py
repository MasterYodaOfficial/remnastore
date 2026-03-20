from app.core.config import settings
from common.logging_setup import (
    configure_logging as configure_runtime_logging,
    resolve_log_format as resolve_runtime_log_format,
    resolve_log_level as resolve_runtime_log_level,
)


def resolve_log_level(raw_level: object) -> int | str:
    return resolve_runtime_log_level(raw_level)


def resolve_log_format(raw_format: object) -> str:
    return resolve_runtime_log_format(raw_format)

def configure_logging(*, component_name: str = "api") -> None:
    configure_runtime_logging(
        service_name=settings.app_name,
        component_name=component_name,
        log_level=settings.log_level,
        log_format=settings.log_format,
        log_to_file=settings.log_to_file,
        log_dir=settings.log_dir,
        log_file_max_bytes=settings.log_file_max_bytes,
        log_file_backup_count=settings.log_file_backup_count,
    )
