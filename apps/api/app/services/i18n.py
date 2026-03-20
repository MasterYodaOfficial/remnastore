from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings

DEFAULT_LOCALE = "ru"
API_CATALOG_FILES = ("common.json", "api.json")


def normalize_locale(raw_locale: str | None) -> str:
    if not raw_locale:
        return DEFAULT_LOCALE

    normalized = raw_locale.strip().lower().replace("_", "-")
    if not normalized:
        return DEFAULT_LOCALE

    language = normalized.split("-", maxsplit=1)[0]
    return language or DEFAULT_LOCALE


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
            continue
        merged[key] = value
    return merged


def _candidate_locales_dirs() -> list[Path]:
    candidates: list[Path] = []

    configured_dir = str(getattr(settings, "api_locales_dir", "") or "").strip()
    if configured_dir:
        candidates.append(Path(configured_dir))

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / "packages" / "locales")

    candidates.extend(
        [Path.cwd() / "packages" / "locales", Path("/app/packages/locales")]
    )

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(resolved)
    return unique_candidates


@lru_cache(maxsize=1)
def resolve_locales_dir() -> Path:
    for candidate in _candidate_locales_dirs():
        if candidate.exists():
            return candidate
    searched = ", ".join(str(candidate) for candidate in _candidate_locales_dirs())
    raise RuntimeError(f"Locales directory not found. Checked: {searched}")


@lru_cache(maxsize=8)
def load_api_catalog(locale: str) -> dict[str, Any]:
    normalized_locale = normalize_locale(locale)
    locale_dir = resolve_locales_dir() / normalized_locale
    if not locale_dir.exists():
        locale_dir = resolve_locales_dir() / DEFAULT_LOCALE

    catalog: dict[str, Any] = {}
    for filename in API_CATALOG_FILES:
        file_path = locale_dir / filename
        if not file_path.exists():
            continue
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        catalog = _deep_merge(catalog, payload)

    return catalog


def _resolve_nested_value(payload: dict[str, Any], key: str) -> Any:
    current: Any = payload
    for segment in key.split("."):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


class _SafeFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def translate(key: str, *, locale: str | None = None, **params: Any) -> str:
    normalized_locale = normalize_locale(locale)
    catalog = load_api_catalog(normalized_locale)
    value = _resolve_nested_value(catalog, key)

    if value is None and normalized_locale != DEFAULT_LOCALE:
        value = _resolve_nested_value(load_api_catalog(DEFAULT_LOCALE), key)

    if not isinstance(value, str):
        return key

    if not params:
        return value

    return value.format_map(_SafeFormatDict(params))
