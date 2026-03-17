import logging

from app.core.config import settings


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


def configure_logging() -> None:
    logging.basicConfig(
        level=resolve_log_level(settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
