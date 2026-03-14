"""Add linked_accounts table for external reputation aggregation.

Revision ID: s08_linked_accounts
Revises: s07_per_kind_email_prefs
Create Date: 2026-03-14 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "s08_linked_accounts"
down_revision = "s07_per_kind_email_prefs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "linked_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id", UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("provider_username", sa.String(255), nullable=True),
        sa.Column(
            "verification_status", sa.String(30),
            nullable=False, server_default="pending",
        ),
        sa.Column("access_token", sa.String(500), nullable=True),
        sa.Column("refresh_token", sa.String(500), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("profile_data", JSONB, server_default="{}"),
        sa.Column("reputation_data", JSONB, server_default="{}"),
        sa.Column("reputation_score", sa.Float, server_default="0.0"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("entity_id", "provider", name="uq_linked_account_provider"),
    )
    op.create_index("ix_linked_accounts_entity", "linked_accounts", ["entity_id"])
    op.create_index("ix_linked_accounts_provider", "linked_accounts", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_linked_accounts_provider", table_name="linked_accounts")
    op.drop_index("ix_linked_accounts_entity", table_name="linked_accounts")
    op.drop_table("linked_accounts")
