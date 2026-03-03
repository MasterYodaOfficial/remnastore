from datetime import datetime
from typing import Optional
from uuid import UUID
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, AccountStatus, LoginSource


async def get_account_by_telegram_id(
    session: AsyncSession, *, telegram_id: int
) -> Account | None:
    result = await session.execute(select(Account).where(Account.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def upsert_telegram_account(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
    is_premium: bool,
    locale: Optional[str],
    email: Optional[str],
    display_name: Optional[str],
    last_login_source: LoginSource,
) -> Account:
    result = await session.execute(
        select(Account).where(Account.telegram_id == telegram_id)
    )
    account = result.scalar_one_or_none()

    now = datetime.utcnow()

    if account is None:
        account = Account(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            is_premium=is_premium,
            locale=locale,
            email=email,
            display_name=display_name,
            status=AccountStatus.ACTIVE,
            last_login_source=last_login_source,
            last_seen_at=now,
        )
        session.add(account)
    else:
        account.username = username or account.username
        account.first_name = first_name or account.first_name
        account.last_name = last_name or account.last_name
        account.is_premium = is_premium or account.is_premium
        account.locale = locale or account.locale
        account.email = email or account.email
        account.display_name = display_name or account.display_name
        account.last_login_source = last_login_source
        account.last_seen_at = now

    # ensure referral_code exists
    if account.referral_code is None:
        account.referral_code = f"ref-{uuid.uuid4().hex[:8]}"

    await session.commit()
    await session.refresh(account)
    return account
