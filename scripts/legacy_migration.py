#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Sequence, TypeVar


SCRIPT_ROOT = Path(__file__).resolve().parent
BASE_ROOT = SCRIPT_ROOT.parent

if (BASE_ROOT / "apps" / "api" / "app").exists():
    REPO_ROOT = BASE_ROOT
    API_APP_ROOT = REPO_ROOT / "apps" / "api"
    DEFAULT_LEGACY_DB = REPO_ROOT / "old_db" / "db_2.sqlite3"
    DEFAULT_PLANS_JSON = (
        REPO_ROOT / "apps" / "api" / "app" / "config" / "subscription-plans.json"
    )
elif (BASE_ROOT / "app").exists():
    REPO_ROOT = BASE_ROOT
    API_APP_ROOT = BASE_ROOT
    DEFAULT_LEGACY_DB = BASE_ROOT / "old_db" / "db_2.sqlite3"
    DEFAULT_PLANS_JSON = BASE_ROOT / "app" / "config" / "subscription-plans.json"
else:
    raise RuntimeError(
        "Unsupported legacy migration layout: API sources were not found"
    )
TERMINAL_PAYMENT_STATUSES = {"succeeded", "canceled"}
ACTIVE_SUBSCRIPTION_STATUS = "ACTIVE"
INACTIVE_SUBSCRIPTION_STATUSES = {"DISABLED", "EXPIRED"}
SKIP_REASON_BLOCKED_BOT = "telegram_bot_blocked_in_legacy"
LEGACY_SOURCE = "legacy_bot"
LEGACY_REFERRAL_BALANCE_REFERENCE_TYPE = "legacy_referral_balance_import"
LEGACY_PAYMENT_REFERENCE_TYPE = "legacy_payment"
DEFAULT_DB_BATCH_SIZE = 250
DEFAULT_REMNAWAVE_BATCH_SIZE = 100

T = TypeVar("T")

if str(API_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(API_APP_ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Legacy bot migration tool: dry-run, DB import, and Remnawave sync.",
    )
    parser.add_argument(
        "--legacy-db",
        type=Path,
        default=DEFAULT_LEGACY_DB,
        help=f"Path to legacy SQLite DB. Default: {DEFAULT_LEGACY_DB}",
    )
    parser.add_argument(
        "--plans-json",
        type=Path,
        default=DEFAULT_PLANS_JSON,
        help=f"Path to current subscription plans JSON. Default: {DEFAULT_PLANS_JSON}",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Target application database URL. Defaults to app settings.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="How many issue samples to print in dry-run output.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write the full report as JSON.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print migration plan without writing to target systems.",
    )
    parser.add_argument(
        "--apply-db",
        action="store_true",
        help="Write imported users, referrals, balances, payments, and grants to the new DB.",
    )
    parser.add_argument(
        "--db-batch-size",
        type=int,
        default=DEFAULT_DB_BATCH_SIZE,
        help=(
            "How many imported accounts to process per DB batch. "
            f"Default: {DEFAULT_DB_BATCH_SIZE}"
        ),
    )
    parser.add_argument(
        "--sync-remnawave",
        action="store_true",
        help="Upsert canonical active subscriptions in Remnawave and delete known redundant legacy users.",
    )
    parser.add_argument(
        "--remnawave-batch-size",
        type=int,
        default=DEFAULT_REMNAWAVE_BATCH_SIZE,
        help=(
            "How many active accounts to sync to Remnawave per batch. "
            f"Default: {DEFAULT_REMNAWAVE_BATCH_SIZE}"
        ),
    )
    parser.add_argument(
        "--report-remnawave",
        action="store_true",
        help="Read current Remnawave inventory and print manual-review candidates without changing the panel.",
    )
    return parser.parse_args()


def _ensure_positive_batch_size(value: int, *, name: str) -> int:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _parse_datetime(value: object) -> datetime | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime format: {normalized}")


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def _as_utc_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _as_utc_naive(value: datetime | None) -> datetime | None:
    normalized = _as_utc_aware(value)
    if normalized is None:
        return None
    return normalized.replace(tzinfo=None)


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    try:
        return uuid.UUID(normalized)
    except ValueError:
        return None


def _deterministic_account_uuid(telegram_id: int) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"remnastore:legacy:telegram:{telegram_id}")


def _generated_referral_code(telegram_id: int) -> str:
    return f"ref-{uuid.uuid5(uuid.NAMESPACE_URL, f'remnastore:legacy:ref:{telegram_id}').hex[:8]}"


def _desired_subscription_status(*, expires_at: datetime | None) -> str | None:
    if expires_at is None:
        return None
    return "ACTIVE" if expires_at > datetime.now(UTC) else "EXPIRED"


def _chunked(items: Sequence[T], chunk_size: int) -> Iterator[list[T]]:
    normalized_chunk_size = _ensure_positive_batch_size(chunk_size, name="chunk_size")
    for start in range(0, len(items), normalized_chunk_size):
        yield list(items[start : start + normalized_chunk_size])


def _batch_count(total_items: int, chunk_size: int) -> int:
    normalized_chunk_size = _ensure_positive_batch_size(chunk_size, name="chunk_size")
    if total_items <= 0:
        return 0
    return (total_items + normalized_chunk_size - 1) // normalized_chunk_size


def _print_batch_progress(
    phase: str,
    *,
    batch_index: int,
    total_batches: int,
    processed: int,
    total_items: int,
) -> None:
    print(
        f"{phase}: batch {batch_index}/{total_batches} committed "
        f"({processed}/{total_items})"
    )


@dataclass(frozen=True, slots=True)
class CurrentPlan:
    code: str
    duration_days: int
    price_rub: int


@dataclass(frozen=True, slots=True)
class LegacyTariff:
    id: int
    name: str
    duration_days: int
    price: int
    currency: str


@dataclass(frozen=True, slots=True)
class LegacyUser:
    telegram_id: int
    username: str | None
    created_at: datetime | None
    balance: int
    inviter_id: int | None
    referral_code: str | None
    language_code: str | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class LegacySubscription:
    id: int
    telegram_id: int
    start_date: datetime | None
    end_date: datetime | None
    status: str
    remnawave_uuid: uuid.UUID | None
    subscription_url: str | None
    tariff_id: int | None
    hwid_device_limit: int | None
    first_connected: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class LegacyPayment:
    id: int
    user_id: int
    amount: int
    currency: str
    status: str
    method: str
    external_payment_id: str | None
    subscription_id: int | None
    tariff_id: int | None
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class PaymentGrantPlan:
    legacy_payment_id: int
    legacy_subscription_id: int | None
    provider_code: str
    target_payment_status: str
    plan_code: str | None
    duration_days: int | None
    grant_importable: bool
    base_expires_at: datetime | None
    target_expires_at: datetime | None

    def to_report_dict(self) -> dict[str, Any]:
        return {
            "legacy_payment_id": self.legacy_payment_id,
            "legacy_subscription_id": self.legacy_subscription_id,
            "provider": self.provider_code,
            "target_payment_status": self.target_payment_status,
            "plan_code": self.plan_code,
            "duration_days": self.duration_days,
            "grant_importable": self.grant_importable,
            "base_expires_at": _serialize_datetime(self.base_expires_at),
            "target_expires_at": _serialize_datetime(self.target_expires_at),
        }


