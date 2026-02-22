"""Add AIP protocol tables: delegations and agent_capability_registry

Revision ID: j03_aip_tables
Revises: i09_sso_config
Create Date: 2026-02-22 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "j03_aip_tables"
down_revision = "i09_sso_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- delegations table ---
    op.create_table(
        "delegations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "delegator_entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "delegate_entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_description", sa.Text(), nullable=False),
        sa.Column("constraints", JSONB, server_default="{}"),
        sa.Column(
            "status", sa.String(20), server_default="pending", nullable=False,
        ),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("correlation_id", sa.String(64), unique=True, nullable=False),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_delegations_delegator", "delegations", ["delegator_entity_id"])
    op.create_index("ix_delegations_delegate", "delegations", ["delegate_entity_id"])
    op.create_index("ix_delegations_status", "delegations", ["status"])
    op.create_index("ix_delegations_correlation", "delegations", ["correlation_id"])

    # --- agent_capability_registry table ---
    op.create_table(
        "agent_capability_registry",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("capability_name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(50), server_default="1.0.0"),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("input_schema", JSONB, server_default="{}"),
        sa.Column("output_schema", JSONB, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("entity_id", "capability_name", name="uq_entity_capability"),
    )
    op.create_index("ix_cap_registry_entity", "agent_capability_registry", ["entity_id"])
    op.create_index(
        "ix_cap_registry_name", "agent_capability_registry", ["capability_name"],
    )
    op.create_index(
        "ix_cap_registry_active", "agent_capability_registry", ["is_active"],
    )


def downgrade() -> None:
    op.drop_table("agent_capability_registry")
    op.drop_table("delegations")
