"""Add interaction_events table for unified pairwise interaction history.

Revision ID: l01_add_interaction_events
Revises: k02_audit_indexes
Create Date: 2026-03-03 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "l01_add_interaction_events"
down_revision = "k02_audit_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interaction_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_a_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_b_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("interaction_type", sa.String(50), nullable=False),
        sa.Column("context", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Individual column indexes
    op.create_index("ix_interaction_entity_a", "interaction_events", ["entity_a_id"])
    op.create_index("ix_interaction_entity_b", "interaction_events", ["entity_b_id"])
    op.create_index("ix_interaction_type", "interaction_events", ["interaction_type"])
    op.create_index("ix_interaction_created_at", "interaction_events", ["created_at"])

    # Composite pairwise index for efficient lookups
    op.create_index(
        "ix_interaction_pairwise",
        "interaction_events",
        ["entity_a_id", "entity_b_id", "interaction_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_interaction_pairwise", table_name="interaction_events")
    op.drop_index("ix_interaction_created_at", table_name="interaction_events")
    op.drop_index("ix_interaction_type", table_name="interaction_events")
    op.drop_index("ix_interaction_entity_b", table_name="interaction_events")
    op.drop_index("ix_interaction_entity_a", table_name="interaction_events")
    op.drop_table("interaction_events")
