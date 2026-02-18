"""add_moderation_appeals_and_message_enabled

Revision ID: 16779b10b997
Revises: 4377b195a944
Create Date: 2026-02-18 08:21:12.428842
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '16779b10b997'
down_revision = '4377b195a944'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create moderation_appeals table
    op.create_table('moderation_appeals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('flag_id', sa.UUID(), nullable=False),
        sa.Column('appellant_id', sa.UUID(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('resolved_by', sa.UUID(), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['flag_id'], ['moderation_flags.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['appellant_id'], ['entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resolved_by'], ['entities.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_appeal_flag', 'moderation_appeals', ['flag_id'], unique=False)
    op.create_index('ix_appeal_status', 'moderation_appeals', ['status'], unique=False)

    # Add message_enabled column to notification_preferences
    op.add_column('notification_preferences',
        sa.Column('message_enabled', sa.Boolean(), nullable=True, server_default=sa.text('true'))
    )


def downgrade() -> None:
    op.drop_column('notification_preferences', 'message_enabled')
    op.drop_index('ix_appeal_status', table_name='moderation_appeals')
    op.drop_index('ix_appeal_flag', table_name='moderation_appeals')
    op.drop_table('moderation_appeals')
