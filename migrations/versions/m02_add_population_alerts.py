"""Add population_alerts table for composition monitoring.

Revision ID: m02_add_population_alerts
Revises: m01_add_entity_primary_context
Create Date: 2026-03-03 14:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m02_add_population_alerts"
down_revision = "m01_add_entity_primary_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "population_alerts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index("ix_population_alerts_type", "population_alerts", ["alert_type"])
    op.create_index("ix_population_alerts_resolved", "population_alerts", ["is_resolved"])
    op.create_index("ix_population_alerts_created", "population_alerts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_population_alerts_created", table_name="population_alerts")
    op.drop_index("ix_population_alerts_resolved", table_name="population_alerts")
    op.drop_index("ix_population_alerts_type", table_name="population_alerts")
    op.drop_table("population_alerts")
