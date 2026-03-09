from __future__ import annotations

from dataclasses import dataclass
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
