"""Add trust_score_history table for tracking score changes over time.

Revision ID: r07_trust_history
Revises: r06_post_media
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "r07_trust_history"
down_revision = "r06_post_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trust_score_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("components", JSONB, server_default="{}"),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_trust_score_history_entity_time",
        "trust_score_history",
        ["entity_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trust_score_history_entity_time",
        table_name="trust_score_history",
    )
    op.drop_table("trust_score_history")
