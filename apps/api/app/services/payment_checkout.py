"""Payment-scoped checkout links. These tickets cannot authenticate an account."""

import hashlib
import hmac
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import TokenError, create_access_token, decode_access_token
from app.db.models import Account, AccountStatus, Payment
from app.domain.payments import (
    PaymentGatewayConfigurationError,
    PaymentProvider,
    PaymentStatus,
)

TOKEN_METADATA_KEY = "checkout_confirmation_token"


def _ticket_secret() -> str:
    return hmac.new(
        settings.jwt_secret.encode(), b"remnastore-checkout-v1", hashlib.sha256
    ).hexdigest()


def checkout_base_url() -> str:
    parsed = urlsplit(settings.webapp_url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise PaymentGatewayConfigurationError(
            "WEBAPP_URL is required for widget checkout"
        )
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/") + "/checkout", "", "")
    )


def create_checkout_url(account_id: UUID, provider_payment_id: str) -> str:
    ticket = create_access_token(
        {
            "purpose": "checkout",
            "account_id": str(account_id),
            "payment_id": provider_payment_id,
        },
        secret=_ticket_secret(),
        expires_in_seconds=3600,
    )
    return (
        checkout_base_url()
        + "?"
        + urlencode({"payment_id": provider_payment_id})
        + "#"
        + urlencode({"checkout_token": ticket})
    )


def sbp_checkout_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url)
    # Never modify an external YooKassa redirect URL.
    if not parsed.path.endswith("/checkout") or not parse_qs(parsed.fragment).get(
        "checkout_token"
    ):
        return None
    query = parse_qs(parsed.query)
    query["mode"] = ["sbp"]
    return urlunsplit(parsed._replace(query=urlencode(query, doseq=True)))


async def read_checkout(session: AsyncSession, ticket: str) -> dict:
    try:
        claims = decode_access_token(ticket, secret=_ticket_secret())
        if claims.get("purpose") != "checkout":
            raise ValueError("wrong purpose")
        account_id = UUID(claims["account_id"])
        payment_id = claims["payment_id"]
        if not isinstance(payment_id, str):
            raise ValueError("wrong payment")
    except (TokenError, ValueError, KeyError, TypeError):
        raise HTTPException(
            401, "Ссылка оплаты недействительна. Откройте платёж из кабинета."
        ) from None
    payment = await session.scalar(
        select(Payment).where(
            Payment.provider == PaymentProvider.YOOKASSA,
            Payment.provider_payment_id == payment_id,
            Payment.account_id == account_id,
        )
    )
    account = await session.get(Account, account_id)
    if payment is None or account is None:
        raise HTTPException(404, "Платёж не найден")
    if account.status == AccountStatus.BLOCKED:
        raise HTTPException(403, "Оплата недоступна для заблокированного аккаунта")
    expires = payment.expires_at
    expired = expires is not None and expires.replace(
        tzinfo=expires.tzinfo or UTC
    ) <= datetime.now(UTC)
    pending = payment.status in {
        PaymentStatus.CREATED,
        PaymentStatus.PENDING,
        PaymentStatus.REQUIRES_ACTION,
    }
    active = pending and not expired
    token = (payment.request_metadata or {}).get(TOKEN_METADATA_KEY) if active else None
    return {
        "provider_payment_id": payment.provider_payment_id,
        "amount": payment.amount,
        "currency": payment.currency,
        "status": "expired" if expired and pending else payment.status,
        "finalized": payment.finalized_at is not None,
        "confirmation_token": token,
        "return_url": settings.webapp_url,
    }
