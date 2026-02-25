"""add missing ondelete to 11 foreign keys

Revision ID: a5d0f69a8cae
Revises: k02_audit_indexes
Create Date: 2026-02-24 19:40:15.579481
"""
from __future__ import annotations

from alembic import op


revision = 'a5d0f69a8cae'
down_revision = 'k02_audit_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Entity.operator_id -> SET NULL
    op.drop_constraint('entities_operator_id_fkey', 'entities', type_='foreignkey')
    op.create_foreign_key(
        'entities_operator_id_fkey', 'entities', 'entities',
        ['operator_id'], ['id'], ondelete='SET NULL',
    )

    # ModerationFlag.resolved_by -> SET NULL
    op.drop_constraint('moderation_flags_resolved_by_fkey', 'moderation_flags', type_='foreignkey')
    op.create_foreign_key(
        'moderation_flags_resolved_by_fkey', 'moderation_flags', 'entities',
        ['resolved_by'], ['id'], ondelete='SET NULL',
    )

    # EvolutionRecord.parent_record_id -> SET NULL
    op.drop_constraint(
        'evolution_records_parent_record_id_fkey', 'evolution_records', type_='foreignkey',
    )
    op.create_foreign_key(
        'evolution_records_parent_record_id_fkey', 'evolution_records', 'evolution_records',
        ['parent_record_id'], ['id'], ondelete='SET NULL',
    )

    # EvolutionRecord.forked_from_entity_id -> SET NULL
    op.drop_constraint(
        'evolution_records_forked_from_entity_id_fkey', 'evolution_records', type_='foreignkey',
    )
    op.create_foreign_key(
        'evolution_records_forked_from_entity_id_fkey', 'evolution_records', 'entities',
        ['forked_from_entity_id'], ['id'], ondelete='SET NULL',
    )

    # EvolutionRecord.approved_by -> SET NULL
    op.drop_constraint(
        'evolution_records_approved_by_fkey', 'evolution_records', type_='foreignkey',
    )
    op.create_foreign_key(
        'evolution_records_approved_by_fkey', 'evolution_records', 'entities',
        ['approved_by'], ['id'], ondelete='SET NULL',
    )

    # Dispute.transaction_id -> CASCADE
    op.drop_constraint('disputes_transaction_id_fkey', 'disputes', type_='foreignkey')
    op.create_foreign_key(
        'disputes_transaction_id_fkey', 'disputes', 'transactions',
        ['transaction_id'], ['id'], ondelete='CASCADE',
    )

    # Dispute.opened_by -> CASCADE
    op.drop_constraint('disputes_opened_by_fkey', 'disputes', type_='foreignkey')
    op.create_foreign_key(
        'disputes_opened_by_fkey', 'disputes', 'entities',
        ['opened_by'], ['id'], ondelete='CASCADE',
    )

    # Dispute.resolved_by -> SET NULL
    op.drop_constraint('disputes_resolved_by_fkey', 'disputes', type_='foreignkey')
    op.create_foreign_key(
        'disputes_resolved_by_fkey', 'disputes', 'entities',
        ['resolved_by'], ['id'], ondelete='SET NULL',
    )

    # ModerationAppeal.resolved_by -> SET NULL
    op.drop_constraint(
        'moderation_appeals_resolved_by_fkey', 'moderation_appeals', type_='foreignkey',
    )
    op.create_foreign_key(
        'moderation_appeals_resolved_by_fkey', 'moderation_appeals', 'entities',
        ['resolved_by'], ['id'], ondelete='SET NULL',
    )

    # PropagationAlert.issued_by -> SET NULL
    op.drop_constraint(
        'propagation_alerts_issued_by_fkey', 'propagation_alerts', type_='foreignkey',
    )
    op.create_foreign_key(
        'propagation_alerts_issued_by_fkey', 'propagation_alerts', 'entities',
        ['issued_by'], ['id'], ondelete='SET NULL',
    )

    # Organization.created_by -> RESTRICT
    op.drop_constraint('organizations_created_by_fkey', 'organizations', type_='foreignkey')
    op.create_foreign_key(
        'organizations_created_by_fkey', 'organizations', 'entities',
        ['created_by'], ['id'], ondelete='RESTRICT',
    )


def downgrade() -> None:
    # Revert all to no ondelete (database default: NO ACTION)
    for table, fk_name, ref_table, local_cols, remote_cols in [
        ('organizations', 'organizations_created_by_fkey', 'entities', ['created_by'], ['id']),
        ('propagation_alerts', 'propagation_alerts_issued_by_fkey', 'entities', ['issued_by'], ['id']),
        ('moderation_appeals', 'moderation_appeals_resolved_by_fkey', 'entities', ['resolved_by'], ['id']),
        ('disputes', 'disputes_resolved_by_fkey', 'entities', ['resolved_by'], ['id']),
        ('disputes', 'disputes_opened_by_fkey', 'entities', ['opened_by'], ['id']),
        ('disputes', 'disputes_transaction_id_fkey', 'transactions', ['transaction_id'], ['id']),
        ('evolution_records', 'evolution_records_approved_by_fkey', 'entities', ['approved_by'], ['id']),
        ('evolution_records', 'evolution_records_forked_from_entity_id_fkey', 'entities', ['forked_from_entity_id'], ['id']),
        ('evolution_records', 'evolution_records_parent_record_id_fkey', 'evolution_records', ['parent_record_id'], ['id']),
        ('moderation_flags', 'moderation_flags_resolved_by_fkey', 'entities', ['resolved_by'], ['id']),
        ('entities', 'entities_operator_id_fkey', 'entities', ['operator_id'], ['id']),
    ]:
        op.drop_constraint(fk_name, table, type_='foreignkey')
        op.create_foreign_key(fk_name, table, ref_table, local_cols, remote_cols)
