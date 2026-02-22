"""Add organizations and memberships

Revision ID: i07_organizations
Revises: i06_quarantine_alerts
Create Date: 2026-02-21 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "i07_organizations"
down_revision = "i06_quarantine_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create organizations table
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("settings", JSONB, server_default="{}"),
        sa.Column("tier", sa.String(20), server_default="free", nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column(
            "created_by", UUID(as_uuid=True),
            sa.ForeignKey("entities.id"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_organizations_name", "organizations", ["name"], unique=True)
    op.create_index("ix_organizations_active", "organizations", ["is_active"])
    op.create_index("ix_organizations_tier", "organizations", ["tier"])

    # Create organization_memberships table
    op.create_table(
        "organization_memberships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id", UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "entity_id", UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("OWNER", "ADMIN", "MEMBER", name="orgrole", create_type=True),
            nullable=False,
        ),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("organization_id", "entity_id", name="uq_org_membership"),
    )
    op.create_index("ix_org_memberships_org", "organization_memberships", ["organization_id"])
    op.create_index("ix_org_memberships_entity", "organization_memberships", ["entity_id"])

    # Add organization_id FK to entities
    op.add_column(
        "entities",
        sa.Column(
            "organization_id", UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("entities", "organization_id")
    op.drop_index("ix_org_memberships_entity", table_name="organization_memberships")
    op.drop_index("ix_org_memberships_org", table_name="organization_memberships")
    op.drop_table("organization_memberships")
    op.drop_index("ix_organizations_tier", table_name="organizations")
    op.drop_index("ix_organizations_active", table_name="organizations")
    op.drop_index("ix_organizations_name", table_name="organizations")
    op.drop_table("organizations")
    sa.Enum("OWNER", "ADMIN", "MEMBER", name="orgrole").drop(op.get_bind(), checkfirst=True)