@dataclass(slots=True)
class MigrationAccountPlan:
    legacy_user: LegacyUser
    account_uuid: uuid.UUID
    import_user: bool
    telegram_bot_blocked: bool
    skip_reason: str | None
    active_subscriptions: list[LegacySubscription]
    canonical_subscription: LegacySubscription | None
    removable_legacy_subscriptions: list[LegacySubscription]
    terminal_payments: list[LegacyPayment]
    pending_payments_count: int
    payment_grant_plans: list[PaymentGrantPlan]
    inviter_importable: bool = False
    imported_referral_code: str | None = None

    @property
    def telegram_id(self) -> int:
        return self.legacy_user.telegram_id

    @property
    def referral_balance(self) -> int:
        return self.legacy_user.balance

    @property
    def target_subscription_expires_at(self) -> datetime | None:
        return (
            None
            if self.canonical_subscription is None
            else self.canonical_subscription.end_date
        )

    @property
    def target_hwid_device_limit(self) -> int | None:
        if self.canonical_subscription is None:
            return None
        return max(1, len(self.active_subscriptions) * 3)

    @property
    def target_remnawave_uuid(self) -> uuid.UUID | None:
        if self.canonical_subscription is None:
            return None
        return self.canonical_subscription.remnawave_uuid or self.account_uuid

    def to_report_dict(self) -> dict[str, Any]:
        return {
            "telegram_id": self.telegram_id,
            "import_user": self.import_user,
            "telegram_bot_blocked": self.telegram_bot_blocked,
            "skip_reason": self.skip_reason,
            "account_uuid": str(self.account_uuid),
            "inviter_id": self.legacy_user.inviter_id,
            "referral_link_importable": self.inviter_importable,
            "referral_balance": self.referral_balance,
            "referral_code": self.imported_referral_code,
            "active_subscription_ids": [item.id for item in self.active_subscriptions],
            "canonical_subscription_id": None
            if self.canonical_subscription is None
            else self.canonical_subscription.id,
            "target_remnawave_uuid": None
            if self.target_remnawave_uuid is None
            else str(self.target_remnawave_uuid),
            "target_subscription_expires_at": _serialize_datetime(
                self.target_subscription_expires_at
            ),
            "target_hwid_device_limit": self.target_hwid_device_limit,
            "imported_payments_count": len(self.terminal_payments),
            "imported_payment_statuses": dict(
                sorted(
                    Counter(
                        item.target_payment_status for item in self.payment_grant_plans
                    ).items()
                )
            ),
            "skipped_pending_payments": self.pending_payments_count,
            "importable_grants_count": sum(
                1 for item in self.payment_grant_plans if item.grant_importable
            ),
            "payment_plans": [
                item.to_report_dict() for item in self.payment_grant_plans
            ],
        }


@dataclass(slots=True)
class MigrationPlan:
    legacy_db_path: Path
    current_plans_path: Path
    current_plans_by_duration: dict[int, CurrentPlan]
    legacy_tariffs: dict[int, LegacyTariff]
    account_plans: list[MigrationAccountPlan]
    all_legacy_remnawave_uuids: set[uuid.UUID]
    removable_legacy_remnawave_uuids: set[uuid.UUID]
    summary: dict[str, Any]
    issue_samples: dict[str, list[dict[str, Any]]]

    def to_report_dict(self) -> dict[str, Any]:
        plan_mapping = [
            {
                "legacy_tariff_id": tariff.id,
                "legacy_name": tariff.name,
                "legacy_duration_days": tariff.duration_days,
                "legacy_price_rub": tariff.price,
                "target_plan_code": None
                if self.current_plans_by_duration.get(tariff.duration_days) is None
                else self.current_plans_by_duration[tariff.duration_days].code,
            }
            for tariff in sorted(self.legacy_tariffs.values(), key=lambda item: item.id)
        ]
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "legacy_db_path": str(self.legacy_db_path),
            "current_plans_path": str(self.current_plans_path),
            "plan_mapping": plan_mapping,
            "summary": self.summary,
            "issue_samples": self.issue_samples,
            "account_plans": [item.to_report_dict() for item in self.account_plans],
        }


@dataclass(frozen=True, slots=True)
class RemnawaveManualReviewItem:
    uuid: str
    username: str
    email: str | None
    telegram_id: int | None
    status: str
    expire_at: str | None
    hwid_device_limit: int | None
    reason: str
    known_legacy_uuid: bool


def _load_current_plans(path: Path) -> dict[int, CurrentPlan]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    plans_by_duration: dict[int, CurrentPlan] = {}
    for item in payload:
        duration_days = int(item["duration_days"])
        if duration_days in plans_by_duration:
            raise ValueError(f"Duplicate current plan duration_days={duration_days}")
        plans_by_duration[duration_days] = CurrentPlan(
            code=str(item["code"]),
            duration_days=duration_days,
            price_rub=int(item["price_rub"]),
        )
    return plans_by_duration


def _connect_legacy_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _load_legacy_tariffs(connection: sqlite3.Connection) -> dict[int, LegacyTariff]:
    tariffs: dict[int, LegacyTariff] = {}
    for row in connection.execute(
        "select id, name, duration_days, price, currency from tariffs order by id"
    ):
        tariffs[int(row["id"])] = LegacyTariff(
            id=int(row["id"]),
            name=_normalize_text(row["name"]) or f"tariff_{row['id']}",
            duration_days=int(row["duration_days"]),
            price=int(row["price"]),
            currency=_normalize_text(row["currency"]) or "RUB",
        )
    return tariffs


def _load_legacy_users(connection: sqlite3.Connection) -> dict[int, LegacyUser]:
    users: dict[int, LegacyUser] = {}
    for row in connection.execute(
        """
        select telegram_id, username, created_at, balance, inviter_id, referral_code, language_code, is_active
        from users
        order by telegram_id
        """
    ):
        users[int(row["telegram_id"])] = LegacyUser(
            telegram_id=int(row["telegram_id"]),
            username=_normalize_text(row["username"]),
            created_at=_parse_datetime(row["created_at"]),
            balance=int(row["balance"] or 0),
            inviter_id=int(row["inviter_id"])
            if row["inviter_id"] is not None
            else None,
            referral_code=_normalize_text(row["referral_code"]),
            language_code=_normalize_text(row["language_code"]),
            is_active=bool(row["is_active"]),
        )
    return users


def _load_legacy_subscriptions(
    connection: sqlite3.Connection,
) -> dict[int, list[LegacySubscription]]:
    subscriptions_by_user: dict[int, list[LegacySubscription]] = defaultdict(list)
    for row in connection.execute(
        """
        select
            id,
            telegram_id,
            start_date,
            end_date,
            status,
            remnawave_uuid,
            subscription_url,
            tariff_id,
            hwidDeviceLimit,
            first_connected,
            updated_at
        from subscriptions
        order by telegram_id, id
        """
    ):
        subscriptions_by_user[int(row["telegram_id"])].append(
            LegacySubscription(
                id=int(row["id"]),
                telegram_id=int(row["telegram_id"]),
                start_date=_parse_datetime(row["start_date"]),
                end_date=_parse_datetime(row["end_date"]),
                status=_normalize_text(row["status"]) or "",
                remnawave_uuid=_parse_uuid(row["remnawave_uuid"]),
                subscription_url=_normalize_text(row["subscription_url"]),
                tariff_id=int(row["tariff_id"])
                if row["tariff_id"] is not None
                else None,
                hwid_device_limit=int(row["hwidDeviceLimit"])
                if _normalize_text(row["hwidDeviceLimit"]) is not None
                else None,
                first_connected=_parse_datetime(row["first_connected"]),
                updated_at=_parse_datetime(row["updated_at"]),
            )
        )
    return subscriptions_by_user


