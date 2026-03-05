"""Add formal_attestations table for verification badge framework

Revision ID: r03_formal_attestations
Revises: r02_content_links
Create Date: 2026-03-04 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r03_formal_attestations"
down_revision = "r02_content_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "formal_attestations",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "issuer_entity_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subject_entity_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attestation_type", sa.String(50), nullable=False),
        sa.Column("evidence", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_revoked", sa.Boolean, default=False, nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "issuer_entity_id", "subject_entity_id", "attestation_type",
            name="uq_formal_attestation",
        ),
    )

    op.create_index("ix_formal_attestations_issuer", "formal_attestations", ["issuer_entity_id"])
    op.create_index("ix_formal_attestations_subject", "formal_attestations", ["subject_entity_id"])
    op.create_index("ix_formal_attestations_type", "formal_attestations", ["attestation_type"])
    op.create_index("ix_formal_attestations_revoked", "formal_attestations", ["is_revoked"])


def downgrade() -> None:
    op.drop_index("ix_formal_attestations_revoked")
    op.drop_index("ix_formal_attestations_type")
    op.drop_index("ix_formal_attestations_subject")
    op.drop_index("ix_formal_attestations_issuer")
    op.drop_table("formal_attestations")
