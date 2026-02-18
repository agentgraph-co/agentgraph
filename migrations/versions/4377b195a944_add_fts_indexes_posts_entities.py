"""add_fts_indexes_posts_entities

Revision ID: 4377b195a944
Revises: a45ccf0effe6
Create Date: 2026-02-17 22:12:13.097122
"""
from __future__ import annotations

from alembic import op

revision = '4377b195a944'
down_revision = 'a45ccf0effe6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # GIN index on posts.content for full-text search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_posts_content_fts "
        "ON posts USING GIN (to_tsvector('english', content))"
    )
    # GIN index on entities.bio_markdown for full-text search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entities_bio_fts "
        "ON entities USING GIN (to_tsvector('english', COALESCE(bio_markdown, '')))"
    )
    # GIN index on entities.display_name for full-text search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entities_display_name_fts "
        "ON entities USING GIN (to_tsvector('english', display_name))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_posts_content_fts")
    op.execute("DROP INDEX IF EXISTS ix_entities_bio_fts")
    op.execute("DROP INDEX IF EXISTS ix_entities_display_name_fts")
