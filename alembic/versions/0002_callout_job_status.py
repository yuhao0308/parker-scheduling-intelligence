"""Add callout job status fields for resumable Finding Replacements flow.

Adds ``status``, ``completed_at``, and ``error_message`` columns to the
``callout`` table so the recommendation pipeline can run as a background
asyncio task and the frontend can resume by callout_id after navigating
away from the Callout page.

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

    # Query information_schema directly; the inspector can lag inside an
    # Alembic transaction (mirrors the pattern in 0001).
    existing_cols = {
        row[0]
        for row in bind.exec_driver_sql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'callout'"
        ).fetchall()
    }

    if "status" not in existing_cols:
        bind.exec_driver_sql(
            "DO $$ BEGIN "
            "CREATE TYPE callout_status AS ENUM "
            "('PENDING', 'RUNNING', 'COMPLETED', 'FAILED'); "
            "EXCEPTION WHEN duplicate_object THEN null; END $$"
        )
        op.add_column(
            "callout",
            sa.Column(
                "status",
                postgresql.ENUM(
                    "PENDING", "RUNNING", "COMPLETED", "FAILED",
                    name="callout_status",
                    create_type=False,
                ),
                nullable=False,
                server_default="PENDING",
            ),
        )
        # Existing rows pre-date the job model; treat them as completed so
        # they don't show up as stuck-running in the UI.
        bind.exec_driver_sql("UPDATE callout SET status = 'COMPLETED'")

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
