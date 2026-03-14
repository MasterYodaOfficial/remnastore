"""add broadcast runtime runs

Revision ID: 20260314_add_broadcast_runs_runtime
Revises: 20260314_add_broadcasts
Create Date: 2026-03-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision = "20260314_add_broadcast_runs_runtime"
down_revision = "20260314_add_broadcasts"
branch_labels = None
depends_on = None


def _map_run_type(scheduled_at: object | None) -> str:
    return "scheduled" if scheduled_at is not None else "send_now"


def _map_run_status(broadcast_status: str) -> str:
    if broadcast_status == "paused":
        return "paused"
    if broadcast_status == "completed":
        return "completed"
    if broadcast_status == "failed":
        return "failed"
    if broadcast_status == "cancelled":
        return "cancelled"
    return "running"


def upgrade() -> None:
    op.create_table(
        "broadcast_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("broadcast_id", sa.Integer(), nullable=False),
        sa.Column("run_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("triggered_by_admin_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_total_accounts", sa.Integer(), nullable=False),
        sa.Column("snapshot_in_app_targets", sa.Integer(), nullable=False),
        sa.Column("snapshot_telegram_targets", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["broadcast_id"], ["broadcasts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_broadcast_runs_broadcast_created",
        "broadcast_runs",
        ["broadcast_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_broadcast_runs_status_created",
        "broadcast_runs",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_broadcast_runs_type_created",
        "broadcast_runs",
        ["run_type", "created_at"],
        unique=False,
    )

    with op.batch_alter_table("broadcast_deliveries") as batch_op:
        batch_op.add_column(sa.Column("run_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("notification_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_broadcast_deliveries_run_id",
            "broadcast_runs",
            ["run_id"],
            ["id"],
            ondelete="CASCADE",
        )

    connection = op.get_bind()
    delivery_rows: Sequence[sa.Row] = connection.execute(
        sa.text(
            """
            SELECT DISTINCT d.broadcast_id
            FROM broadcast_deliveries AS d
            """
        )
    ).fetchall()

    for row in delivery_rows:
        broadcast_id = int(row.broadcast_id)
        broadcast = connection.execute(
            sa.text(
                """
                SELECT
                    id,
                    status,
                    scheduled_at,
                    launched_at,
                    completed_at,
                    cancelled_at,
                    last_error,
                    created_at,
                    created_by_admin_id,
                    estimated_total_accounts,
                    estimated_in_app_recipients,
                    estimated_telegram_recipients
                FROM broadcasts
                WHERE id = :broadcast_id
                """
            ),
            {"broadcast_id": broadcast_id},
        ).mappings().first()
        if broadcast is None:
            continue

        run_insert = connection.execute(
            sa.text(
                """
                INSERT INTO broadcast_runs (
                    broadcast_id,
                    run_type,
                    status,
                    triggered_by_admin_id,
                    snapshot_total_accounts,
                    snapshot_in_app_targets,
                    snapshot_telegram_targets,
                    started_at,
                    completed_at,
                    cancelled_at,
                    last_error
                ) VALUES (
                    :broadcast_id,
                    :run_type,
                    :status,
                    :triggered_by_admin_id,
                    :snapshot_total_accounts,
                    :snapshot_in_app_targets,
                    :snapshot_telegram_targets,
                    :started_at,
                    :completed_at,
                    :cancelled_at,
                    :last_error
                )
                RETURNING id
                """
            ),
            {
                "broadcast_id": broadcast_id,
                "run_type": _map_run_type(broadcast["scheduled_at"]),
                "status": _map_run_status(str(broadcast["status"])),
                "triggered_by_admin_id": broadcast["created_by_admin_id"],
                "snapshot_total_accounts": int(broadcast["estimated_total_accounts"] or 0),
                "snapshot_in_app_targets": int(broadcast["estimated_in_app_recipients"] or 0),
                "snapshot_telegram_targets": int(broadcast["estimated_telegram_recipients"] or 0),
                "started_at": broadcast["launched_at"] or broadcast["created_at"],
                "completed_at": broadcast["completed_at"],
                "cancelled_at": broadcast["cancelled_at"],
                "last_error": broadcast["last_error"],
            },
        )
        run_id = int(run_insert.scalar_one())
        connection.execute(
            sa.text(
                """
                UPDATE broadcast_deliveries
                SET run_id = :run_id
                WHERE broadcast_id = :broadcast_id
                """
            ),
            {"run_id": run_id, "broadcast_id": broadcast_id},
        )

    with op.batch_alter_table("broadcast_deliveries") as batch_op:
        batch_op.drop_constraint("uq_broadcast_deliveries_target_channel", type_="unique")
        batch_op.create_unique_constraint(
            "uq_broadcast_deliveries_target_channel",
            ["run_id", "account_id", "channel"],
        )
        batch_op.create_index(
            "ix_broadcast_deliveries_run_status",
            ["run_id", "status"],
            unique=False,
        )
        batch_op.alter_column("run_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("broadcast_deliveries") as batch_op:
        batch_op.alter_column("run_id", existing_type=sa.Integer(), nullable=True)
        batch_op.drop_index("ix_broadcast_deliveries_run_status")
        batch_op.drop_constraint("uq_broadcast_deliveries_target_channel", type_="unique")
        batch_op.create_unique_constraint(
            "uq_broadcast_deliveries_target_channel",
            ["broadcast_id", "account_id", "channel"],
        )
        batch_op.drop_constraint("fk_broadcast_deliveries_run_id", type_="foreignkey")
        batch_op.drop_column("notification_id")
        batch_op.drop_column("run_id")

    op.drop_index("ix_broadcast_runs_type_created", table_name="broadcast_runs")
    op.drop_index("ix_broadcast_runs_status_created", table_name="broadcast_runs")
    op.drop_index("ix_broadcast_runs_broadcast_created", table_name="broadcast_runs")
    op.drop_table("broadcast_runs")
