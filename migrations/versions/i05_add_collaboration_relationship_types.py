"""Add COLLABORATION and SERVICE relationship types

Revision ID: i05_collab_types
Revises: i04_framework_scans
Create Date: 2026-02-21
"""
from __future__ import annotations

from alembic import op

revision = 'i05_collab_types'
down_revision = 'i04_framework_scans'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE relationshiptype ADD VALUE IF NOT EXISTS 'COLLABORATION'")
    op.execute("ALTER TYPE relationshiptype ADD VALUE IF NOT EXISTS 'SERVICE'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values directly.
    # A full enum migration would be needed for a real rollback.
    pass
