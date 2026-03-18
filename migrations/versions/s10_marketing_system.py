"""Add marketing_campaigns and marketing_posts tables.

Revision ID: s10_marketing_system
Revises: s09_source_import
Create Date: 2026-03-17 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "s10_marketing_system"
down_revision = "s09_source_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Marketing campaigns
    op.create_table(
        "marketing_campaigns",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("topic", sa.String(100), nullable=False),
        sa.Column("platforms", ARRAY(sa.String(50)), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("schedule_config", JSONB, nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mktg_campaign_status", "marketing_campaigns", ["status"])
    op.create_index("ix_mktg_campaign_topic", "marketing_campaigns", ["topic"])

    # Marketing posts
    op.create_table(
        "marketing_posts",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", UUID(as_uuid=True), nullable=True),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("post_type", sa.String(20), nullable=False),
        sa.Column("topic", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("parent_external_id", sa.String(255), nullable=True),
        sa.Column("llm_model", sa.String(50), nullable=True),
        sa.Column("llm_tokens_in", sa.Integer(), nullable=True),
        sa.Column("llm_tokens_out", sa.Integer(), nullable=True),
        sa.Column("llm_cost_usd", sa.Float(), nullable=True),
        sa.Column("metrics_json", JSONB, nullable=True),
        sa.Column("utm_params", JSONB, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["marketing_campaigns.id"], ondelete="SET NULL",
        ),
        sa.UniqueConstraint("platform", "external_id", name="uq_mktg_platform_external"),
    )
    op.create_index("ix_mktg_post_platform", "marketing_posts", ["platform"])
    op.create_index("ix_mktg_post_status", "marketing_posts", ["status"])
    op.create_index("ix_mktg_post_type", "marketing_posts", ["post_type"])
    op.create_index("ix_mktg_post_topic", "marketing_posts", ["topic"])
    op.create_index("ix_mktg_post_content_hash", "marketing_posts", ["content_hash"])
    op.create_index("ix_mktg_post_posted_at", "marketing_posts", ["posted_at"])
    op.create_index("ix_mktg_post_campaign", "marketing_posts", ["campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_mktg_post_campaign", table_name="marketing_posts")
    op.drop_index("ix_mktg_post_posted_at", table_name="marketing_posts")
    op.drop_index("ix_mktg_post_content_hash", table_name="marketing_posts")
    op.drop_index("ix_mktg_post_topic", table_name="marketing_posts")
    op.drop_index("ix_mktg_post_type", table_name="marketing_posts")
    op.drop_index("ix_mktg_post_status", table_name="marketing_posts")
    op.drop_index("ix_mktg_post_platform", table_name="marketing_posts")
    op.drop_table("marketing_posts")

    op.drop_index("ix_mktg_campaign_topic", table_name="marketing_campaigns")
    op.drop_index("ix_mktg_campaign_status", table_name="marketing_campaigns")
    op.drop_table("marketing_campaigns")
