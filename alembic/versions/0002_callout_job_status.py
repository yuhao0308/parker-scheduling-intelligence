"""Add async job status columns to callout.

Adds ``status``, ``completed_at``, and ``error_message`` to the callout
table so the recommendation pipeline can run as a background task and be
polled by the frontend (page-reload-safe).

Existing rows are back-filled to ``COMPLETED`` — they already had their
recommendations generated synchronously pre-migration, so surfacing them
as RUNNING would make them look stuck.

Revision ID: 0002_callout_job_status
Revises: 0001_baseline_with_confirmations
Create Date: 2026-04-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_callout_job_status"
down_revision = "0001_baseline_with_confirmations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Create the enum type if it doesn't already exist.
    bind.exec_driver_sql(
        "DO $$ BEGIN "
        "CREATE TYPE callout_status AS ENUM "
        "('PENDING', 'RUNNING', 'COMPLETED', 'FAILED'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$"
    )

    existing_cols = {
        row[0]
        for row in bind.exec_driver_sql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'callout'"
        ).fetchall()
    }

    if "status" not in existing_cols:
        # Add as nullable first, backfill existing rows to COMPLETED, then
        # enforce NOT NULL. New inserts pick up the server_default.
        op.add_column(
            "callout",
            sa.Column(
                "status",
                postgresql.ENUM(
                    "PENDING", "RUNNING", "COMPLETED", "FAILED",
                    name="callout_status", create_type=False,
                ),
                nullable=True,
                server_default="PENDING",
            ),
        )
        bind.exec_driver_sql(
            "UPDATE callout SET status = 'COMPLETED' WHERE status IS NULL"
        )
        op.alter_column("callout", "status", nullable=False)

    if "completed_at" not in existing_cols:
        op.add_column(
            "callout",
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "error_message" not in existing_cols:
        op.add_column(
            "callout",
            sa.Column("error_message", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("callout", "error_message")
    op.drop_column("callout", "completed_at")
    op.drop_column("callout", "status")
    op.execute("DROP TYPE IF EXISTS callout_status")
