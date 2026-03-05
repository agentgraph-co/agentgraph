"""Add reporter_trust_score to moderation_flags

Revision ID: q01_trust_weighted_flag
Revises: p01_provisional_reg
Create Date: 2026-03-05 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "q01_trust_weighted_flag"
down_revision = "p01_provisional_reg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "moderation_flags",
        sa.Column("reporter_trust_score", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("moderation_flags", "reporter_trust_score")
