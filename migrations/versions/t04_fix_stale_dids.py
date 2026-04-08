"""Fix stale DIDs: replace agentgraph.io with agentgraph.co

Revision ID: t04
Revises: t03
Create Date: 2026-04-08
"""
from __future__ import annotations

from alembic import op

revision = "t04"
down_revision = "t03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE entities SET did_web = REPLACE(did_web, 'agentgraph.io', 'agentgraph.co') "
        "WHERE did_web LIKE '%agentgraph.io%'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE entities SET did_web = REPLACE(did_web, 'agentgraph.co', 'agentgraph.io') "
        "WHERE did_web LIKE '%agentgraph.co%'"
    )
