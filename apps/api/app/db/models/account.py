import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AccountStatus(str, enum.Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class LoginSource(str, enum.Enum):
    TELEGRAM_WEBAPP = "telegram_webapp"
    TELEGRAM_BOT_START = "telegram_bot_start"
    BROWSER_OAUTH = "browser_oauth"


class AuthProvider(str, enum.Enum):
    GOOGLE = "google"
    YANDEX = "yandex"
    VK = "vk"


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("telegram_id", name="uq_accounts_telegram_id"),
        Index("ix_accounts_remnawave_user_uuid", "remnawave_user_uuid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )

    email: Mapped[Optional[str]] = mapped_column(String(255))
    display_name: Mapped[Optional[str]] = mapped_column(String(255))

    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    first_name: Mapped[Optional[str]] = mapped_column(String(64))
    last_name: Mapped[Optional[str]] = mapped_column(String(64))
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locale: Mapped[Optional[str]] = mapped_column(String(16))

    remnawave_user_uuid: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True))
    subscription_url: Mapped[Optional[str]] = mapped_column(String(512))

    status: Mapped[AccountStatus] = mapped_column(
        Enum(
            AccountStatus,
            values_callable=lambda obj: [e.value for e in obj],
            name="accountstatus",
            native_enum=True,
        ),
        default=AccountStatus.ACTIVE,
        nullable=False,
    )
    last_login_source: Mapped[Optional[LoginSource]] = mapped_column(
        Enum(
            LoginSource,
            values_callable=lambda obj: [e.value for e in obj],
            name="loginsource",
            native_enum=True,
        )
    )

    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    auth_accounts: Mapped[list["AuthAccount"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


provider_enum_kwargs = dict(
    values_callable=lambda obj: [e.value for e in obj],
    name="authprovider",
    native_enum=True,
)


class AuthAccount(Base):
    __tablename__ = "auth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_uid", name="uq_auth_provider_uid"),
        Index("ix_auth_accounts_account_id", "account_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, **provider_enum_kwargs), nullable=False
    )
    provider_uid: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    account: Mapped[Account] = relationship(back_populates="auth_accounts")


class AuthLinkToken(Base):
    """
    Временный токен для авто-привязки OAuth-аккаунта к Telegram.
    Живёт до expires_at или пока не будет consumed_at.
    """

    __tablename__ = "auth_link_tokens"
    __table_args__ = (
        UniqueConstraint("link_token", name="uq_link_token"),
        Index("ix_auth_link_tokens_provider_uid", "provider", "provider_uid"),
        Index("ix_auth_link_tokens_account_id", "account_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )

    link_token: Mapped[str] = mapped_column(String(128), nullable=False)

    provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, **provider_enum_kwargs), nullable=False
    )
    provider_uid: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    display_name: Mapped[Optional[str]] = mapped_column(String(255))

    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True))

    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
