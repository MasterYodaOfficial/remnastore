from __future__ import annotations

from dataclasses import dataclass


PREFIX = "m1"


@dataclass(frozen=True, slots=True)
class ParsedMenuCallback:
    scope: str
    action: str
    value: str | None = None


def nav(screen: str) -> str:
    return f"{PREFIX}:n:{screen}"


def action(scope: str, action_name: str, value: str | None = None) -> str:
    if value:
        return f"{PREFIX}:{scope}:{action_name}:{value}"
    return f"{PREFIX}:{scope}:{action_name}"


def parse_menu_callback(data: str | None) -> ParsedMenuCallback | None:
    if not data or not data.startswith(f"{PREFIX}:"):
        return None

    parts = data.split(":", maxsplit=3)
    if len(parts) < 3:
        return None

    scope = parts[1]
    action_name = parts[2]
    value = parts[3] if len(parts) == 4 else None
    return ParsedMenuCallback(scope=scope, action=action_name, value=value)