def _load_legacy_payments(
    connection: sqlite3.Connection,
) -> dict[int, list[LegacyPayment]]:
    payments_by_user: dict[int, list[LegacyPayment]] = defaultdict(list)
    for row in connection.execute(
        """
        select
            id,
            user_id,
            amount,
            currency,
            status,
            method,
            external_payment_id,
            subscription_id,
            tariff_id,
            created_at
        from payments_gateways
        order by user_id, datetime(created_at), id
        """
    ):
        payments_by_user[int(row["user_id"])].append(
            LegacyPayment(
                id=int(row["id"]),
                user_id=int(row["user_id"]),
                amount=int(row["amount"] or 0),
                currency=_normalize_text(row["currency"]) or "RUB",
                status=_normalize_text(row["status"]) or "",
                method=_normalize_text(row["method"]) or "",
                external_payment_id=_normalize_text(row["external_payment_id"]),
                subscription_id=int(row["subscription_id"])
                if row["subscription_id"] is not None
                else None,
                tariff_id=int(row["tariff_id"])
                if row["tariff_id"] is not None
                else None,
                created_at=_parse_datetime(row["created_at"]),
            )
        )
    return payments_by_user


def _subscription_sort_key(
    subscription: LegacySubscription,
) -> tuple[float, float, int]:
    end_ts = (
        subscription.end_date.timestamp()
        if subscription.end_date is not None
        else float("-inf")
    )
    updated_ts = (
        subscription.updated_at.timestamp()
        if subscription.updated_at is not None
        else float("-inf")
    )
    return (end_ts, updated_ts, subscription.id)


def _build_payment_grant_plans(
    *,
    payments: list[LegacyPayment],
    legacy_tariffs: dict[int, LegacyTariff],
    current_plans_by_duration: dict[int, CurrentPlan],
) -> list[PaymentGrantPlan]:
    grant_plans: list[PaymentGrantPlan] = []
    rolling_expires_at: datetime | None = None

    for payment in payments:
        target_payment_status = {
            "succeeded": "succeeded",
            "canceled": "cancelled",
        }.get(payment.status, payment.status)
        provider_code = {
            "yookassa": "yookassa",
            "tg_stars": "telegram_stars",
        }.get(payment.method, payment.method)
        tariff = (
            legacy_tariffs.get(payment.tariff_id)
            if payment.tariff_id is not None
            else None
        )
        current_plan = (
            None
            if tariff is None
            else current_plans_by_duration.get(tariff.duration_days)
        )

        grant_importable = (
            payment.status == "succeeded"
            and tariff is not None
            and current_plan is not None
            and payment.created_at is not None
        )

        base_expires_at: datetime | None = None
        target_expires_at: datetime | None = None
        if grant_importable:
            base_expires_at = payment.created_at
            if rolling_expires_at is not None and rolling_expires_at > base_expires_at:
                base_expires_at = rolling_expires_at
            target_expires_at = base_expires_at + timedelta(days=tariff.duration_days)
            rolling_expires_at = target_expires_at

        grant_plans.append(
            PaymentGrantPlan(
                legacy_payment_id=payment.id,
                legacy_subscription_id=payment.subscription_id,
                provider_code=provider_code,
                target_payment_status=target_payment_status,
                plan_code=None if current_plan is None else current_plan.code,
                duration_days=None if tariff is None else tariff.duration_days,
                grant_importable=grant_importable,
                base_expires_at=base_expires_at,
                target_expires_at=target_expires_at,
            )
        )

    return grant_plans


def _should_import_blocked_bot_user(
    *,
    legacy_user: LegacyUser,
    active_subscriptions: list[LegacySubscription],
) -> bool:
    if legacy_user.is_active:
        return True
    if active_subscriptions:
        return True
    if legacy_user.balance > 0:
        return True
    return False


