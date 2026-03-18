"""Marketing system database models."""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.database import Base


class MarketingCampaign(Base):
    """A marketing campaign groups related posts across platforms."""

    __tablename__ = "marketing_campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    topic = Column(String(100), nullable=False)
    platforms = Column(ARRAY(String(50)), nullable=False, server_default="{}")
    status = Column(String(20), nullable=False, server_default="draft")
    schedule_config = Column(JSONB, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    posts = relationship("MarketingPost", back_populates="campaign")

    __table_args__ = (
        Index("ix_mktg_campaign_status", "status"),
        Index("ix_mktg_campaign_topic", "topic"),
    )


class MarketingPost(Base):
    """An individual marketing post to an external platform."""

    __tablename__ = "marketing_posts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(
        UUID(as_uuid=True), ForeignKey("marketing_campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )
    platform = Column(String(50), nullable=False)
    external_id = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    post_type = Column(String(20), nullable=False)
    topic = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, server_default="draft")
    parent_external_id = Column(String(255), nullable=True)

    # LLM tracking
    llm_model = Column(String(50), nullable=True)
    llm_tokens_in = Column(Integer, nullable=True)
    llm_tokens_out = Column(Integer, nullable=True)
    llm_cost_usd = Column(Float, nullable=True)

    # Engagement metrics (refreshed periodically)
    metrics_json = Column(JSONB, nullable=True)

    # UTM attribution
    utm_params = Column(JSONB, nullable=True)

    # Error handling
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, server_default="0")

    # Timestamps
    posted_at = Column(DateTime(timezone=True), nullable=True)
    metrics_updated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    campaign = relationship("MarketingCampaign", back_populates="posts")

    __table_args__ = (
        UniqueConstraint("platform", "external_id", name="uq_mktg_platform_external"),
        Index("ix_mktg_post_platform", "platform"),
        Index("ix_mktg_post_status", "status"),
        Index("ix_mktg_post_type", "post_type"),
        Index("ix_mktg_post_topic", "topic"),
        Index("ix_mktg_post_content_hash", "content_hash"),
        Index("ix_mktg_post_posted_at", "posted_at"),
        Index("ix_mktg_post_campaign", "campaign_id"),
    )
