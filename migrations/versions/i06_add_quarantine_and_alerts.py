"""Add quarantine and propagation alerts

Revision ID: i06_quarantine_alerts
Revises: i05_collab_types
Create Date: 2026-02-21 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "i06_quarantine_alerts"
down_revision = "i05_collab_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_quarantined column to entities
    op.add_column(
        "entities",
        sa.Column("is_quarantined", sa.Boolean(), nullable=True, server_default="false"),
    )

    # Create propagation_alerts table
    op.create_table(
        "propagation_alerts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("alert_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "issued_by",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id"),
            nullable=True,
        ),
        sa.Column("is_resolved", sa.Boolean(), server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_propagation_alerts_type",
        "propagation_alerts",
        ["alert_type"],
    )
    op.create_index(
        "ix_propagation_alerts_resolved",
        "propagation_alerts",
        ["is_resolved"],
    )
    op.create_index(
        "ix_propagation_alerts_created",
        "propagation_alerts",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_propagation_alerts_created", table_name="propagation_alerts")
    op.drop_index("ix_propagation_alerts_resolved", table_name="propagation_alerts")
    op.drop_index("ix_propagation_alerts_type", table_name="propagation_alerts")
    op.drop_table("propagation_alerts")
    op.drop_column("entities", "is_quarantined")
