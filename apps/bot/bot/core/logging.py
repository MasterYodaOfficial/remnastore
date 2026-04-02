from bot.core.config import settings
from common.logging_setup import configure_logging as configure_runtime_logging


def configure_logging(*, component_name: str = "bot") -> None:
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