def build_migration_plan(
    *,
    legacy_db_path: Path,
    current_plans_path: Path,
    users: dict[int, LegacyUser],
    subscriptions_by_user: dict[int, list[LegacySubscription]],
    payments_by_user: dict[int, list[LegacyPayment]],
    legacy_tariffs: dict[int, LegacyTariff],
    current_plans_by_duration: dict[int, CurrentPlan],
    sample_limit: int,
) -> MigrationPlan:
    account_plans: list[MigrationAccountPlan] = []
    plans_by_telegram_id: dict[int, MigrationAccountPlan] = {}
    counters: Counter[str] = Counter()
    imported_payment_statuses: Counter[str] = Counter()
    imported_payment_methods: Counter[str] = Counter()
    sample_multi_subscription_accounts: list[dict[str, Any]] = []
    sample_referral_gaps: list[dict[str, Any]] = []
    all_legacy_remnawave_uuids: set[uuid.UUID] = set()
    removable_legacy_remnawave_uuids: set[uuid.UUID] = set()

    counters["legacy_users_total"] = len(users)
    counters["legacy_subscriptions_total"] = sum(
        len(items) for items in subscriptions_by_user.values()
    )
    counters["legacy_payments_total"] = sum(
        len(items) for items in payments_by_user.values()
    )
    counters["referral_links_total"] = sum(
        1 for item in users.values() if item.inviter_id is not None
    )

    for telegram_id, legacy_user in sorted(users.items()):
        all_subscriptions = subscriptions_by_user.get(telegram_id, [])
        active_subscriptions = [
            subscription
            for subscription in all_subscriptions
            if subscription.status == ACTIVE_SUBSCRIPTION_STATUS
        ]
        canonical_subscription = (
            max(active_subscriptions, key=_subscription_sort_key)
            if active_subscriptions
            else None
        )
        removable_subscriptions = [
            subscription
            for subscription in all_subscriptions
            if canonical_subscription is None
            or subscription.id != canonical_subscription.id
        ]
        terminal_payments = [
            payment
            for payment in payments_by_user.get(telegram_id, [])
            if payment.status in TERMINAL_PAYMENT_STATUSES
        ]
        pending_payments = [
            payment
            for payment in payments_by_user.get(telegram_id, [])
            if payment.status == "pending"
        ]
        payment_grant_plans = _build_payment_grant_plans(
            payments=terminal_payments,
            legacy_tariffs=legacy_tariffs,
            current_plans_by_duration=current_plans_by_duration,
        )

        import_user = _should_import_blocked_bot_user(
            legacy_user=legacy_user,
            active_subscriptions=active_subscriptions,
        )
        telegram_bot_blocked = not legacy_user.is_active and import_user

        if legacy_user.is_active:
            counters["users_imported"] += 1
        elif import_user:
            counters["users_imported_telegram_bot_blocked"] += 1
        else:
            counters["users_skipped_blocked_bot"] += 1

        counters["pending_payments_skipped"] += len(pending_payments)

        if import_user and active_subscriptions:
            counters["accounts_with_active_snapshot"] += 1
        if import_user and len(active_subscriptions) > 1:
            counters["accounts_with_collapsed_multi_subscription"] += 1
            if len(sample_multi_subscription_accounts) < sample_limit:
                sample_multi_subscription_accounts.append(
                    {
                        "telegram_id": telegram_id,
                        "legacy_subscription_ids": [
                            item.id for item in active_subscriptions
                        ],
                        "canonical_subscription_id": None
                        if canonical_subscription is None
                        else canonical_subscription.id,
                        "target_subscription_expires_at": _serialize_datetime(
                            None
                            if canonical_subscription is None
                            else canonical_subscription.end_date
                        ),
                        "target_hwid_device_limit": None
                        if canonical_subscription is None
                        else max(1, len(active_subscriptions) * 3),
                    }
                )

        if telegram_bot_blocked:
            if active_subscriptions:
                counters["telegram_bot_blocked_users_with_active_subscription"] += 1
            if legacy_user.balance > 0:
                counters["telegram_bot_blocked_users_with_referral_balance"] += 1

        if import_user and legacy_user.balance > 0:
            counters["users_with_referral_balance_import"] += 1
            counters["referral_balance_import_sum"] += legacy_user.balance

        if import_user:
            counters["payments_imported"] += len(terminal_payments)
            for grant_plan in payment_grant_plans:
                imported_payment_statuses[grant_plan.target_payment_status] += 1
                imported_payment_methods[grant_plan.provider_code] += 1
                if grant_plan.grant_importable:
                    counters["subscription_grants_importable"] += 1
        else:
            counters["payments_skipped_due_user_skip"] += len(terminal_payments)

        for subscription in all_subscriptions:
            if subscription.remnawave_uuid is not None:
                all_legacy_remnawave_uuids.add(subscription.remnawave_uuid)
        for subscription in removable_subscriptions:
            if subscription.remnawave_uuid is not None:
                removable_legacy_remnawave_uuids.add(subscription.remnawave_uuid)

        plan = MigrationAccountPlan(
            legacy_user=legacy_user,
            account_uuid=_deterministic_account_uuid(telegram_id),
            import_user=import_user,
            telegram_bot_blocked=telegram_bot_blocked,
            skip_reason=None if import_user else SKIP_REASON_BLOCKED_BOT,
            active_subscriptions=active_subscriptions,
            canonical_subscription=canonical_subscription,
            removable_legacy_subscriptions=removable_subscriptions,
            terminal_payments=terminal_payments,
            pending_payments_count=len(pending_payments),
            payment_grant_plans=payment_grant_plans,
            imported_referral_code=legacy_user.referral_code
            or _generated_referral_code(telegram_id),
        )
        account_plans.append(plan)
        plans_by_telegram_id[telegram_id] = plan

    for plan in account_plans:
        inviter_id = plan.legacy_user.inviter_id
        if inviter_id is None:
            continue
        inviter_plan = plans_by_telegram_id.get(inviter_id)
        if inviter_plan is None or not inviter_plan.import_user:
            counters["referral_links_skipped_missing_or_inactive_referrer"] += 1
            if len(sample_referral_gaps) < sample_limit:
                sample_referral_gaps.append(
                    {
                        "telegram_id": plan.telegram_id,
                        "inviter_id": inviter_id,
                        "reason": "referrer_missing_or_skipped",
                    }
                )
            continue
        if not plan.import_user:
            counters["referral_links_skipped_referred_user_skipped"] += 1
            continue
        plan.inviter_importable = True
        counters["referral_links_importable"] += 1

    summary = {
        "legacy_users_total": counters["legacy_users_total"],
        "users_imported": counters["users_imported"]
        + counters["users_imported_telegram_bot_blocked"],
        "users_imported_active": counters["users_imported"],
        "users_imported_telegram_bot_blocked": counters[
            "users_imported_telegram_bot_blocked"
        ],
        "users_skipped_blocked_bot": counters["users_skipped_blocked_bot"],
        "telegram_bot_blocked_users_with_active_subscription": counters[
            "telegram_bot_blocked_users_with_active_subscription"
        ],
        "users_with_referral_balance_import": counters[
            "users_with_referral_balance_import"
        ],
        "referral_balance_import_sum": counters["referral_balance_import_sum"],
        "referral_links_total": counters["referral_links_total"],
        "referral_links_importable": counters["referral_links_importable"],
        "referral_links_skipped_referred_user_skipped": counters[
            "referral_links_skipped_referred_user_skipped"
        ],
        "referral_links_skipped_missing_or_inactive_referrer": counters[
            "referral_links_skipped_missing_or_inactive_referrer"
        ],
        "accounts_with_active_snapshot": counters["accounts_with_active_snapshot"],
        "accounts_with_collapsed_multi_subscription": counters[
            "accounts_with_collapsed_multi_subscription"
        ],
        "payments_imported_total": counters["payments_imported"],
        "payments_imported_by_status": dict(sorted(imported_payment_statuses.items())),
        "payments_imported_by_provider": dict(sorted(imported_payment_methods.items())),
        "payments_skipped_due_user_skip": counters["payments_skipped_due_user_skip"],
        "pending_payments_skipped": counters["pending_payments_skipped"],
        "subscription_grants_importable": counters["subscription_grants_importable"],
    }

    issue_samples = {
        "multi_subscription_accounts": sample_multi_subscription_accounts,
        "referral_gaps": sample_referral_gaps,
    }

    return MigrationPlan(
        legacy_db_path=legacy_db_path,
        current_plans_path=current_plans_path,
        current_plans_by_duration=current_plans_by_duration,
        legacy_tariffs=legacy_tariffs,
        account_plans=account_plans,
        all_legacy_remnawave_uuids=all_legacy_remnawave_uuids,
        removable_legacy_remnawave_uuids=removable_legacy_remnawave_uuids,
        summary=summary,
        issue_samples=issue_samples,
    )


def _print_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print("Legacy migration dry-run")
    print(f"Legacy DB: {report['legacy_db_path']}")
    print(f"Plans JSON: {report['current_plans_path']}")
    print()
    print("Summary")
    for key in (
        "legacy_users_total",
        "users_imported",
        "users_imported_active",
        "users_imported_telegram_bot_blocked",
        "users_skipped_blocked_bot",
        "telegram_bot_blocked_users_with_active_subscription",
        "users_with_referral_balance_import",
        "referral_balance_import_sum",
        "referral_links_total",
        "referral_links_importable",
        "referral_links_skipped_referred_user_skipped",
        "referral_links_skipped_missing_or_inactive_referrer",
        "accounts_with_active_snapshot",
        "accounts_with_collapsed_multi_subscription",
        "payments_imported_total",
        "payments_skipped_due_user_skip",
        "pending_payments_skipped",
        "subscription_grants_importable",
    ):
        print(f"- {key}: {summary[key]}")
    print(f"- payments_imported_by_status: {summary['payments_imported_by_status']}")
    print(
        f"- payments_imported_by_provider: {summary['payments_imported_by_provider']}"
    )
    print()
    print("Plan mapping")
    for item in report["plan_mapping"]:
        print(
            f"- legacy tariff {item['legacy_tariff_id']} ({item['legacy_duration_days']}d / {item['legacy_price_rub']} RUB)"
            f" -> {item['target_plan_code']}"
        )

    if report["issue_samples"]["multi_subscription_accounts"]:
        print()
        print("Multi-subscription samples")
        for item in report["issue_samples"]["multi_subscription_accounts"]:
            print(
                f"- telegram_id={item['telegram_id']} subs={item['legacy_subscription_ids']} "
                f"canonical={item['canonical_subscription_id']} "
                f"expires_at={item['target_subscription_expires_at']} "
                f"hwid_limit={item['target_hwid_device_limit']}"
            )

    if report["issue_samples"]["referral_gaps"]:
        print()
        print("Referral gap samples")
        for item in report["issue_samples"]["referral_gaps"]:
            print(
                f"- telegram_id={item['telegram_id']} inviter_id={item['inviter_id']} reason={item['reason']}"
            )


def _print_apply_db_summary(summary: dict[str, Any]) -> None:
    print()
    print("DB import summary")
    for key in (
        "accounts_created",
        "accounts_updated",
        "accounts_marked_telegram_bot_blocked",
        "referral_attributions_created",
        "referral_attributions_updated",
        "payments_created",
        "payments_updated",
        "subscription_grants_created",
        "subscription_grants_updated",
        "ledger_referral_balance_entries_created",
        "ledger_referral_balance_entries_reused",
    ):
        print(f"- {key}: {summary[key]}")


