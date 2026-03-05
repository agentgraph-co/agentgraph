"""Add attestation_providers table.

Revision ID: r04
Revises: r03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "r04"
down_revision = "r03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attestation_providers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "operator_entity_id", UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("provider_name", sa.String(200), nullable=False, unique=True),
        sa.Column("provider_url", sa.String(500), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("supported_types", JSONB, server_default="[]"),
        sa.Column("api_key_hash", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("attestation_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_attestation_providers_operator",
        "attestation_providers", ["operator_entity_id"],
    )
    op.create_index(
        "ix_attestation_providers_active",
        "attestation_providers", ["is_active"],
    )


def downgrade() -> None:
    op.drop_table("attestation_providers")
