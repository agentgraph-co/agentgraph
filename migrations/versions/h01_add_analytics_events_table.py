"""add analytics_events table for conversion funnel tracking

Revision ID: h01_analytics_events
Revises: g01_perf_indexes
Create Date: 2026-02-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'h01_analytics_events'
down_revision = 'g01_perf_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('analytics_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('event_type', sa.String(length=50), nullable=False),
    sa.Column('session_id', sa.String(length=64), nullable=False),
    sa.Column('page', sa.String(length=200), nullable=False),
    sa.Column('intent', sa.String(length=50), nullable=True),
    sa.Column('referrer', sa.String(length=500), nullable=True),
    sa.Column('entity_id', sa.UUID(), nullable=True),
    sa.Column('extra_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column(
        'created_at', sa.DateTime(timezone=True),
        server_default=sa.text('now()'), nullable=False,
    ),
    sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_analytics_event_type', 'analytics_events', ['event_type'], unique=False)
    op.create_index('ix_analytics_created_at', 'analytics_events', ['created_at'], unique=False)
    op.create_index('ix_analytics_session_id', 'analytics_events', ['session_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_analytics_session_id', table_name='analytics_events')
    op.drop_index('ix_analytics_created_at', table_name='analytics_events')
    op.drop_index('ix_analytics_event_type', table_name='analytics_events')
    op.drop_table('analytics_events')
