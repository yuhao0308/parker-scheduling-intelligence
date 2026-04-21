"""Baseline schema plus confirmation/notification additions.

This is the first migration in the project. It bootstraps the full
SQLAlchemy schema via ``Base.metadata.create_all`` on an empty DB, then
layers in the confirmation-flow deltas (schedule_entry columns +
simulated_notification table). On an already-populated dev DB the
create_all call is a no-op thanks to ``checkfirst=True``.

Revision ID: 0001_baseline_with_confirmations
Revises:
Create Date: 2026-04-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.models import Base  # noqa: E402 — need Base populated

revision = "0001_baseline_with_confirmations"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Create every table declared on the metadata. On a fresh DB this
    # bootstraps the entire baseline schema. On an already-populated dev DB
    # it's a no-op thanks to checkfirst=True.
    Base.metadata.create_all(bind=bind, checkfirst=True)

    # 1b. Explicitly create simulated_notification and its enums. We do this
    # separately because Base.metadata.create_all inside Alembic's transaction
    # sometimes skips newer tables; a direct per-table create is reliable.
    existing_tables_raw = {
        row[0]
        for row in bind.exec_driver_sql(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    }
    if "simulated_notification" not in existing_tables_raw:
        for enum_ddl in (
            "DO $$ BEGIN CREATE TYPE notification_channel AS ENUM "
            "('SMS', 'EMAIL'); EXCEPTION WHEN duplicate_object THEN null; END $$",
            "DO $$ BEGIN CREATE TYPE notification_kind AS ENUM "
            "('CONFIRM_SHIFT', 'CALLOUT_OUTREACH'); "
            "EXCEPTION WHEN duplicate_object THEN null; END $$",
            "DO $$ BEGIN CREATE TYPE notification_status AS ENUM "
            "('SENT', 'ACCEPTED', 'DECLINED', 'TIMEOUT', 'SKIPPED', 'CANCELED'); "
            "EXCEPTION WHEN duplicate_object THEN null; END $$",
        ):
            bind.exec_driver_sql(enum_ddl)
        op.create_table(
            "simulated_notification",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "schedule_entry_id",
                sa.Integer,
                sa.ForeignKey("schedule_entry.id"),
                nullable=True,
            ),
            sa.Column(
                "callout_id",
                sa.Integer,
                sa.ForeignKey("callout.id"),
                nullable=True,
            ),
            sa.Column(
                "recommendation_log_id",
                sa.Integer,
                sa.ForeignKey("recommendation_log.id"),
                nullable=True,
            ),
            sa.Column(
                "employee_id",
                sa.String(50),
                sa.ForeignKey("staff_master.employee_id"),
                nullable=False,
            ),
            sa.Column(
                "channel",
                postgresql.ENUM(
                    "SMS", "EMAIL",
                    name="notification_channel", create_type=False,
                ),
                nullable=False,
            ),
            sa.Column(
                "kind",
                postgresql.ENUM(
                    "CONFIRM_SHIFT", "CALLOUT_OUTREACH",
                    name="notification_kind", create_type=False,
                ),
                nullable=False,
            ),
            sa.Column(
                "status",
                postgresql.ENUM(
                    "SENT", "ACCEPTED", "DECLINED", "TIMEOUT", "SKIPPED", "CANCELED",
                    name="notification_status", create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("payload_text", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        )

    # 2. On existing DBs where schedule_entry pre-dates this migration, add
    # the new confirmation columns. Query information_schema directly; the
    # SQLAlchemy inspector's cache can lag inside an Alembic transaction.
    existing_cols = {
        row[0]
        for row in bind.exec_driver_sql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'schedule_entry'"
        ).fetchall()
    }

    if "confirmation_status" not in existing_cols:
        bind.exec_driver_sql(
            "DO $$ BEGIN "
            "CREATE TYPE confirmation_status AS ENUM "
            "('UNSENT', 'PENDING', 'ACCEPTED', 'DECLINED', 'REPLACED'); "
            "EXCEPTION WHEN duplicate_object THEN null; END $$"
        )
        op.add_column(
            "schedule_entry",
            sa.Column(
                "confirmation_status",
                postgresql.ENUM(
                    "UNSENT", "PENDING", "ACCEPTED", "DECLINED", "REPLACED",
                    name="confirmation_status",
                    create_type=False,
                ),
                nullable=False,
                server_default="UNSENT",
            ),
        )
    if "confirmation_sent_at" not in existing_cols:
        op.add_column(
            "schedule_entry",
            sa.Column("confirmation_sent_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "confirmation_responded_at" not in existing_cols:
        op.add_column(
            "schedule_entry",
            sa.Column(
                "confirmation_responded_at", sa.DateTime(timezone=True), nullable=True
            ),
        )
    if "replaced_by_entry_id" not in existing_cols:
        op.add_column(
            "schedule_entry",
            sa.Column(
                "replaced_by_entry_id",
                sa.Integer(),
                sa.ForeignKey("schedule_entry.id"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    # Non-reversible baseline. Drop only the columns and table we explicitly
    # added so pre-existing data is preserved.
    op.drop_column("schedule_entry", "replaced_by_entry_id")
    op.drop_column("schedule_entry", "confirmation_responded_at")
    op.drop_column("schedule_entry", "confirmation_sent_at")
    op.drop_column("schedule_entry", "confirmation_status")
    op.execute("DROP TYPE IF EXISTS confirmation_status")
    op.drop_table("simulated_notification")
    op.execute("DROP TYPE IF EXISTS notification_channel")
    op.execute("DROP TYPE IF EXISTS notification_kind")
    op.execute("DROP TYPE IF EXISTS notification_status")
