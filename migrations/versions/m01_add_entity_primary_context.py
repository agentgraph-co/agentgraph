"""Add primary_context column to entities table.

Revision ID: m01_add_entity_primary_context
Revises: l01_add_interaction_events
Create Date: 2026-03-03 18:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "m01_add_entity_primary_context"
down_revision = "l01_add_interaction_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entities",
        sa.Column("primary_context", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entities", "primary_context")
