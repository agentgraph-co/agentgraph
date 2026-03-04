"""Add last_seen_at and agent_status columns to entities for agent heartbeat.

Revision ID: o01_agent_heartbeat
Revises: n02_add_behavioral_baselines
Create Date: 2026-03-04 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "o01_agent_heartbeat"
down_revision = "n02_add_behavioral_baselines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entities",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "entities",
        sa.Column("agent_status", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entities", "agent_status")
    op.drop_column("entities", "last_seen_at")
