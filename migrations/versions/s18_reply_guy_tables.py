"""Add reply_targets and reply_opportunities tables for reply guy system."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "s18_reply_guy"
down_revision = "s17_topic"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reply_targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("handle", sa.String(200), nullable=False),
        sa.Column("display_name", sa.String(300)),
        sa.Column("follower_count", sa.Integer, default=0),
        sa.Column("priority_tier", sa.Integer, default=2),
        sa.Column("topics", postgresql.JSONB, default=list),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "platform", "handle", name="uq_reply_target_platform_handle",
        ),
    )
    op.create_index(
        "ix_reply_target_active_tier",
        "reply_targets",
        ["is_active", "priority_tier"],
    )

    op.create_table(
        "reply_opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "target_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reply_targets.id"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("post_uri", sa.String(500), nullable=False),
        sa.Column("post_content", sa.Text),
        sa.Column("post_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(50), default="new", nullable=False),
        sa.Column("draft_content", sa.Text),
        sa.Column("drafted_at", sa.DateTime(timezone=True)),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("reply_url", sa.String(500)),
        sa.Column("urgency_score", sa.Float, default=0.0),
        sa.Column("engagement_count", sa.Integer, default=0),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "platform", "post_uri", name="uq_reply_opportunity_post",
        ),
    )
    op.create_index(
        "ix_reply_opp_status_urgency",
        "reply_opportunities",
        ["status", "urgency_score"],
    )
    op.create_index(
        "ix_reply_opp_target",
        "reply_opportunities",
        ["target_id", "post_timestamp"],
    )


def downgrade() -> None:
    op.drop_table("reply_opportunities")
    op.drop_table("reply_targets")
