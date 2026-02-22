"""Add anomaly_alerts table

Revision ID: i08_anomaly_alerts
Revises: i07_organizations
Create Date: 2026-02-21 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "i08_anomaly_alerts"
down_revision = "i07_organizations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "anomaly_alerts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id", UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("z_score", sa.Float, nullable=False),
        sa.Column("details", JSONB, server_default="{}"),
        sa.Column("is_resolved", sa.Boolean, server_default="false"),
        sa.Column(
            "resolved_by", UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_anomaly_alerts_entity", "anomaly_alerts", ["entity_id"])
    op.create_index("ix_anomaly_alerts_type", "anomaly_alerts", ["alert_type"])
    op.create_index("ix_anomaly_alerts_resolved", "anomaly_alerts", ["is_resolved"])
    op.create_index("ix_anomaly_alerts_created", "anomaly_alerts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_anomaly_alerts_created", table_name="anomaly_alerts")
    op.drop_index("ix_anomaly_alerts_resolved", table_name="anomaly_alerts")
    op.drop_index("ix_anomaly_alerts_type", table_name="anomaly_alerts")
    op.drop_index("ix_anomaly_alerts_entity", table_name="anomaly_alerts")
    op.drop_table("anomaly_alerts")
