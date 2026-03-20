from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.passwords import hash_password, verify_password
from app.db.models import Admin


logger = logging.getLogger(__name__)


class AdminAuthError(Exception):
    pass


class AdminAlreadyExistsError(AdminAuthError):
    pass


class AdminInvalidCredentialsError(AdminAuthError):
    code = "admin_invalid_credentials"


def _normalize_required_login(value: str, *, field_name: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


async def get_admin_by_id(
    session: AsyncSession, admin_id: str | uuid.UUID
) -> Admin | None:
    if isinstance(admin_id, str):
        try:
            admin_id = uuid.UUID(admin_id)
        except ValueError:
            return None
    return await session.get(Admin, admin_id)


async def get_admin_by_login(session: AsyncSession, login: str) -> Admin | None:
    normalized_login = _normalize_required_login(login, field_name="login")
    result = await session.execute(
        select(Admin).where(
            or_(
                func.lower(Admin.username) == normalized_login,
                func.lower(Admin.email) == normalized_login,
            )
        )
    )
    return result.scalar_one_or_none()


async def create_admin(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    email: str | None = None,
    full_name: str | None = None,
    is_superuser: bool = True,
) -> Admin:
    normalized_username = _normalize_required_login(username, field_name="username")
    normalized_email = _normalize_optional_text(email)
    normalized_email = normalized_email.lower() if normalized_email else None
    normalized_full_name = _normalize_optional_text(full_name)

    existing = await get_admin_by_login(session, normalized_username)
    if existing is not None:
        raise AdminAlreadyExistsError(f"admin already exists: {normalized_username}")

    if normalized_email:
        result = await session.execute(
            select(Admin).where(func.lower(Admin.email) == normalized_email)
        )
        if result.scalar_one_or_none() is not None:
            raise AdminAlreadyExistsError(
                f"admin already exists for email: {normalized_email}"
            )

    admin = Admin(
        username=normalized_username,
        email=normalized_email,
        full_name=normalized_full_name,
        password_hash=hash_password(password),
        is_active=True,
        is_superuser=is_superuser,
    )
    session.add(admin)
    await session.flush()
    return admin


async def authenticate_admin(
    session: AsyncSession,
    *,
    login: str,
    password: str,
) -> Admin:
    admin = await get_admin_by_login(session, login)
    if (
        admin is None
        or not admin.is_active
        or not verify_password(password, admin.password_hash)
    ):
        raise AdminInvalidCredentialsError("invalid admin credentials")
    return admin


async def ensure_bootstrap_admin(session: AsyncSession) -> Admin | None:
    username = settings.admin_bootstrap_username.strip()
    password = settings.admin_bootstrap_password

    if not username and not password:
        return None

    if not username or not password:
        logger.warning(
            "Admin bootstrap skipped: both ADMIN_BOOTSTRAP_USERNAME and ADMIN_BOOTSTRAP_PASSWORD are required"
        )
        return None

    admins_count = await session.scalar(select(func.count()).select_from(Admin))
    if int(admins_count or 0) > 0:
        return None

    admin = await create_admin(
        session,
        username=username,
        password=password,
        email=settings.admin_bootstrap_email or None,
        full_name=settings.admin_bootstrap_full_name or None,
        is_superuser=True,
    )
    await session.commit()
    await session.refresh(admin)
    logger.info("Bootstrap admin created: username=%s", admin.username)
    return admin
