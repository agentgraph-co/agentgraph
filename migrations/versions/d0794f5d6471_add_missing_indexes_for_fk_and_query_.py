"""add missing indexes for FK and query columns

Revision ID: d0794f5d6471
Revises: a5d0f69a8cae
Create Date: 2026-02-24 20:04:37.294076
"""
from __future__ import annotations

from alembic import op


revision = 'd0794f5d6471'
down_revision = 'a5d0f69a8cae'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('ix_api_keys_entity_id', 'api_keys', ['entity_id'])
    op.create_index('ix_entities_is_active', 'entities', ['is_active'])
    op.create_index('ix_entities_organization_id', 'entities', ['organization_id'])
    op.create_index('ix_evolution_approval_status', 'evolution_records', ['approval_status'])
    op.create_index('ix_evolution_parent', 'evolution_records', ['parent_record_id'])
    op.create_index('ix_moderation_reporter', 'moderation_flags', ['reporter_entity_id'])
    op.create_index('ix_post_edits_edited_by', 'post_edits', ['edited_by'])


def downgrade() -> None:
    op.drop_index('ix_post_edits_edited_by', table_name='post_edits')
    op.drop_index('ix_moderation_reporter', table_name='moderation_flags')
    op.drop_index('ix_evolution_parent', table_name='evolution_records')
    op.drop_index('ix_evolution_approval_status', table_name='evolution_records')
    op.drop_index('ix_entities_organization_id', table_name='entities')
    op.drop_index('ix_entities_is_active', table_name='entities')
    op.drop_index('ix_api_keys_entity_id', table_name='api_keys')
