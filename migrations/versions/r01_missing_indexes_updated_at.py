"""Add missing indexes and updated_at to mutable models

Revision ID: r01_indexes_updated_at
Revises: q01_trust_weighted_flag
Create Date: 2026-03-05 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r01_indexes_updated_at"
down_revision = "q01_trust_weighted_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add updated_at to moderation_flags
    op.add_column(
        "moderation_flags",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Add updated_at to evolution_records
    op.add_column(
        "evolution_records",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Performance indexes
    op.create_index("ix_moderation_created_at", "moderation_flags", ["created_at"])
    op.create_index("ix_evolution_created_at", "evolution_records", ["created_at"])
    op.create_index("ix_evolution_change_type", "evolution_records", ["change_type"])
    op.create_index("ix_posts_hidden", "posts", ["is_hidden"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_created_at")
    op.drop_index("ix_posts_hidden")
    op.drop_index("ix_evolution_change_type")
    op.drop_index("ix_evolution_created_at")
    op.drop_index("ix_moderation_created_at")
    op.drop_column("evolution_records", "updated_at")
    op.drop_column("moderation_flags", "updated_at")
