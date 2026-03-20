"""Add GIN trigram indexes for submolt ILIKE search columns.

The search router uses ILIKE on submolts.display_name, submolts.name,
and submolts.description for short-query fallback. At 700K+ rows these
cause sequential scans. GIN trigram indexes via pg_trgm fix this.

Prior migrations already cover entities (display_name, bio_markdown,
did_web), posts (content), and listings (title, description).

Revision ID: s12_search_trgm
Revises: s11_search_trgm
Create Date: 2026-03-20 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "s12_search_trgm"
down_revision = "s11_search_trgm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pg_trgm extension already enabled in k01_performance_indexes

    # GIN trigram index on submolts.display_name for ILIKE search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trgm_submolts_display_name "
        "ON submolts USING gin (COALESCE(display_name, '') gin_trgm_ops)"
    )

    # GIN trigram index on submolts.name for ILIKE search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trgm_submolts_name "
        "ON submolts USING gin (name gin_trgm_ops)"
    )

    # GIN trigram index on submolts.description for ILIKE search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trgm_submolts_description "
        "ON submolts USING gin (COALESCE(description, '') gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trgm_submolts_description")
    op.execute("DROP INDEX IF EXISTS ix_trgm_submolts_name")
    op.execute("DROP INDEX IF EXISTS ix_trgm_submolts_display_name")
