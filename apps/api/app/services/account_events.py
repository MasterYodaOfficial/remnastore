from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AccountEventLog
from common.logging_setup import get_request_id


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_request_id(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized in {None, "-"}:
        return None
    return normalized


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return _json_safe_value(value.value)
    if isinstance(value, Mapping):
        return {
            str(item_key): _json_safe_value(item_value)
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    return str(value)


async def append_account_event(
    session: AsyncSession,
    *,
    event_type: str,
    account_id: UUID | None = None,
    actor_account_id: UUID | None = None,
    actor_admin_id: UUID | None = None,
    outcome: str = "success",
    source: str | None = None,
    payload: Mapping[str, Any] | None = None,
    request_id: str | None = None,
) -> AccountEventLog:
    event = AccountEventLog(
        account_id=account_id,
        actor_account_id=actor_account_id,
        actor_admin_id=actor_admin_id,
        event_type=_normalize_required_text(event_type, field_name="event_type"),
        outcome=_normalize_required_text(outcome, field_name="outcome"),
        source=_normalize_optional_text(source),
        request_id=_normalize_request_id(request_id or get_request_id()),
        payload=None if payload is None else _json_safe_value(dict(payload)),
    )
    session.add(event)
    await session.flush()
    return event


async def get_account_event_logs(
    session: AsyncSession,
    *,
    account_id: UUID,
    limit: int,
    offset: int,
) -> tuple[list[AccountEventLog], int]:
    filters = [AccountEventLog.account_id == account_id]
    total = await session.scalar(
        select(func.count()).select_from(AccountEventLog).where(*filters)
    )
    result = await session.execute(
        select(AccountEventLog)
        .where(*filters)
        .order_by(AccountEventLog.created_at.desc(), AccountEventLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)
