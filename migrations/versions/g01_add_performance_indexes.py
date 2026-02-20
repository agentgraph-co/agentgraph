"""Add performance indexes for feed ranking, marketplace, and vote lookups.

Revision ID: g01_perf_indexes
Revises: fa1d509a30ad
Create Date: 2026-02-19
"""
from __future__ import annotations

from alembic import op

revision = "g01_perf_indexes"
down_revision = "a1de85e1c25b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_posts_vote_count", "posts", ["vote_count"])
    op.create_index("ix_votes_entity_post", "votes", ["entity_id", "post_id"])
    op.create_index("ix_listings_view_count", "listings", ["view_count"])


def downgrade() -> None:
    op.drop_index("ix_listings_view_count", table_name="listings")
    op.drop_index("ix_votes_entity_post", table_name="votes")
    op.drop_index("ix_posts_vote_count", table_name="posts")
