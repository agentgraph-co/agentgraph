"""Add GIN trigram indexes for ILIKE search on posts, entities bio, and did_web.

The search router falls back to ILIKE for short queries (<2 chars).
Existing trigram indexes cover entities.display_name and listings
but miss posts.content, entities.bio_markdown, and entities.did_web.
These GIN trigram indexes accelerate ILIKE patterns with pg_trgm.

Revision ID: s11_search_trgm
Revises: s10_marketing_system
Create Date: 2026-03-19 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "s11_search_trgm"
down_revision = "s10_marketing_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pg_trgm extension already enabled in k01_performance_indexes

    # GIN trigram index on posts.content for ILIKE fallback search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_posts_content_trgm "
        "ON posts USING gin (content gin_trgm_ops)"
    )

    # GIN trigram index on entities.bio_markdown for ILIKE fallback search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entities_bio_trgm "
        "ON entities USING gin (COALESCE(bio_markdown, '') gin_trgm_ops)"
    )

    # GIN trigram index on entities.did_web for ILIKE search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entities_did_web_trgm "
        "ON entities USING gin (did_web gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_entities_did_web_trgm")
    op.execute("DROP INDEX IF EXISTS ix_entities_bio_trgm")
    op.execute("DROP INDEX IF EXISTS ix_posts_content_trgm")
