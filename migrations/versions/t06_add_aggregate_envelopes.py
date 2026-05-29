"""Add aggregate_envelopes table for persisted Trust Score v2 envelopes.

Durable store behind the /aggregate surface (design §5.2): one row per subject
DID with the latest signed v2 envelope JSON, score, and freshness window.
Purely additive — creates one new table, touches no existing data.

Revision ID: t06
Revises: t05
Create Date: 2026-05-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "t06"
down_revision = "t05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aggregate_envelopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_did", sa.String(500), nullable=False),
        sa.Column("trust_score", sa.Float(), nullable=False),
        sa.Column("score_version", sa.String(10), nullable=False),
        sa.Column("envelope", postgresql.JSONB(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject_did", name="uq_aggregate_envelopes_subject_did"),
    )
    op.create_index(
        "ix_aggregate_envelopes_subject", "aggregate_envelopes", ["subject_did"],
    )
    op.create_index(
        "ix_aggregate_envelopes_expires", "aggregate_envelopes", ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_aggregate_envelopes_expires", table_name="aggregate_envelopes")
    op.drop_index("ix_aggregate_envelopes_subject", table_name="aggregate_envelopes")
    op.drop_table("aggregate_envelopes")
