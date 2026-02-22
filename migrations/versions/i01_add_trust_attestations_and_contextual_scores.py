"""add trust attestations and contextual scores

Revision ID: i01_trust_attestations
Revises: h01_analytics_events
Create Date: 2026-02-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'i01_trust_attestations'
down_revision = 'h01_analytics_events'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create trust_attestations table
    op.create_table(
        'trust_attestations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('attester_entity_id', sa.UUID(), nullable=False),
        sa.Column('target_entity_id', sa.UUID(), nullable=False),
        sa.Column('attestation_type', sa.String(length=20), nullable=False),
        sa.Column('context', sa.String(length=100), nullable=True),
        sa.Column('weight', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['attester_entity_id'], ['entities.id'], ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['target_entity_id'], ['entities.id'], ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'attester_entity_id', 'target_entity_id', 'attestation_type',
            name='uq_trust_attestation',
        ),
    )
    op.create_index(
        'ix_trust_attestations_target', 'trust_attestations',
        ['target_entity_id'],
    )
    op.create_index(
        'ix_trust_attestations_attester', 'trust_attestations',
        ['attester_entity_id'],
    )

    # Add contextual_scores column to trust_scores
    op.add_column(
        'trust_scores',
        sa.Column(
            'contextual_scores',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='{}',
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('trust_scores', 'contextual_scores')
    op.drop_index('ix_trust_attestations_attester', table_name='trust_attestations')
    op.drop_index('ix_trust_attestations_target', table_name='trust_attestations')
    op.drop_table('trust_attestations')
