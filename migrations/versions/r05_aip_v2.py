"""Add aip_channels and aip_messages tables for AIP v2.

Revision ID: r05_aip_v2
Revises: r04_attestation_providers
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "r05_aip_v2"
down_revision = "r04_attestation_providers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- aip_channels ---
    op.create_table(
        "aip_channels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_by_entity_id", UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("participant_ids", JSONB, server_default="[]"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
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
        "ix_aip_channels_created_by", "aip_channels", ["created_by_entity_id"],
    )

    # --- aip_messages ---
    op.create_table(
        "aip_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sender_entity_id", UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "recipient_entity_id", UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "channel_id", UUID(as_uuid=True),
            sa.ForeignKey("aip_channels.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("message_type", sa.String(20), nullable=False),
        sa.Column("payload", JSONB, server_default="{}"),
        sa.Column("sender_trust_score", sa.Float, nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_aip_messages_sender", "aip_messages", ["sender_entity_id"],
    )
    op.create_index(
        "ix_aip_messages_recipient", "aip_messages", ["recipient_entity_id"],
    )
    op.create_index(
        "ix_aip_messages_channel", "aip_messages", ["channel_id"],
    )
    op.create_index(
        "ix_aip_messages_created_at", "aip_messages", ["created_at"],
    )


def downgrade() -> None:
    op.drop_table("aip_messages")
    op.drop_table("aip_channels")
