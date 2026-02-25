"""add missing indexes and updated_at columns

Revision ID: 430d35e8855c
Revises: d0794f5d6471
Create Date: 2026-02-25 12:05:17.272654
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '430d35e8855c'
down_revision = 'd0794f5d6471'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New indexes on FK columns queried without indexes
    op.create_index('ix_disputes_resolved_by', 'disputes', ['resolved_by'], unique=False)
    op.create_index('ix_token_blacklist_entity', 'token_blacklist', ['entity_id'], unique=False)
    op.create_index('ix_appeal_appellant', 'moderation_appeals', ['appellant_id'], unique=False)

    # Add updated_at to mutable models that were missing it
    op.add_column('disputes', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('delegations', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('notifications', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    op.drop_column('notifications', 'updated_at')
    op.drop_column('delegations', 'updated_at')
    op.drop_column('disputes', 'updated_at')
    op.drop_index('ix_appeal_appellant', table_name='moderation_appeals')
    op.drop_index('ix_token_blacklist_entity', table_name='token_blacklist')
    op.drop_index('ix_disputes_resolved_by', table_name='disputes')