def _print_manual_review_items(items: list[RemnawaveManualReviewItem]) -> None:
    if not items:
        print()
        print("Remnawave manual review")
        print("- no unmatched panel users found")
        return

    print()
    print("Remnawave manual review")
    for item in items:
        print(
            f"- uuid={item.uuid} username={item.username} email={item.email or '-'} "
            f"telegram_id={item.telegram_id or '-'} status={item.status} "
            f"expire_at={item.expire_at or '-'} hwid_limit={item.hwid_device_limit if item.hwid_device_limit is not None else '-'} "
            f"known_legacy_uuid={item.known_legacy_uuid} reason={item.reason}"
        )


def _print_sync_summary(
    summary: dict[str, Any], manual_review_items: list[RemnawaveManualReviewItem]
) -> None:
    print()
    print("Remnawave sync summary")
    for key in (
        "desired_active_accounts",
        "upserts_completed",
        "legacy_cleanup_candidates",
        "legacy_cleanup_deleted",
        "legacy_cleanup_missing",
        "manual_review_candidates",
    ):
        print(f"- {key}: {summary[key]}")
    _print_manual_review_items(manual_review_items)


def _print_remnawave_report_summary(
    summary: dict[str, Any],
    manual_review_items: list[RemnawaveManualReviewItem],
) -> None:
    print()
    print("Remnawave report summary")
    for key in (
        "desired_active_accounts",
        "legacy_cleanup_candidates",
        "legacy_cleanup_present_in_panel",
        "manual_review_candidates",
    ):
        print(f"- {key}: {summary[key]}")
    _print_manual_review_items(manual_review_items)


