"""Add api_health_checks table for API uptime monitoring.

Revision ID: t01_api_health
Revises: 1a1a8c1b2565
Create Date: 2026-03-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = 't01_api_health'
down_revision = '1a1a8c1b2565'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'api_health_checks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_id', UUID(as_uuid=True),
                   sa.ForeignKey('entities.id', ondelete='CASCADE'),
                   nullable=False),
        sa.Column('endpoint_url', sa.String(1000), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_status', sa.Integer(), nullable=True),
        sa.Column('last_response_ms', sa.Integer(), nullable=True),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('uptime_pct_30d', sa.Float(), default=0.0),
        sa.Column('total_checks', sa.Integer(), default=0),
        sa.Column('successful_checks', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(timezone=True),
                   server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                   server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_api_health_checks_entity', 'api_health_checks', ['entity_id'])
    op.create_index('ix_api_health_checks_active', 'api_health_checks', ['is_active'])


def downgrade() -> None:
    op.drop_index('ix_api_health_checks_active', table_name='api_health_checks')
    op.drop_index('ix_api_health_checks_entity', table_name='api_health_checks')
    op.drop_table('api_health_checks')
