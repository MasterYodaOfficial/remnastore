from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx
from remnawave import RemnawaveSDK
from remnawave.enums import UserStatus
from remnawave.exceptions import ApiError, NotFoundError
from remnawave.models.users import CreateUserRequestDto, UpdateUserRequestDto

from app.core.config import settings


class RemnawaveConfigurationError(Exception):
    pass


class RemnawaveRequestError(Exception):
    pass


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


@dataclass(slots=True)
class RemnawaveSubscriptionAccess:
    user_uuid: UUID | None
    short_uuid: str | None
    username: str | None
    status: str | None
    user_status: str | None
    is_active: bool
    expires_at: datetime | None
    days_left: int | None
    subscription_url: str | None
    links: list[str] = field(default_factory=list)
    ssconf_links: dict[str, str] = field(default_factory=dict)
    traffic_used_bytes: int | None = None
    traffic_limit_bytes: int | None = None
    lifetime_traffic_used_bytes: int | None = None


def build_remnawave_username(account_id: UUID) -> str:
    return f"acc_{account_id.hex}"


def _normalize_status(status: object) -> str:
    value = getattr(status, "value", status)
    return str(value)


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
    )


def _request_error_message(exc: Exception) -> str:
    message = getattr(exc, "message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()

    rendered = str(exc).strip()
    if rendered:
        return rendered

    return exc.__class__.__name__


def _optional_text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        try:
            return int(float(normalized))
        except ValueError:
            return None
    return None


def _coerce_links(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        normalized = _optional_text(item)
        if normalized:
            result.append(normalized)
    return result


def _coerce_link_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, item in value.items():
        normalized = _optional_text(item)
        if normalized:
            result[str(key)] = normalized
    return result


def _to_subscription_access_snapshot(response: object) -> RemnawaveSubscriptionAccess:
    user = getattr(response, "user", None)
    if user is None:
        raise RemnawaveRequestError("Remnawave returned subscription without user payload")

    return RemnawaveSubscriptionAccess(
        user_uuid=None,
        short_uuid=_optional_text(getattr(user, "short_uuid", None)),
        username=_optional_text(getattr(user, "username", None)),
        status=_normalize_status(getattr(user, "user_status", None)),
        user_status=_normalize_status(getattr(user, "user_status", None)),
        is_active=bool(getattr(user, "is_active", False)),
        expires_at=getattr(user, "expires_at", None),
        days_left=_optional_int(getattr(user, "days_left", None)),
        subscription_url=_optional_text(getattr(response, "subscription_url", None)),
        links=_coerce_links(getattr(response, "links", None)),
        ssconf_links=_coerce_link_map(getattr(response, "ss_conf_links", None)),
        traffic_used_bytes=_optional_int(getattr(user, "traffic_used_bytes", None)),
        traffic_limit_bytes=_optional_int(getattr(user, "traffic_limit_bytes", None)),
        lifetime_traffic_used_bytes=_optional_int(
            getattr(user, "lifetime_traffic_used_bytes", None)
        ),
    )


class RemnawaveGateway:
    def __init__(self) -> None:
        if not settings.remnawave_api_url or not settings.remnawave_api_token:
            raise RemnawaveConfigurationError("Remnawave is not configured")

        self._sdk = RemnawaveSDK(
            base_url=settings.remnawave_api_url,
            token=settings.remnawave_api_token,
        )

    async def get_user_by_uuid(self, user_uuid: UUID) -> RemnawaveUser | None:
        try:
            response = await self._sdk.users.get_user_by_uuid(str(user_uuid))
        except NotFoundError:
            return None
        except (ApiError, httpx.HTTPError) as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

        return _to_user_snapshot(response)

    async def get_subscription_access_by_uuid(
        self,
        user_uuid: UUID,
    ) -> RemnawaveSubscriptionAccess | None:
        try:
            response = await self._sdk.subscriptions.get_subscription_by_uuid(str(user_uuid))
        except NotFoundError:
            return None
        except ApiError as exc:
            message = _request_error_message(exc)
            if getattr(exc, "status_code", None) == 404 or "404" in message:
                return None
            raise RemnawaveRequestError(message) from exc
        except httpx.HTTPError as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

        snapshot = _to_subscription_access_snapshot(response)
        return RemnawaveSubscriptionAccess(
            user_uuid=user_uuid,
            short_uuid=snapshot.short_uuid,
            username=snapshot.username,
            status=snapshot.status,
            user_status=snapshot.user_status,
            is_active=snapshot.is_active,
            expires_at=snapshot.expires_at,
            days_left=snapshot.days_left,
            subscription_url=snapshot.subscription_url,
            links=snapshot.links,
            ssconf_links=snapshot.ssconf_links,
            traffic_used_bytes=snapshot.traffic_used_bytes,
            traffic_limit_bytes=snapshot.traffic_limit_bytes,
            lifetime_traffic_used_bytes=snapshot.lifetime_traffic_used_bytes,
        )

    async def provision_user(
        self,
        *,
        user_uuid: UUID,
        expire_at: datetime,
        email: str | None,
        telegram_id: int | None,
        is_trial: bool,
    ) -> RemnawaveUser:
        username = build_remnawave_username(user_uuid)
        description = f"remnastore:{user_uuid}"
        tag = "TRIAL" if is_trial else None
        existing_user = await self.get_user_by_uuid(user_uuid)

        try:
            if existing_user is None:
                response = await self._sdk.users.create_user(
                    CreateUserRequestDto(
                        uuid=user_uuid,
                        username=username,
                        expire_at=expire_at,
                        status=UserStatus.ACTIVE,
                        email=email,
                        telegram_id=telegram_id,
                        description=description,
                        tag=tag,
                    )
                )
            else:
                response = await self._sdk.users.update_user(
                    UpdateUserRequestDto(
                        uuid=user_uuid,
                        expire_at=expire_at,
                        status=UserStatus.ACTIVE,
                        email=email,
                        telegram_id=telegram_id,
                        description=description,
                        tag=tag,
                    )
                )
        except (ApiError, httpx.HTTPError) as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

        return _to_user_snapshot(response)

    async def get_users_by_email(self, email: str) -> list[RemnawaveUser]:
        try:
            response = await self._sdk.users.get_users_by_email(email)
        except (ApiError, httpx.HTTPError) as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

        return [_to_user_snapshot(user) for user in response.root]

    async def get_users_by_telegram_id(self, telegram_id: int) -> list[RemnawaveUser]:
        try:
            response = await self._sdk.users.get_users_by_telegram_id(str(telegram_id))
        except (ApiError, httpx.HTTPError) as exc:
            raise RemnawaveRequestError(_request_error_message(exc)) from exc

        return [_to_user_snapshot(user) for user in response.root]


_gateway: RemnawaveGateway | None = None


def get_remnawave_gateway() -> RemnawaveGateway:
    global _gateway
    if _gateway is None:
        _gateway = RemnawaveGateway()
    return _gateway
