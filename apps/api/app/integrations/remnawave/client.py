from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Optional
from uuid import UUID

import httpx
from pydantic import ValidationError
from remnawave import RemnawaveSDK
from remnawave.enums import UserStatus
from remnawave.exceptions import ApiError, NotFoundError
from remnawave.models.internal_squads import InternalSquadDto
from remnawave.models.users import (
    CreateUserRequestDto,
    UpdateUserRequestDto,
    UpdateUserResponseDto,
)

from app.core.config import settings


class RemnawaveConfigurationError(Exception):
    pass


class RemnawaveRequestError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RemnawaveInternalSquad:
    uuid: UUID
    name: str


@dataclass(slots=True)
class RemnawaveUser:
    uuid: UUID
    username: str
    status: str
    expire_at: datetime
    subscription_url: str
    telegram_id: Optional[int]
    email: Optional[str]
    tag: Optional[str]
    hwid_device_limit: Optional[int] = None
    traffic_limit_bytes: Optional[int] = None
    traffic_limit_strategy: Optional[str] = None
    used_traffic_bytes: int = 0
    lifetime_used_traffic_bytes: int = 0
    online_at: Optional[datetime] = None
    first_connected_at: Optional[datetime] = None


def _sanitize_username_component(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return ""
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_-")
    return normalized.lower()


def _resolve_username_prefix() -> str:
    candidates = (
        settings.remnawave_username_prefix,
        settings.telegram_bot_username,
        settings.app_name,
        "acc",
    )
    for candidate in candidates:
        normalized = _sanitize_username_component(candidate)
        if normalized:
            return normalized
    return "acc"


def build_remnawave_username(account_id: UUID, telegram_id: int | None = None) -> str:
    prefix = _resolve_username_prefix()
    if telegram_id is not None:
        suffix = f"tg{telegram_id}"
    else:
        suffix = account_id.hex[:12]

    max_prefix_len = max(3, 36 - len(suffix) - 1)
    normalized_prefix = prefix[:max_prefix_len].strip("_-") or "acc"
    return f"{normalized_prefix}_{suffix}"


def build_remnawave_description(
    *,
    user_uuid: UUID,
    telegram_id: int | None,
    is_trial: bool,
) -> str:
    label = (
        settings.remnawave_user_label or settings.telegram_bot_username or "Remnastore"
    ).strip()
    parts = [label]
    if telegram_id is not None:
        parts.append(f"tg:{telegram_id}")
    if is_trial:
        parts.append("trial")
    parts.append(f"uuid:{user_uuid}")
    return " | ".join(part for part in parts if part)


def _normalize_status(status: object) -> str:
    value = getattr(status, "value", status)
    return str(value)


def _normalize_optional_strategy(value: object) -> str | None:
    if value is None:
        return None
    normalized = getattr(value, "value", value)
    rendered = str(normalized).strip()
    return rendered or None


def _resolve_user_status(status: str | None, *, expire_at: datetime) -> UserStatus:
    normalized = _normalize_status(status).strip().upper() if status is not None else ""
    for candidate in UserStatus:
        if candidate.value == normalized:
            return candidate

    normalized_expire_at = expire_at
    if normalized_expire_at.tzinfo is None:
        normalized_expire_at = normalized_expire_at.replace(tzinfo=timezone.utc)
    if normalized_expire_at <= datetime.now(timezone.utc):
        return UserStatus.EXPIRED
    return UserStatus.ACTIVE


def _to_user_snapshot(response: object) -> RemnawaveUser:
    return RemnawaveUser(
        uuid=response.uuid,
        username=response.username,
        status=_normalize_status(response.status),
        expire_at=response.expire_at,
        subscription_url=response.subscription_url,
        telegram_id=response.telegram_id,
        email=response.email,
        tag=response.tag,
        hwid_device_limit=getattr(response, "hwid_device_limit", None),
        traffic_limit_bytes=getattr(response, "traffic_limit_bytes", None),
        traffic_limit_strategy=_normalize_optional_strategy(
            getattr(response, "traffic_limit_strategy", None)
        ),
        used_traffic_bytes=int(getattr(response, "used_traffic_bytes", 0) or 0),
        lifetime_used_traffic_bytes=int(
            getattr(response, "lifetime_used_traffic_bytes", 0) or 0
        ),
        online_at=getattr(response, "online_at", None),
        first_connected_at=getattr(response, "first_connected_at", None),
    )


def _resolve_effective_hwid_device_limit(
    *,
    existing_user: RemnawaveUser | None,
    requested_limit: int | None,
    is_trial: bool,
) -> int | None:
    if existing_user is None:
        return requested_limit

    existing_limit = getattr(existing_user, "hwid_device_limit", None)
    existing_tag = _normalize_optional_strategy(getattr(existing_user, "tag", None))
    if existing_limit is not None:
        if existing_tag == "TRIAL" and not is_trial and requested_limit is not None:
            return requested_limit
        return existing_limit
    if requested_limit is not None:
        return requested_limit
    return existing_limit


def _to_internal_squad_snapshot(response: InternalSquadDto) -> RemnawaveInternalSquad:
    return RemnawaveInternalSquad(
        uuid=response.uuid,
        name=response.name,
    )


def _request_error_message(exc: Exception) -> str:
    message = getattr(exc, "message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()

    rendered = str(exc).strip()
    if rendered:
        return rendered

    return exc.__class__.__name__


def _response_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        for key in ("message", "detail", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    body = response.text.strip()
    if body:
        return body
    return f"Remnawave request failed with status {response.status_code}"


def _unwrap_response_envelope(payload: object) -> object:
    if not isinstance(payload, dict):
        return payload
    nested_payload = payload.get("response")
    if nested_payload is None:
        return payload
    return nested_payload


def _dedupe_users_by_uuid(users: list[RemnawaveUser]) -> list[RemnawaveUser]:
    deduped: dict[UUID, RemnawaveUser] = {}
    for user in users:
        deduped[user.uuid] = user
    return list(deduped.values())


class RemnawaveGateway:
    def __init__(self) -> None:
        if not settings.remnawave_api_url or not settings.remnawave_api_token:
            raise RemnawaveConfigurationError("Remnawave is not configured")

        self._sdk = RemnawaveSDK(
            base_url=settings.remnawave_api_url,
            token=settings.remnawave_api_token,
        )
        self._default_internal_squad_uuid_cache: UUID | None = None
        self._default_internal_squad_uuid_resolved = False

    async def get_user_by_uuid(self, user_uuid: UUID) -> RemnawaveUser | None:
        try:
            response = await self._sdk.users.get_user_by_uuid(str(user_uuid))
        except NotFoundError:
            return None
        except (ApiError, httpx.HTTPError) as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

        return _to_user_snapshot(response)

    async def get_user_by_username(self, username: str) -> RemnawaveUser | None:
        try:
            response = await self._sdk.users.get_user_by_username(username)
        except NotFoundError:
            return None
        except (ApiError, httpx.HTTPError) as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

        return _to_user_snapshot(response)

    async def _find_existing_user_for_upsert(
        self,
        *,
        user_uuid: UUID,
        username: str,
        email: str | None,
        telegram_id: int | None,
    ) -> RemnawaveUser | None:
        existing_user = await self.get_user_by_uuid(user_uuid)
        if existing_user is not None:
            return existing_user

        existing_user = await self.get_user_by_username(username)
        if existing_user is not None:
            return existing_user

        candidates: list[RemnawaveUser] = []
        if telegram_id is not None:
            candidates.extend(await self.get_users_by_telegram_id(telegram_id))
        if email:
            candidates.extend(await self.get_users_by_email(email))

        deduped_candidates = _dedupe_users_by_uuid(candidates)
        if not deduped_candidates:
            return None
        if len(deduped_candidates) == 1:
            return deduped_candidates[0]

        raise RemnawaveRequestError(
            "Multiple Remnawave users match this account identity"
        )

    async def _update_user(
        self,
        body: UpdateUserRequestDto,
        *,
        clear_tag: bool,
    ) -> RemnawaveUser:
        try:
            if clear_tag:
                payload = body.model_dump(exclude_none=True, by_alias=True, mode="json")
                payload["tag"] = None
                response = await self._sdk.users.client.patch("users", json=payload)
                response.raise_for_status()
                return _to_user_snapshot(
                    UpdateUserResponseDto.model_validate(
                        _unwrap_response_envelope(response.json())
                    )
                )

            response = await self._sdk.users.update_user(body)
            return _to_user_snapshot(response)
        except ValidationError as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise RemnawaveRequestError(_response_error_message(exc.response)) from exc
        except (ApiError, httpx.HTTPError) as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

    async def provision_user(
        self,
        *,
        user_uuid: UUID,
        expire_at: datetime,
        email: str | None,
        telegram_id: int | None,
        is_trial: bool,
        hwid_device_limit: int | None = None,
        traffic_limit_bytes: int | None = None,
        traffic_limit_strategy: str | None = None,
    ) -> RemnawaveUser:
        username = build_remnawave_username(user_uuid, telegram_id)
        description = build_remnawave_description(
            user_uuid=user_uuid,
            telegram_id=telegram_id,
            is_trial=is_trial,
        )
        tag = "TRIAL" if is_trial else None
        active_internal_squads = await self._resolve_active_internal_squads()
        existing_user = await self._find_existing_user_for_upsert(
            user_uuid=user_uuid,
            username=username,
            email=email,
            telegram_id=telegram_id,
        )
        clear_tag = (
            existing_user is not None and existing_user.tag is not None and tag is None
        )
        effective_hwid_device_limit = _resolve_effective_hwid_device_limit(
            existing_user=existing_user,
            requested_limit=hwid_device_limit,
            is_trial=is_trial,
        )
        create_payload = {
            "uuid": user_uuid,
            "username": username,
            "expire_at": expire_at,
            "status": UserStatus.ACTIVE,
            "email": email,
            "telegram_id": telegram_id,
            "hwid_device_limit": effective_hwid_device_limit,
            "active_internal_squads": active_internal_squads,
            "description": description,
            "tag": tag,
        }
        update_payload = {
            "uuid": existing_user.uuid if existing_user is not None else user_uuid,
            "expire_at": expire_at,
            "status": UserStatus.ACTIVE,
            "email": email,
            "telegram_id": telegram_id,
            "hwid_device_limit": effective_hwid_device_limit,
            "active_internal_squads": active_internal_squads,
            "description": description,
            "tag": tag,
        }
        if traffic_limit_bytes is not None:
            create_payload["traffic_limit_bytes"] = traffic_limit_bytes
            update_payload["traffic_limit_bytes"] = traffic_limit_bytes
        if traffic_limit_strategy is not None:
            create_payload["traffic_limit_strategy"] = traffic_limit_strategy
            update_payload["traffic_limit_strategy"] = traffic_limit_strategy

        try:
            if existing_user is None:
                response = await self._sdk.users.create_user(
                    CreateUserRequestDto(**create_payload)
                )
            else:
                response = await self._update_user(
                    UpdateUserRequestDto(**update_payload),
                    clear_tag=clear_tag,
                )
        except (ApiError, httpx.HTTPError) as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

        return _to_user_snapshot(response)

    async def upsert_user(
        self,
        *,
        user_uuid: UUID,
        expire_at: datetime,
        email: str | None,
        telegram_id: int | None,
        status: str | None,
        is_trial: bool,
        hwid_device_limit: int | None = None,
        traffic_limit_bytes: int | None = None,
        traffic_limit_strategy: str | None = None,
    ) -> RemnawaveUser:
        username = build_remnawave_username(user_uuid, telegram_id)
        description = build_remnawave_description(
            user_uuid=user_uuid,
            telegram_id=telegram_id,
            is_trial=is_trial,
        )
        tag = "TRIAL" if is_trial else None
        resolved_status = _resolve_user_status(status, expire_at=expire_at)
        active_internal_squads = await self._resolve_active_internal_squads()
        existing_user = await self._find_existing_user_for_upsert(
            user_uuid=user_uuid,
            username=username,
            email=email,
            telegram_id=telegram_id,
        )
        clear_tag = (
            existing_user is not None and existing_user.tag is not None and tag is None
        )
        effective_hwid_device_limit = _resolve_effective_hwid_device_limit(
            existing_user=existing_user,
            requested_limit=hwid_device_limit,
            is_trial=is_trial,
        )
        create_payload = {
            "uuid": user_uuid,
            "username": username,
            "expire_at": expire_at,
            "status": resolved_status,
            "email": email,
            "telegram_id": telegram_id,
            "hwid_device_limit": effective_hwid_device_limit,
            "active_internal_squads": active_internal_squads,
            "description": description,
            "tag": tag,
        }
        update_payload = {
            "uuid": existing_user.uuid if existing_user is not None else user_uuid,
            "expire_at": expire_at,
            "status": resolved_status,
            "email": email,
            "telegram_id": telegram_id,
            "hwid_device_limit": effective_hwid_device_limit,
            "active_internal_squads": active_internal_squads,
            "description": description,
            "tag": tag,
        }
        if traffic_limit_bytes is not None:
            create_payload["traffic_limit_bytes"] = traffic_limit_bytes
            update_payload["traffic_limit_bytes"] = traffic_limit_bytes
        if traffic_limit_strategy is not None:
            create_payload["traffic_limit_strategy"] = traffic_limit_strategy
            update_payload["traffic_limit_strategy"] = traffic_limit_strategy

        try:
            if existing_user is None:
                response = await self._sdk.users.create_user(
                    CreateUserRequestDto(**create_payload)
                )
            else:
                response = await self._update_user(
                    UpdateUserRequestDto(**update_payload),
                    clear_tag=clear_tag,
                )
        except (ApiError, httpx.HTTPError) as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

        return _to_user_snapshot(response)

    async def delete_user(self, user_uuid: UUID) -> None:
        try:
            await self._sdk.users.delete_user(str(user_uuid))
        except NotFoundError:
            return None
        except (ApiError, httpx.HTTPError) as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

    async def get_users_by_email(self, email: str) -> list[RemnawaveUser]:
        try:
            response = await self._sdk.users.get_users_by_email(email)
        except (ApiError, httpx.HTTPError) as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

        return [_to_user_snapshot(user) for user in response.root]

    async def get_internal_squads(self) -> list[RemnawaveInternalSquad]:
        try:
            response = await self._sdk.internal_squads.get_internal_squads()
        except (ApiError, httpx.HTTPError) as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

        return [
            _to_internal_squad_snapshot(squad) for squad in response.internal_squads
        ]

    async def get_all_users(self, *, page_size: int = 500) -> list[RemnawaveUser]:
        if page_size <= 0:
            raise ValueError("page_size must be positive")

        users: list[RemnawaveUser] = []
        offset = 0

        while True:
            try:
                response = await self._sdk.users.get_all_users(
                    start=offset, size=page_size
                )
            except (ApiError, httpx.HTTPError) as exc:
                raise RemnawaveRequestError(_request_error_message(exc)) from exc

            batch = [_to_user_snapshot(user) for user in response.users]
            users.extend(batch)

            if not batch or len(batch) < page_size or len(users) >= int(response.total):
                break
            offset += page_size

        return users

    async def get_users_by_telegram_id(self, telegram_id: int) -> list[RemnawaveUser]:
        try:
            response = await self._sdk.users.get_users_by_telegram_id(str(telegram_id))
        except (ApiError, httpx.HTTPError) as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

        return [_to_user_snapshot(user) for user in response.root]

    async def _resolve_active_internal_squads(self) -> list[UUID]:
        default_squad_uuid = await self._resolve_default_internal_squad_uuid()
        return [default_squad_uuid]

    async def _resolve_default_internal_squad_uuid(self) -> UUID:
        if (
            self._default_internal_squad_uuid_resolved
            and self._default_internal_squad_uuid_cache is not None
        ):
            return self._default_internal_squad_uuid_cache

        internal_squads = await self.get_internal_squads()
        if not internal_squads:
            raise RemnawaveConfigurationError(
                "Remnawave has no internal squads. Create one squad before provisioning users."
            )

        configured_uuid = self._configured_internal_squad_uuid()
        if configured_uuid is not None:
            for squad in internal_squads:
                if squad.uuid == configured_uuid:
                    self._default_internal_squad_uuid_cache = squad.uuid
                    self._default_internal_squad_uuid_resolved = True
                    return squad.uuid
            raise RemnawaveConfigurationError(
                f"Configured Remnawave internal squad UUID was not found: {configured_uuid}"
            )

        configured_name = settings.remnawave_default_internal_squad_name.strip()
        if configured_name:
            for squad in internal_squads:
                if squad.name.casefold() == configured_name.casefold():
                    self._default_internal_squad_uuid_cache = squad.uuid
                    self._default_internal_squad_uuid_resolved = True
                    return squad.uuid
            if len(internal_squads) == 1:
                only_squad = internal_squads[0]
                self._default_internal_squad_uuid_cache = only_squad.uuid
                self._default_internal_squad_uuid_resolved = True
                return only_squad.uuid
            raise RemnawaveConfigurationError(
                "Configured Remnawave internal squad name was not found. "
                f"Set REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUID or update "
                f"REMNAWAVE_DEFAULT_INTERNAL_SQUAD_NAME={configured_name!r}."
            )

        if len(internal_squads) == 1:
            only_squad = internal_squads[0]
            self._default_internal_squad_uuid_cache = only_squad.uuid
            self._default_internal_squad_uuid_resolved = True
            return only_squad.uuid

        squad_names = ", ".join(sorted(squad.name for squad in internal_squads))
        raise RemnawaveConfigurationError(
            "Multiple Remnawave internal squads found. "
            "Set REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUID or REMNAWAVE_DEFAULT_INTERNAL_SQUAD_NAME. "
            f"Available squads: {squad_names}"
        )

    def _configured_internal_squad_uuid(self) -> UUID | None:
        raw_value = settings.remnawave_default_internal_squad_uuid.strip()
        if not raw_value:
            return None
        try:
            return UUID(raw_value)
        except ValueError as exc:
            raise RemnawaveConfigurationError(
                "REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUID must be a valid UUID"
            ) from exc


_gateway: RemnawaveGateway | None = None


def get_remnawave_gateway() -> RemnawaveGateway:
    global _gateway
    if _gateway is None:
        _gateway = RemnawaveGateway()
    return _gateway
