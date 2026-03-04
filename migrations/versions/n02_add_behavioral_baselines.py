"""Add behavioral_baselines table for temporal baseline metrics.

Revision ID: n02_add_behavioral_baselines
Revises: n01_deleg_and_contracts
Create Date: 2026-03-03 18:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "n02_add_behavioral_baselines"
down_revision = "n01_deleg_and_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "behavioral_baselines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("metrics", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_behavioral_baselines_entity",
        "behavioral_baselines",
        ["entity_id"],
    )
    op.create_index(
        "ix_behavioral_baselines_period",
        "behavioral_baselines",
        ["period_start", "period_end"],
    )


def downgrade() -> None:
    op.drop_index("ix_behavioral_baselines_period", table_name="behavioral_baselines")
    op.drop_index("ix_behavioral_baselines_entity", table_name="behavioral_baselines")
    op.drop_table("behavioral_baselines")
