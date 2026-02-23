"""Add performance indexes for search, feed, and lookup queries.

Revision ID: k01_performance_indexes
Revises: j04_org_usage_metering
Create Date: 2026-02-22 18:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "k01_performance_indexes"
down_revision = "j04_org_usage_metering"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pg_trgm extension for trigram-based ILIKE acceleration
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # GIN trigram indexes on listings for ILIKE search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_listings_title_trgm "
        "ON listings USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_listings_description_trgm "
        "ON listings USING gin (description gin_trgm_ops)"
    )

    # GIN tsvector index on posts.content for full-text search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_posts_content_fts "
        "ON posts USING gin (to_tsvector('english', content))"
    )

    # Partial index on posts.is_hidden (most feed queries filter by this)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_posts_not_hidden "
        "ON posts (created_at DESC) WHERE is_hidden = false"
    )

    # Index on entities.display_name for mention lookup
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entities_display_name "
        "ON entities USING gin (display_name gin_trgm_ops)"
    )

    # Index on votes.post_id for vote count aggregation
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_votes_post_id "
        "ON votes (post_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_votes_post_id")
    op.execute("DROP INDEX IF EXISTS ix_entities_display_name")
    op.execute("DROP INDEX IF EXISTS ix_posts_not_hidden")
    op.execute("DROP INDEX IF EXISTS ix_posts_content_fts")
    op.execute("DROP INDEX IF EXISTS ix_listings_description_trgm")
    op.execute("DROP INDEX IF EXISTS ix_listings_title_trgm")
