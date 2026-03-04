"""Add indexes for agent discovery endpoint

Revision ID: o02_agent_discovery_idx
Revises: o01_agent_heartbeat
Create Date: 2026-03-04 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "o02_agent_discovery_idx"
down_revision = "o01_agent_heartbeat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_entities_framework_source",
        "entities",
        ["framework_source"],
        unique=False,
    )
    op.create_index(
        "ix_entities_type_active",
        "entities",
        ["type", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_entities_type_active", table_name="entities")
    op.drop_index("ix_entities_framework_source", table_name="entities")
