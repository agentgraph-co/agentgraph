"""Add search performance indexes: display_name trgm + composite indexes.

Adds a GIN trigram index on entities.display_name for fast ILIKE search,
and composite B-tree indexes on (is_active, source_type) and
(type, is_active, source_type) for the Moltbook filter pattern.

Note: entities.bio_markdown trgm index already exists in s11_search_trgm.

Revision ID: s14_search_perf
Revises: s13_csam_enum
Create Date: 2026-03-21
"""
from __future__ import annotations

from alembic import op

revision = "s14_search_perf"
down_revision = "s13_csam_enum"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pg_trgm extension is available (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # GIN trigram index on entities.display_name for fast ILIKE search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entities_display_name_trgm "
        "ON entities USING gin (display_name gin_trgm_ops)"
    )

    # Composite indexes for the Moltbook filter pattern
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entities_active_source_type "
        "ON entities (is_active, source_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entities_type_active_source "
        "ON entities (type, is_active, source_type)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_entities_type_active_source")
    op.execute("DROP INDEX IF EXISTS ix_entities_active_source_type")
    op.execute("DROP INDEX IF EXISTS ix_entities_display_name_trgm")
