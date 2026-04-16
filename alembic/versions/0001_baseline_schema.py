"""baseline schema

Creates all tables from SQLAlchemy models. Acts as the initial migration
so fresh deploys (Railway, CI, etc.) have a working schema without
requiring a manual create_all step.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-16
"""
from __future__ import annotations

from alembic import op

from app.models import Base


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
