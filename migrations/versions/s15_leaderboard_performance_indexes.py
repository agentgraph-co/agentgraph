"""Add leaderboard performance indexes.

Adds indexes to support leaderboard queries after removing _not_moltbook filters:
- Descending trust score index for leaderboard sorting
- Drops Moltbook source_type partial indexes (no longer used)

Revision ID: s15_lb_perf
Revises: s14_search_perf
Create Date: 2026-03-21
"""
from __future__ import annotations

from alembic import op

revision = "s15_lb_perf"
down_revision = "s14_search_perf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Descending trust score index for leaderboard ORDER BY score DESC
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trust_scores_score_desc "
        "ON trust_scores (score DESC NULLS LAST)"
    )

    # Drop Moltbook-specific indexes that are no longer needed
    op.execute("DROP INDEX IF EXISTS ix_entities_not_moltbook")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trust_scores_score_desc")
