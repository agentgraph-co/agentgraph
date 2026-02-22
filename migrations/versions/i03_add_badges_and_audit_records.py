"""add_badges_and_audit_records

Revision ID: i03_badges_audit
Revises: i02_stripe
Create Date: 2026-02-21 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "i03_badges_audit"
down_revision = "i02_stripe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create verification_badges table
    op.create_table(
        "verification_badges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id", UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("badge_type", sa.String(length=50), nullable=False),
        sa.Column(
            "issued_by", UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("proof_url", sa.String(length=1000), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_verification_badges_entity",
        "verification_badges", ["entity_id"],
    )
    op.create_index(
        "ix_verification_badges_type",
        "verification_badges", ["badge_type"],
    )
    op.create_index(
        "ix_verification_badges_active",
        "verification_badges", ["is_active"],
    )

    # Create audit_records table
    op.create_table(
        "audit_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "target_entity_id", UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "auditor_entity_id", UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("audit_type", sa.String(length=30), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("findings", JSONB, nullable=True),
        sa.Column("report_url", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_audit_records_target",
        "audit_records", ["target_entity_id"],
    )
    op.create_index(
        "ix_audit_records_auditor",
        "audit_records", ["auditor_entity_id"],
    )
    op.create_index(
        "ix_audit_records_type",
        "audit_records", ["audit_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_records_type", table_name="audit_records")
    op.drop_index("ix_audit_records_auditor", table_name="audit_records")
    op.drop_index("ix_audit_records_target", table_name="audit_records")
    op.drop_table("audit_records")

    op.drop_index("ix_verification_badges_active", table_name="verification_badges")
    op.drop_index("ix_verification_badges_type", table_name="verification_badges")
    op.drop_index("ix_verification_badges_entity", table_name="verification_badges")
    op.drop_table("verification_badges")
