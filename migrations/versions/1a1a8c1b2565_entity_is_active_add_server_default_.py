"""entity is_active: add server_default true, set not null

Revision ID: 1a1a8c1b2565
Revises: s18_reply_guy
Create Date: 2026-03-27 16:54:33.097390
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = '1a1a8c1b2565'
down_revision = 's18_reply_guy'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fix any NULL is_active values first
    op.execute("UPDATE entities SET is_active = true WHERE is_active IS NULL")
    # Add server_default and set NOT NULL
    op.alter_column('entities', 'is_active',
               existing_type=sa.BOOLEAN(),
               server_default=sa.text('true'),
               nullable=False)


def downgrade() -> None:
    op.alter_column('entities', 'is_active',
               existing_type=sa.BOOLEAN(),
               server_default=None,
               nullable=True)
