"""Widen avatar_url to 2000 chars.

Google profile photo URLs can exceed 500 characters.

Revision ID: t02_avatar_url
Revises: t01_api_health
Create Date: 2026-03-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "t02_avatar_url"
down_revision = "t01_api_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "entities",
        "avatar_url",
        type_=sa.String(2000),
        existing_type=sa.String(500),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "entities",
        "avatar_url",
        type_=sa.String(500),
        existing_type=sa.String(2000),
        existing_nullable=True,
    )