async def _open_target_session_factory(database_url: str):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def apply_db_import(
    migration_plan: MigrationPlan, *, database_url: str, batch_size: int
) -> dict[str, Any]:
    from sqlalchemy import select, tuple_

    from app.db.models import (
        Account,
        AccountStatus,
        LedgerEntry,
        LedgerEntryType,
        Payment,
        ReferralAttribution,
        SubscriptionGrant,
    )
    from app.domain.payments import PaymentFlowType, PaymentProvider, PaymentStatus
    from app.services.ledger import apply_credit_in_transaction

    normalized_batch_size = _ensure_positive_batch_size(
        batch_size, name="db_batch_size"
    )
    engine, session_factory = await _open_target_session_factory(database_url)
    summary = Counter[str]()
    imported_plans = [plan for plan in migration_plan.account_plans if plan.import_user]
    imported_plans_by_telegram_id = {plan.telegram_id: plan for plan in imported_plans}
    referral_counts_by_telegram_id: Counter[int] = Counter()

    for plan in imported_plans:
        if not plan.inviter_importable or plan.legacy_user.inviter_id is None:
            continue
        referral_counts_by_telegram_id[plan.legacy_user.inviter_id] += 1

    try:
        total_accounts_batches = _batch_count(
            len(imported_plans), normalized_batch_size
        )
        processed_accounts = 0
        for batch_index, batch in enumerate(
            _chunked(imported_plans, normalized_batch_size), start=1
        ):
            async with session_factory() as session:
                batch_telegram_ids = [plan.telegram_id for plan in batch]
                existing_accounts = {
                    account.telegram_id: account
                    for account in (
                        await session.execute(
                            select(Account).where(
                                Account.telegram_id.in_(batch_telegram_ids)
                            )
                        )
                    )
                    .scalars()
                    .all()
                    if account.telegram_id is not None
                }

                for plan in batch:
                    account = existing_accounts.get(plan.telegram_id)
                    if account is None:
                        account = Account(
                            id=plan.account_uuid, telegram_id=plan.telegram_id
                        )
                        session.add(account)
                        summary["accounts_created"] += 1
                    else:
                        summary["accounts_updated"] += 1

                    account.telegram_id = plan.telegram_id
                    account.username = plan.legacy_user.username
                    account.locale = plan.legacy_user.language_code
                    account.status = AccountStatus.ACTIVE
                    account.referral_code = plan.imported_referral_code
                    account.referral_earnings = plan.referral_balance
                    account.created_at = (
                        plan.legacy_user.created_at
                        or account.created_at
                        or datetime.now(UTC)
                    )
                    if plan.telegram_bot_blocked:
                        account.telegram_bot_blocked_at = (
                            account.telegram_bot_blocked_at or datetime.now(UTC)
                        )
                        summary["accounts_marked_telegram_bot_blocked"] += 1
                    else:
                        account.telegram_bot_blocked_at = None

                    if plan.canonical_subscription is None:
                        account.remnawave_user_uuid = None
                        account.subscription_url = None
                        account.subscription_status = None
                        account.subscription_expires_at = None
                        account.subscription_last_synced_at = None
                        account.subscription_is_trial = False
                    else:
                        account.remnawave_user_uuid = plan.target_remnawave_uuid
                        account.subscription_url = (
                            plan.canonical_subscription.subscription_url
                        )
                        account.subscription_status = _desired_subscription_status(
                            expires_at=plan.target_subscription_expires_at
                        )
                        account.subscription_expires_at = (
                            plan.target_subscription_expires_at
                        )
                        account.subscription_last_synced_at = (
                            plan.canonical_subscription.updated_at
                        )
                        account.subscription_is_trial = False

                await session.commit()

            processed_accounts += len(batch)
            _print_batch_progress(
                "DB import/accounts",
                batch_index=batch_index,
                total_batches=total_accounts_batches,
                processed=processed_accounts,
                total_items=len(imported_plans),
            )

        processed_referrals = 0
        for batch_index, batch in enumerate(
            _chunked(imported_plans, normalized_batch_size), start=1
        ):
            async with session_factory() as session:
                batch_telegram_ids = [plan.telegram_id for plan in batch]
                related_telegram_ids = set(batch_telegram_ids)
                for plan in batch:
                    if (
                        plan.inviter_importable
                        and plan.legacy_user.inviter_id is not None
                    ):
                        related_telegram_ids.add(plan.legacy_user.inviter_id)

                accounts_by_telegram_id = {
                    account.telegram_id: account
                    for account in (
                        await session.execute(
                            select(Account).where(
                                Account.telegram_id.in_(sorted(related_telegram_ids))
                            )
                        )
                    )
                    .scalars()
                    .all()
                    if account.telegram_id is not None
                }
                batch_accounts_by_telegram_id = {
                    telegram_id: accounts_by_telegram_id[telegram_id]
                    for telegram_id in batch_telegram_ids
                }
                account_ids = [
                    account.id for account in batch_accounts_by_telegram_id.values()
                ]
                existing_attributions: dict[uuid.UUID, ReferralAttribution] = {}
                if account_ids:
                    existing_attributions = {
                        attribution.referred_account_id: attribution
                        for attribution in (
                            await session.execute(
                                select(ReferralAttribution).where(
                                    ReferralAttribution.referred_account_id.in_(
                                        account_ids
                                    )
                                )
                            )
                        )
                        .scalars()
                        .all()
                    }

                for plan in batch:
                    account = batch_accounts_by_telegram_id[plan.telegram_id]
                    account.referred_by_account_id = None
                    account.referrals_count = referral_counts_by_telegram_id[
                        plan.telegram_id
                    ]

                for plan in batch:
                    if (
                        not plan.inviter_importable
                        or plan.legacy_user.inviter_id is None
                    ):
                        continue

                    account = batch_accounts_by_telegram_id[plan.telegram_id]
                    referrer_plan = imported_plans_by_telegram_id[
                        plan.legacy_user.inviter_id
                    ]
                    referrer_account = accounts_by_telegram_id[
                        plan.legacy_user.inviter_id
                    ]
                    account.referred_by_account_id = referrer_account.id
                    referral_code = (
                        referrer_plan.imported_referral_code
                        or referrer_plan.legacy_user.username
                        or "legacy"
                    )
                    attribution = existing_attributions.get(account.id)
                    if attribution is None:
                        attribution = ReferralAttribution(
                            referrer_account_id=referrer_account.id,
                            referred_account_id=account.id,
                            referral_code=referral_code,
                            created_at=_as_utc_naive(plan.legacy_user.created_at)
                            or _as_utc_naive(datetime.now(UTC)),
                        )
                        session.add(attribution)
                        summary["referral_attributions_created"] += 1
                    else:
                        attribution.referrer_account_id = referrer_account.id
                        attribution.referral_code = referral_code
                        if plan.legacy_user.created_at is not None:
                            attribution.created_at = _as_utc_naive(
                                plan.legacy_user.created_at
                            )
                        summary["referral_attributions_updated"] += 1

                await session.commit()

            processed_referrals += len(batch)
            _print_batch_progress(
                "DB import/referrals",
                batch_index=batch_index,
                total_batches=total_accounts_batches,
                processed=processed_referrals,
                total_items=len(imported_plans),
            )

        provider_map = {
            "yookassa": PaymentProvider.YOOKASSA,
            "telegram_stars": PaymentProvider.TELEGRAM_STARS,
        }
        status_map = {
            "succeeded": PaymentStatus.SUCCEEDED,
            "cancelled": PaymentStatus.CANCELLED,
        }
        payment_import_plans = [
            plan for plan in imported_plans if plan.terminal_payments
        ]
        total_payment_batches = _batch_count(
            len(payment_import_plans), normalized_batch_size
        )
        processed_payment_accounts = 0
        for batch_index, batch in enumerate(
            _chunked(payment_import_plans, normalized_batch_size), start=1
        ):
            async with session_factory() as session:
                batch_telegram_ids = [plan.telegram_id for plan in batch]
                accounts_by_telegram_id = {
                    account.telegram_id: account
                    for account in (
                        await session.execute(
                            select(Account).where(
                                Account.telegram_id.in_(batch_telegram_ids)
                            )
                        )
                    )
                    .scalars()
                    .all()
                    if account.telegram_id is not None
                }

                payment_lookup_keys: list[tuple[PaymentProvider, str]] = []
                grant_reference_ids: list[str] = []
                for plan in batch:
                    for legacy_payment, grant_plan in zip(
                        plan.terminal_payments, plan.payment_grant_plans
                    ):
                        provider = provider_map[grant_plan.provider_code]
                        provider_payment_id = (
                            legacy_payment.external_payment_id
                            or f"legacy-payment-{legacy_payment.id}"
                        )
                        payment_lookup_keys.append((provider, provider_payment_id))
                        if grant_plan.grant_importable:
                            grant_reference_ids.append(str(legacy_payment.id))

                existing_payments: dict[tuple[PaymentProvider, str], Payment] = {}
                if payment_lookup_keys:
                    existing_payments = {
                        (payment.provider, payment.provider_payment_id): payment
                        for payment in (
                            await session.execute(
                                select(Payment).where(
                                    tuple_(
                                        Payment.provider,
                                        Payment.provider_payment_id,
                                    ).in_(payment_lookup_keys)
                                )
                            )
                        )
                        .scalars()
                        .all()
                    }

                existing_grants: dict[
                    tuple[str | None, str | None], SubscriptionGrant
                ] = {}
                if grant_reference_ids:
                    existing_grants = {
                        (grant.reference_type, grant.reference_id): grant
                        for grant in (
                            await session.execute(
                                select(SubscriptionGrant).where(
                                    SubscriptionGrant.reference_type
                                    == LEGACY_PAYMENT_REFERENCE_TYPE,
                                    SubscriptionGrant.reference_id.in_(
                                        grant_reference_ids
                                    ),
                                )
                            )
                        )
                        .scalars()
                        .all()
                    }

                for plan in batch:
                    account = accounts_by_telegram_id[plan.telegram_id]
                    for legacy_payment, grant_plan in zip(
                        plan.terminal_payments, plan.payment_grant_plans
                    ):
                        provider = provider_map[grant_plan.provider_code]
                        provider_payment_id = (
                            legacy_payment.external_payment_id
                            or f"legacy-payment-{legacy_payment.id}"
                        )
                        payment_key = (provider, provider_payment_id)
                        payment = existing_payments.get(payment_key)

                        if payment is None:
                            payment = Payment(
                                account_id=account.id,
                                provider=provider,
                                flow_type=PaymentFlowType.DIRECT_PLAN_PURCHASE,
                                status=status_map[grant_plan.target_payment_status],
                                amount=legacy_payment.amount,
                                currency=legacy_payment.currency,
                                provider_payment_id=provider_payment_id,
                                external_reference=f"legacy-payment:{legacy_payment.id}",
                                idempotency_key=f"legacy-payment:{legacy_payment.id}",
                                plan_code=grant_plan.plan_code,
                                description=f"Legacy import payment #{legacy_payment.id}",
                                expires_at=None,
                                finalized_at=legacy_payment.created_at,
                                raw_payload={
                                    "source": LEGACY_SOURCE,
                                    "legacy_payment_id": legacy_payment.id,
                                    "legacy_user_id": legacy_payment.user_id,
                                    "legacy_subscription_id": legacy_payment.subscription_id,
                                    "legacy_tariff_id": legacy_payment.tariff_id,
                                },
                                request_metadata={
                                    "migration_source": LEGACY_SOURCE,
                                    "legacy_payment_id": legacy_payment.id,
                                },
                                created_at=_as_utc_naive(legacy_payment.created_at)
                                or _as_utc_naive(datetime.now(UTC)),
                                updated_at=_as_utc_naive(legacy_payment.created_at)
                                or _as_utc_naive(datetime.now(UTC)),
                            )
                            session.add(payment)
                            existing_payments[payment_key] = payment
                            summary["payments_created"] += 1
                        else:
                            payment.account_id = account.id
                            payment.status = status_map[
                                grant_plan.target_payment_status
                            ]
                            payment.amount = legacy_payment.amount
                            payment.currency = legacy_payment.currency
                            payment.plan_code = grant_plan.plan_code
                            payment.description = (
                                f"Legacy import payment #{legacy_payment.id}"
                            )
                            payment.finalized_at = legacy_payment.created_at
                            payment.raw_payload = {
                                "source": LEGACY_SOURCE,
                                "legacy_payment_id": legacy_payment.id,
                                "legacy_user_id": legacy_payment.user_id,
                                "legacy_subscription_id": legacy_payment.subscription_id,
                                "legacy_tariff_id": legacy_payment.tariff_id,
                            }
                            payment.request_metadata = {
                                "migration_source": LEGACY_SOURCE,
                                "legacy_payment_id": legacy_payment.id,
                            }
                            summary["payments_updated"] += 1

                        await session.flush()

                        if not grant_plan.grant_importable:
                            continue

                        grant_key = (
                            LEGACY_PAYMENT_REFERENCE_TYPE,
                            str(legacy_payment.id),
                        )
                        grant = existing_grants.get(grant_key)
                        if grant is None:
                            grant = SubscriptionGrant(
                                account_id=account.id,
                                payment_id=payment.id,
                                purchase_source="direct_payment",
                                reference_type=LEGACY_PAYMENT_REFERENCE_TYPE,
                                reference_id=str(legacy_payment.id),
                                plan_code=grant_plan.plan_code or "plan_1m",
                                amount=legacy_payment.amount,
                                currency=legacy_payment.currency,
                                duration_days=grant_plan.duration_days or 30,
                                base_expires_at=grant_plan.base_expires_at
                                or legacy_payment.created_at
                                or datetime.now(UTC),
                                target_expires_at=grant_plan.target_expires_at
                                or legacy_payment.created_at
                                or datetime.now(UTC),
                                applied_at=legacy_payment.created_at
                                or datetime.now(UTC),
                                created_at=_as_utc_naive(legacy_payment.created_at)
                                or _as_utc_naive(datetime.now(UTC)),
                            )
                            session.add(grant)
                            existing_grants[grant_key] = grant
                            summary["subscription_grants_created"] += 1
                        else:
                            grant.account_id = account.id
                            grant.payment_id = payment.id
                            grant.plan_code = grant_plan.plan_code or grant.plan_code
                            grant.amount = legacy_payment.amount
                            grant.currency = legacy_payment.currency
                            grant.duration_days = (
                                grant_plan.duration_days or grant.duration_days
                            )
                            if grant_plan.base_expires_at is not None:
                                grant.base_expires_at = grant_plan.base_expires_at
                            if grant_plan.target_expires_at is not None:
                                grant.target_expires_at = grant_plan.target_expires_at
                            grant.applied_at = (
                                legacy_payment.created_at or grant.applied_at
                            )
                            summary["subscription_grants_updated"] += 1

                await session.commit()

            processed_payment_accounts += len(batch)
            _print_batch_progress(
                "DB import/payments",
                batch_index=batch_index,
                total_batches=total_payment_batches,
                processed=processed_payment_accounts,
                total_items=len(payment_import_plans),
            )

        balance_plans = [plan for plan in imported_plans if plan.referral_balance > 0]
        total_balance_batches = _batch_count(len(balance_plans), normalized_batch_size)
        processed_balance_accounts = 0
        for batch_index, batch in enumerate(
            _chunked(balance_plans, normalized_batch_size), start=1
        ):
            async with session_factory() as session:
                batch_telegram_ids = [plan.telegram_id for plan in batch]
                accounts_by_telegram_id = {
                    account.telegram_id: account
                    for account in (
                        await session.execute(
                            select(Account).where(
                                Account.telegram_id.in_(batch_telegram_ids)
                            )
                        )
                    )
                    .scalars()
                    .all()
                    if account.telegram_id is not None
                }
                idempotency_keys = [
                    f"legacy-referral-balance:{plan.telegram_id}" for plan in batch
                ]
                existing_ledger_idempotency_keys = {
                    key
                    for key in (
                        await session.execute(
                            select(LedgerEntry.idempotency_key).where(
                                LedgerEntry.idempotency_key.in_(idempotency_keys)
                            )
                        )
                    )
                    .scalars()
                    .all()
                    if key is not None
                }

                for plan in batch:
                    account = accounts_by_telegram_id[plan.telegram_id]
                    idempotency_key = f"legacy-referral-balance:{plan.telegram_id}"
                    if idempotency_key in existing_ledger_idempotency_keys:
                        summary["ledger_referral_balance_entries_reused"] += 1
                    else:
                        summary["ledger_referral_balance_entries_created"] += 1
                    entry = await apply_credit_in_transaction(
                        session,
                        account_id=account.id,
                        amount=plan.referral_balance,
                        entry_type=LedgerEntryType.ADMIN_CREDIT,
                        reference_type=LEGACY_REFERRAL_BALANCE_REFERENCE_TYPE,
                        reference_id=str(plan.telegram_id),
                        comment="Legacy referral balance import",
                        idempotency_key=idempotency_key,
                    )
                    existing_ledger_idempotency_keys.add(idempotency_key)
                    del entry

                await session.commit()

            processed_balance_accounts += len(batch)
            _print_batch_progress(
                "DB import/referral-balances",
                batch_index=batch_index,
                total_batches=total_balance_batches,
                processed=processed_balance_accounts,
                total_items=len(balance_plans),
            )
    finally:
        await engine.dispose()

    return {
        "accounts_created": summary["accounts_created"],
        "accounts_updated": summary["accounts_updated"],
        "accounts_marked_telegram_bot_blocked": summary[
            "accounts_marked_telegram_bot_blocked"
        ],
        "referral_attributions_created": summary["referral_attributions_created"],
        "referral_attributions_updated": summary["referral_attributions_updated"],
        "payments_created": summary["payments_created"],
        "payments_updated": summary["payments_updated"],
        "subscription_grants_created": summary["subscription_grants_created"],
        "subscription_grants_updated": summary["subscription_grants_updated"],
        "ledger_referral_balance_entries_created": summary[
            "ledger_referral_balance_entries_created"
        ],
        "ledger_referral_balance_entries_reused": summary[
            "ledger_referral_balance_entries_reused"
        ],
    }


