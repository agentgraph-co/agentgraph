"""Add media_url and media_type columns to posts.

Revision ID: r06_post_media
Revises: r05_aip_v2
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r06_post_media"
down_revision = "r05_aip_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("media_url", sa.String(1000), nullable=True))
    op.add_column("posts", sa.Column("media_type", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "media_type")
    op.drop_column("posts", "media_url")
