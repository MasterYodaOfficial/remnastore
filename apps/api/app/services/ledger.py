from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, LedgerEntry, LedgerEntryType
from app.services.cache import get_cache


class LedgerServiceError(Exception):
    pass


class LedgerCommentRequiredError(LedgerServiceError):
    pass


class LedgerIdempotencyConflictError(LedgerServiceError):
    pass


class InsufficientFundsError(LedgerServiceError):
    pass


async def _clear_account_cache(account_id: uuid.UUID) -> None:
    cache = get_cache()
    await cache.delete(cache.account_response_key(str(account_id)))


async def _load_account_for_update(session: AsyncSession, account_id: uuid.UUID) -> Account:
    result = await session.execute(
        select(Account).where(Account.id == account_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise LedgerServiceError(f"account not found: {account_id}")
    return account


async def _get_entry_by_idempotency_key(
    session: AsyncSession,
    idempotency_key: str,
) -> LedgerEntry | None:
    result = await session.execute(
        select(LedgerEntry).where(LedgerEntry.idempotency_key == idempotency_key)
    )
    return result.scalar_one_or_none()


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _ensure_positive_amount(amount: int) -> None:
    if amount <= 0:
        raise ValueError("amount must be positive")


def _validate_idempotent_entry(
    entry: LedgerEntry,
    *,
    account_id: uuid.UUID,
    entry_type: LedgerEntryType,
    amount: int,
) -> None:
    if (
        entry.account_id != account_id
        or entry.entry_type != entry_type
        or entry.amount != amount
    ):
        raise LedgerIdempotencyConflictError("idempotency key already used for another operation")


async def _append_entry_for_locked_account(
    session: AsyncSession,
    *,
    account: Account,
    amount: int,
    entry_type: LedgerEntryType,
    reference_type: str | None = None,
    reference_id: str | None = None,
    comment: str | None = None,
    idempotency_key: str | None = None,
    created_by_account_id: uuid.UUID | None = None,
    created_by_admin_id: uuid.UUID | None = None,
    allow_negative: bool = False,
) -> LedgerEntry:
    if amount == 0:
        raise ValueError("amount must be non-zero")

    balance_before = int(account.balance)
    balance_after = balance_before + amount
    if balance_after < 0 and not allow_negative:
        raise InsufficientFundsError("insufficient funds")

    entry = LedgerEntry(
        account_id=account.id,
        entry_type=entry_type,
        amount=amount,
        currency="RUB",
        balance_before=balance_before,
        balance_after=balance_after,
        reference_type=_normalize_optional_text(reference_type),
        reference_id=_normalize_optional_text(reference_id),
        comment=_normalize_optional_text(comment),
        idempotency_key=_normalize_optional_text(idempotency_key),
        created_by_account_id=created_by_account_id,
        created_by_admin_id=created_by_admin_id,
    )
    account.balance = balance_after
    session.add(entry)
    await session.flush()
    return entry


async def _apply_entry(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    amount: int,
    entry_type: LedgerEntryType,
    reference_type: str | None = None,
    reference_id: str | None = None,
    comment: str | None = None,
    idempotency_key: str | None = None,
    created_by_account_id: uuid.UUID | None = None,
    created_by_admin_id: uuid.UUID | None = None,
    allow_negative: bool = False,
) -> LedgerEntry:
    normalized_idempotency_key = _normalize_optional_text(idempotency_key)
    if normalized_idempotency_key is not None:
        existing_entry = await _get_entry_by_idempotency_key(session, normalized_idempotency_key)
        if existing_entry is not None:
            _validate_idempotent_entry(
                existing_entry,
                account_id=account_id,
                entry_type=entry_type,
                amount=amount,
            )
            return existing_entry

    account = await _load_account_for_update(session, account_id)

    return await _apply_entry_for_loaded_account(
        session,
        account=account,
        amount=amount,
        entry_type=entry_type,
        reference_type=reference_type,
        reference_id=reference_id,
        comment=comment,
        idempotency_key=normalized_idempotency_key,
        created_by_account_id=created_by_account_id,
        created_by_admin_id=created_by_admin_id,
        allow_negative=allow_negative,
    )


async def _apply_entry_for_loaded_account(
    session: AsyncSession,
    *,
    account: Account,
    amount: int,
    entry_type: LedgerEntryType,
    reference_type: str | None = None,
    reference_id: str | None = None,
    comment: str | None = None,
    idempotency_key: str | None = None,
    created_by_account_id: uuid.UUID | None = None,
    created_by_admin_id: uuid.UUID | None = None,
    allow_negative: bool = False,
) -> LedgerEntry:
    normalized_idempotency_key = _normalize_optional_text(idempotency_key)
    if normalized_idempotency_key is not None:
        existing_entry = await _get_entry_by_idempotency_key(session, normalized_idempotency_key)
        if existing_entry is not None:
            _validate_idempotent_entry(
                existing_entry,
                account_id=account.id,
                entry_type=entry_type,
                amount=amount,
            )
            return existing_entry

    try:
        entry = await _append_entry_for_locked_account(
            session,
            account=account,
            amount=amount,
            entry_type=entry_type,
            reference_type=reference_type,
            reference_id=reference_id,
            comment=comment,
            idempotency_key=normalized_idempotency_key,
            created_by_account_id=created_by_account_id,
            created_by_admin_id=created_by_admin_id,
            allow_negative=allow_negative,
        )
    except IntegrityError as exc:
        if normalized_idempotency_key and "uq_ledger_entries_idempotency_key" in str(exc):
            await session.rollback()
            existing_entry = await _get_entry_by_idempotency_key(session, normalized_idempotency_key)
            if existing_entry is not None:
                _validate_idempotent_entry(
                    existing_entry,
                    account_id=account.id,
                    entry_type=entry_type,
                    amount=amount,
                )
                return existing_entry
        raise

    return entry


async def apply_credit_in_transaction(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    amount: int,
    entry_type: LedgerEntryType,
    reference_type: str | None = None,
    reference_id: str | None = None,
    comment: str | None = None,
    idempotency_key: str | None = None,
    created_by_account_id: uuid.UUID | None = None,
    created_by_admin_id: uuid.UUID | None = None,
) -> LedgerEntry:
    _ensure_positive_amount(amount)
    account = await _load_account_for_update(session, account_id)
    return await _apply_entry_for_loaded_account(
        session,
        account=account,
        amount=amount,
        entry_type=entry_type,
        reference_type=reference_type,
        reference_id=reference_id,
        comment=comment,
        idempotency_key=idempotency_key,
        created_by_account_id=created_by_account_id,
        created_by_admin_id=created_by_admin_id,
    )


async def apply_debit_in_transaction(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    amount: int,
    entry_type: LedgerEntryType,
    reference_type: str | None = None,
    reference_id: str | None = None,
    comment: str | None = None,
    idempotency_key: str | None = None,
    created_by_account_id: uuid.UUID | None = None,
    created_by_admin_id: uuid.UUID | None = None,
) -> LedgerEntry:
    _ensure_positive_amount(amount)
    account = await _load_account_for_update(session, account_id)
    return await _apply_entry_for_loaded_account(
        session,
        account=account,
        amount=-amount,
        entry_type=entry_type,
        reference_type=reference_type,
        reference_id=reference_id,
        comment=comment,
        idempotency_key=idempotency_key,
        created_by_account_id=created_by_account_id,
        created_by_admin_id=created_by_admin_id,
    )


async def clear_account_cache(account_id: uuid.UUID) -> None:
    await _clear_account_cache(account_id)


async def _commit_entry(session: AsyncSession, *, entry: LedgerEntry, account_id: uuid.UUID) -> LedgerEntry:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise

    await session.refresh(entry)
    await _clear_account_cache(account_id)
    return entry


async def credit_balance(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    amount: int,
    entry_type: LedgerEntryType,
    reference_type: str | None = None,
    reference_id: str | None = None,
    comment: str | None = None,
    idempotency_key: str | None = None,
    created_by_account_id: uuid.UUID | None = None,
    created_by_admin_id: uuid.UUID | None = None,
) -> LedgerEntry:
    _ensure_positive_amount(amount)
    entry = await _apply_entry(
        session,
        account_id=account_id,
        amount=amount,
        entry_type=entry_type,
        reference_type=reference_type,
        reference_id=reference_id,
        comment=comment,
        idempotency_key=idempotency_key,
        created_by_account_id=created_by_account_id,
        created_by_admin_id=created_by_admin_id,
    )
    return await _commit_entry(session, entry=entry, account_id=account_id)


async def debit_balance(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    amount: int,
    entry_type: LedgerEntryType,
    reference_type: str | None = None,
    reference_id: str | None = None,
    comment: str | None = None,
    idempotency_key: str | None = None,
    created_by_account_id: uuid.UUID | None = None,
    created_by_admin_id: uuid.UUID | None = None,
) -> LedgerEntry:
    _ensure_positive_amount(amount)
    entry = await _apply_entry(
        session,
        account_id=account_id,
        amount=-amount,
        entry_type=entry_type,
        reference_type=reference_type,
        reference_id=reference_id,
        comment=comment,
        idempotency_key=idempotency_key,
        created_by_account_id=created_by_account_id,
        created_by_admin_id=created_by_admin_id,
    )
    return await _commit_entry(session, entry=entry, account_id=account_id)


async def admin_adjust_balance(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    amount: int,
    admin_id: uuid.UUID,
    comment: str,
    reference_type: str | None = "admin_adjustment",
    reference_id: str | None = None,
    idempotency_key: str | None = None,
) -> LedgerEntry:
    normalized_comment = _normalize_optional_text(comment)
    if normalized_comment is None:
        raise LedgerCommentRequiredError("admin comment is required")
    if amount == 0:
        raise ValueError("amount must be non-zero")

    entry_type = LedgerEntryType.ADMIN_CREDIT if amount > 0 else LedgerEntryType.ADMIN_DEBIT
    entry = await _apply_entry(
        session,
        account_id=account_id,
        amount=amount,
        entry_type=entry_type,
        reference_type=reference_type,
        reference_id=reference_id,
        comment=normalized_comment,
        idempotency_key=idempotency_key,
        created_by_admin_id=admin_id,
    )
    return await _commit_entry(session, entry=entry, account_id=account_id)


async def transfer_balance_for_merge(
    session: AsyncSession,
    *,
    source_account: Account,
    target_account: Account,
    amount: int,
    reference_id: str,
) -> tuple[LedgerEntry, LedgerEntry]:
    _ensure_positive_amount(amount)
    debit_entry = await _append_entry_for_locked_account(
        session,
        account=source_account,
        amount=-amount,
        entry_type=LedgerEntryType.MERGE_DEBIT,
        reference_type="account_merge",
        reference_id=reference_id,
        comment=f"balance merged into account {target_account.id}",
    )
    credit_entry = await _append_entry_for_locked_account(
        session,
        account=target_account,
        amount=amount,
        entry_type=LedgerEntryType.MERGE_CREDIT,
        reference_type="account_merge",
        reference_id=reference_id,
        comment=f"balance merged from account {source_account.id}",
    )
    return debit_entry, credit_entry


async def get_account_ledger_history(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    limit: int,
    offset: int,
    entry_types: tuple[LedgerEntryType, ...] | None = None,
) -> tuple[list[LedgerEntry], int]:
    count_statement = select(func.count()).select_from(LedgerEntry).where(
        LedgerEntry.account_id == account_id
    )
    history_statement = select(LedgerEntry).where(LedgerEntry.account_id == account_id)

    if entry_types:
        count_statement = count_statement.where(LedgerEntry.entry_type.in_(entry_types))
        history_statement = history_statement.where(LedgerEntry.entry_type.in_(entry_types))

    total = await session.scalar(count_statement)
    result = await session.execute(
        history_statement
        .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .limit(limit)
        .offset(offset)
    )
    entries = list(result.scalars().all())
    return entries, int(total or 0)