async def sync_remnawave_state(
    migration_plan: MigrationPlan, *, database_url: str, batch_size: int
) -> tuple[dict[str, Any], list[RemnawaveManualReviewItem]]:
    from sqlalchemy import select

    from app.db.models import Account
    from app.integrations.remnawave import get_remnawave_gateway
    from app.services.purchases import apply_remote_subscription_snapshot

    normalized_batch_size = _ensure_positive_batch_size(
        batch_size, name="remnawave_batch_size"
    )
    engine, session_factory = await _open_target_session_factory(database_url)
    gateway = get_remnawave_gateway()
    summary = Counter[str]()
    desired_plans = [
        plan
        for plan in migration_plan.account_plans
        if plan.import_user and plan.canonical_subscription is not None
    ]
    summary["desired_active_accounts"] = len(desired_plans)
    desired_uuid_set: set[uuid.UUID] = set()

    try:
        total_sync_batches = _batch_count(len(desired_plans), normalized_batch_size)
        processed_sync_accounts = 0
        for batch_index, batch in enumerate(
            _chunked(desired_plans, normalized_batch_size), start=1
        ):
            async with session_factory() as session:
                batch_telegram_ids = [plan.telegram_id for plan in batch]
                accounts_by_telegram_id = {
                    account.telegram_id: account
                    for account in (
                        await session.execute(
                            select(Account).where(
                                Account.telegram_id.in_(batch_telegram_ids)
                            )
                        )
                    )
                    .scalars()
                    .all()
                    if account.telegram_id is not None
                }

                for plan in batch:
                    account = accounts_by_telegram_id.get(plan.telegram_id)
                    if account is None:
                        raise RuntimeError(
                            f"Target account missing in DB for telegram_id={plan.telegram_id}. "
                            "Run --apply-db first."
                        )

                    desired_uuid = (
                        account.remnawave_user_uuid
                        or plan.target_remnawave_uuid
                        or account.id
                    )
                    desired_uuid_set.add(desired_uuid)
                    remote_user = await gateway.upsert_user(
                        user_uuid=desired_uuid,
                        expire_at=account.subscription_expires_at
                        or plan.target_subscription_expires_at
                        or datetime.now(UTC),
                        email=account.email,
                        telegram_id=account.telegram_id,
                        status=_desired_subscription_status(
                            expires_at=account.subscription_expires_at
                        ),
                        is_trial=bool(account.subscription_is_trial),
                        hwid_device_limit=plan.target_hwid_device_limit,
                    )
                    apply_remote_subscription_snapshot(account, remote_user)
                    summary["upserts_completed"] += 1

                await session.commit()

            processed_sync_accounts += len(batch)
            _print_batch_progress(
                "Remnawave sync/upserts",
                batch_index=batch_index,
                total_batches=total_sync_batches,
                processed=processed_sync_accounts,
                total_items=len(desired_plans),
            )

        cleanup_candidates = sorted(
            uuid_value
            for uuid_value in migration_plan.removable_legacy_remnawave_uuids
            if uuid_value not in desired_uuid_set
        )
        summary["legacy_cleanup_candidates"] = len(cleanup_candidates)
        total_cleanup_batches = _batch_count(
            len(cleanup_candidates), normalized_batch_size
        )
        processed_cleanup_candidates = 0
        for batch_index, batch in enumerate(
            _chunked(cleanup_candidates, normalized_batch_size), start=1
        ):
            for user_uuid in batch:
                remote_user = await gateway.get_user_by_uuid(user_uuid)
                if remote_user is None:
                    summary["legacy_cleanup_missing"] += 1
                    continue
                await gateway.delete_user(user_uuid)
                summary["legacy_cleanup_deleted"] += 1
            processed_cleanup_candidates += len(batch)
            _print_batch_progress(
                "Remnawave sync/cleanup",
                batch_index=batch_index,
                total_batches=total_cleanup_batches,
                processed=processed_cleanup_candidates,
                total_items=len(cleanup_candidates),
            )

        remote_inventory = await gateway.get_all_users()
    finally:
        await engine.dispose()

    desired_uuid_strs = {str(item) for item in desired_uuid_set}
    known_legacy_uuid_strs = {
        str(item) for item in migration_plan.all_legacy_remnawave_uuids
    }
    manual_review_items = [
        RemnawaveManualReviewItem(
            uuid=str(user.uuid),
            username=user.username,
            email=user.email,
            telegram_id=user.telegram_id,
            status=user.status,
            expire_at=_serialize_datetime(user.expire_at),
            hwid_device_limit=user.hwid_device_limit,
            reason="not_matched_to_imported_active_account",
            known_legacy_uuid=str(user.uuid) in known_legacy_uuid_strs,
        )
        for user in remote_inventory
        if str(user.uuid) not in desired_uuid_strs
    ]

    summary["manual_review_candidates"] = len(manual_review_items)
    return (
        {
            "desired_active_accounts": summary["desired_active_accounts"],
            "upserts_completed": summary["upserts_completed"],
            "legacy_cleanup_candidates": summary["legacy_cleanup_candidates"],
            "legacy_cleanup_deleted": summary["legacy_cleanup_deleted"],
            "legacy_cleanup_missing": summary["legacy_cleanup_missing"],
            "manual_review_candidates": summary["manual_review_candidates"],
        },
        manual_review_items,
    )


async def report_remnawave_state(
    migration_plan: MigrationPlan,
) -> tuple[dict[str, Any], list[RemnawaveManualReviewItem]]:
    from app.integrations.remnawave import get_remnawave_gateway

    gateway = get_remnawave_gateway()
    desired_plans = [
        plan
        for plan in migration_plan.account_plans
        if plan.import_user and plan.canonical_subscription is not None
    ]
    desired_uuid_set = {
        str(plan.target_remnawave_uuid)
        for plan in desired_plans
        if plan.target_remnawave_uuid is not None
    }
    cleanup_candidates = {
        str(uuid_value)
        for uuid_value in migration_plan.removable_legacy_remnawave_uuids
        if str(uuid_value) not in desired_uuid_set
    }

    remote_inventory = await gateway.get_all_users()
    remote_uuid_set = {str(user.uuid) for user in remote_inventory}
    known_legacy_uuid_strs = {
        str(item) for item in migration_plan.all_legacy_remnawave_uuids
    }
    manual_review_items = [
        RemnawaveManualReviewItem(
            uuid=str(user.uuid),
            username=user.username,
            email=user.email,
            telegram_id=user.telegram_id,
            status=user.status,
            expire_at=_serialize_datetime(user.expire_at),
            hwid_device_limit=user.hwid_device_limit,
            reason="not_matched_to_imported_active_account",
            known_legacy_uuid=str(user.uuid) in known_legacy_uuid_strs,
        )
        for user in remote_inventory
        if str(user.uuid) not in desired_uuid_set
    ]

    summary = {
        "desired_active_accounts": len(desired_plans),
        "legacy_cleanup_candidates": len(cleanup_candidates),
        "legacy_cleanup_present_in_panel": sum(
            1 for item in cleanup_candidates if item in remote_uuid_set
        ),
        "manual_review_candidates": len(manual_review_items),
    }
    return summary, manual_review_items


async def _async_main(args: argparse.Namespace) -> dict[str, Any]:
    if not args.legacy_db.exists():
        raise SystemExit(f"Legacy DB not found: {args.legacy_db}")
    if not args.plans_json.exists():
        raise SystemExit(f"Plans JSON not found: {args.plans_json}")
    _ensure_positive_batch_size(args.db_batch_size, name="db_batch_size")
    _ensure_positive_batch_size(args.remnawave_batch_size, name="remnawave_batch_size")

    current_plans_by_duration = _load_current_plans(args.plans_json)
    connection = _connect_legacy_db(args.legacy_db)
    try:
        legacy_tariffs = _load_legacy_tariffs(connection)
        users = _load_legacy_users(connection)
        subscriptions_by_user = _load_legacy_subscriptions(connection)
        payments_by_user = _load_legacy_payments(connection)
    finally:
        connection.close()

    migration_plan = build_migration_plan(
        legacy_db_path=args.legacy_db,
        current_plans_path=args.plans_json,
        users=users,
        subscriptions_by_user=subscriptions_by_user,
        payments_by_user=payments_by_user,
        legacy_tariffs=legacy_tariffs,
        current_plans_by_duration=current_plans_by_duration,
        sample_limit=args.sample_limit,
    )
    report = migration_plan.to_report_dict()

    do_dry_run = args.dry_run or (
        not args.apply_db and not args.sync_remnawave and not args.report_remnawave
    )
    if do_dry_run:
        _print_report(report)

    database_url = args.database_url
    if (args.apply_db or args.sync_remnawave) and not database_url:
        from app.core.config import settings

        database_url = settings.database_url
    if (args.apply_db or args.sync_remnawave) and not database_url:
        raise SystemExit(
            "Target database URL is required for --apply-db or --sync-remnawave"
        )

    if args.apply_db:
        db_summary = await apply_db_import(
            migration_plan,
            database_url=database_url,
            batch_size=args.db_batch_size,
        )
        report["db_apply_summary"] = db_summary
        _print_apply_db_summary(db_summary)

    if args.report_remnawave:
        (
            remnawave_report_summary,
            remnawave_manual_review,
        ) = await report_remnawave_state(
            migration_plan,
        )
        report["remnawave_report_summary"] = remnawave_report_summary
        report["remnawave_manual_review"] = [
            {
                "uuid": item.uuid,
                "username": item.username,
                "email": item.email,
                "telegram_id": item.telegram_id,
                "status": item.status,
                "expire_at": item.expire_at,
                "hwid_device_limit": item.hwid_device_limit,
                "reason": item.reason,
                "known_legacy_uuid": item.known_legacy_uuid,
            }
            for item in remnawave_manual_review
        ]
        _print_remnawave_report_summary(
            remnawave_report_summary, remnawave_manual_review
        )

    if args.sync_remnawave:
        sync_summary, manual_review_items = await sync_remnawave_state(
            migration_plan,
            database_url=database_url,
            batch_size=args.remnawave_batch_size,
        )
        report["remnawave_sync_summary"] = sync_summary
        report["remnawave_manual_review"] = [
            {
                "uuid": item.uuid,
                "username": item.username,
                "email": item.email,
                "telegram_id": item.telegram_id,
                "status": item.status,
                "expire_at": item.expire_at,
                "hwid_device_limit": item.hwid_device_limit,
                "reason": item.reason,
                "known_legacy_uuid": item.known_legacy_uuid,
            }
            for item in manual_review_items
        ]
        _print_sync_summary(sync_summary, manual_review_items)

    return report


def main() -> int:
    args = _parse_args()
    report = asyncio.run(_async_main(args))

    if args.output_json is not None:
        args.output_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print()
        print(f"JSON report written to: {args.output_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
