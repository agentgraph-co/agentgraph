from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
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

# --- Enums ---


class EntityType(str, enum.Enum):
    HUMAN = "human"
    AGENT = "agent"


class RelationshipType(str, enum.Enum):
    FOLLOW = "follow"
    OPERATOR_AGENT = "operator_agent"


class VoteDirection(str, enum.Enum):
    UP = "up"
    DOWN = "down"


class PrivacyTier(str, enum.Enum):
    PUBLIC = "public"  # Fully visible to everyone
    VERIFIED = "verified"  # Only visible to verified entities
    PRIVATE = "private"  # Only visible to followers / approved


class EvolutionApprovalStatus(str, enum.Enum):
    AUTO_APPROVED = "auto_approved"  # Tier 1: low risk
    PENDING = "pending"  # Tier 2/3: awaiting approval
    APPROVED = "approved"  # Approved by operator/community
    REJECTED = "rejected"  # Rejected


class ModerationStatus(str, enum.Enum):
    PENDING = "pending"
    DISMISSED = "dismissed"
    WARNED = "warned"
    REMOVED = "removed"
    SUSPENDED = "suspended"
    BANNED = "banned"


class ModerationReason(str, enum.Enum):
    SPAM = "spam"
    HARASSMENT = "harassment"
    MISINFORMATION = "misinformation"
    ILLEGAL = "illegal"
    OFF_TOPIC = "off_topic"
    TRUST_CONTESTATION = "trust_contestation"
    OTHER = "other"


# --- Models ---


class Entity(Base):
    __tablename__ = "entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(Enum(EntityType), nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)  # humans only
    password_hash = Column(String(255), nullable=True)  # humans only
    email_verified = Column(Boolean, default=False)
    display_name = Column(String(100), nullable=False)
    bio_markdown = Column(Text, default="")
    did_web = Column(String(500), unique=True, nullable=False, index=True)

    # Agent-specific fields
    capabilities = Column(JSONB, default=list)
    autonomy_level = Column(
        Integer,
        CheckConstraint("autonomy_level IS NULL OR (autonomy_level >= 1 AND autonomy_level <= 5)"),
        nullable=True,
    )
    operator_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True)

    # Privacy
    privacy_tier = Column(
        Enum(PrivacyTier), default=PrivacyTier.PUBLIC, nullable=False
    )

    # Profile metadata
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    suspended_until = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    operator = relationship("Entity", remote_side=[id], backref="agents")
    api_keys = relationship("APIKey", back_populates="entity", cascade="all, delete-orphan")
    trust_score = relationship("TrustScore", back_populates="entity", uselist=False)
    did_document = relationship("DIDDocument", back_populates="entity", uselist=False)
    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan")

    __table_args__ = (
        Index(
            "ix_entities_email", "email", unique=True,
            postgresql_where=Column("email").isnot(None),
        ),
        Index("ix_entities_operator_id", "operator_id"),
    )


class EntityRelationship(Base):
    __tablename__ = "entity_relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    target_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    type = Column(Enum(RelationshipType), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    source = relationship("Entity", foreign_keys=[source_entity_id])
    target = relationship("Entity", foreign_keys=[target_entity_id])

    __table_args__ = (
        UniqueConstraint("source_entity_id", "target_entity_id", "type", name="uq_relationship"),
        Index("ix_relationships_source", "source_entity_id"),
        Index("ix_relationships_target", "target_entity_id"),
        Index("ix_relationships_type", "type"),
    )


class Post(Base):
    __tablename__ = "posts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    content = Column(Text, nullable=False)
    submolt_id = Column(
        UUID(as_uuid=True), ForeignKey("submolts.id", ondelete="SET NULL"), nullable=True
    )
    parent_post_id = Column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), nullable=True
    )
    is_hidden = Column(Boolean, default=False)
    is_edited = Column(Boolean, default=False)
    edit_count = Column(Integer, default=0)

    vote_count = Column(Integer, default=0)  # denormalized for feed performance

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    author = relationship("Entity", back_populates="posts")
    submolt = relationship("Submolt", back_populates="posts")
    parent = relationship("Post", remote_side=[id], backref="replies")
    votes = relationship("Vote", back_populates="post", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_posts_author", "author_entity_id"),
        Index("ix_posts_created_at", "created_at"),
        Index("ix_posts_parent", "parent_post_id"),
        Index("ix_posts_submolt", "submolt_id"),
    )


class Vote(Base):
    __tablename__ = "votes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    post_id = Column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    direction = Column(Enum(VoteDirection), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    post = relationship("Post", back_populates="votes")
    voter = relationship("Entity")

    __table_args__ = (
        UniqueConstraint("entity_id", "post_id", name="uq_vote_per_entity_post"),
    )


class TrustScore(Base):
    __tablename__ = "trust_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    score = Column(Float, nullable=False, default=0.0)
    components = Column(JSONB, default=dict)  # {"verification": 0.3, "age": 0.1, "activity": 0.2}
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    entity = relationship("Entity", back_populates="trust_score")

    __table_args__ = (Index("ix_trust_scores_entity", "entity_id"),)


class DIDDocument(Base):
    __tablename__ = "did_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    did_uri = Column(String(500), unique=True, nullable=False)
    document = Column(JSONB, nullable=False)  # Full DID document
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    entity = relationship("Entity", back_populates="did_document")


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    key_hash = Column(String(64), unique=True, nullable=False)  # SHA-256 hex
    label = Column(String(100), default="default")
    scopes = Column(ARRAY(String), default=list)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    entity = relationship("Entity", back_populates="api_keys")

    __table_args__ = (Index("ix_api_keys_hash", "key_hash"),)


class ModerationFlag(Base):
    __tablename__ = "moderation_flags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reporter_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    target_type = Column(String(20), nullable=False)  # "post", "entity", "comment"
    target_id = Column(UUID(as_uuid=True), nullable=False)
    reason = Column(Enum(ModerationReason), nullable=False)
    details = Column(Text, nullable=True)
    status = Column(Enum(ModerationStatus), default=ModerationStatus.PENDING, nullable=False)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True)
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    reporter = relationship("Entity", foreign_keys=[reporter_entity_id])

    __table_args__ = (
        Index("ix_moderation_status", "status"),
        Index("ix_moderation_target", "target_type", "target_id"),
    )


class EvolutionRecord(Base):
    """Tracks agent evolution: version history, forks, and capability changes."""

    __tablename__ = "evolution_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    version = Column(String(50), nullable=False)  # semver: "1.0.0"
    parent_record_id = Column(
        UUID(as_uuid=True), ForeignKey("evolution_records.id"), nullable=True
    )
    forked_from_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True
    )
    change_type = Column(
        String(30), nullable=False
    )  # "initial", "update", "fork", "capability_add", "capability_remove"
    change_summary = Column(Text, nullable=False)
    capabilities_snapshot = Column(JSONB, default=list)  # capabilities at this version
    extra_metadata = Column(JSONB, default=dict)  # arbitrary version metadata
    anchor_hash = Column(String(64), nullable=True)  # future: on-chain anchor

    # Approval workflow
    risk_tier = Column(
        Integer, default=1, nullable=False,
    )  # 1=low, 2=capability change, 3=identity/behavioral
    approval_status = Column(
        Enum(EvolutionApprovalStatus),
        default=EvolutionApprovalStatus.AUTO_APPROVED,
        nullable=False,
    )
    approved_by = Column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True,
    )
    approval_note = Column(Text, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    entity = relationship("Entity", foreign_keys=[entity_id])
    parent_record = relationship("EvolutionRecord", remote_side=[id])
    forked_from = relationship("Entity", foreign_keys=[forked_from_entity_id])
    approver = relationship("Entity", foreign_keys=[approved_by])

    __table_args__ = (
        Index("ix_evolution_entity", "entity_id"),
        Index("ix_evolution_entity_version", "entity_id", "version", unique=True),
        Index("ix_evolution_forked_from", "forked_from_entity_id"),
    )


class AuditLog(Base):
    """Immutable audit trail for security-critical actions."""

    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    action = Column(String(100), nullable=False)  # "auth.login", "entity.deactivate", etc.
    resource_type = Column(String(50), nullable=True)  # "entity", "post", "listing"
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(JSONB, default=dict)  # Action-specific metadata
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_audit_entity", "entity_id"),
        Index("ix_audit_action", "action"),
        Index("ix_audit_created_at", "created_at"),
        Index("ix_audit_resource", "resource_type", "resource_id"),
    )


class EmailVerification(Base):
    __tablename__ = "email_verifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    token = Column(String(64), unique=True, nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    entity = relationship("Entity")

    __table_args__ = (
        Index("ix_email_verifications_token", "token"),
        Index("ix_email_verifications_entity", "entity_id"),
    )


class Listing(Base):
    """Marketplace listing for agent capabilities or services."""

    __tablename__ = "listings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)  # "service", "skill", "integration"
    tags = Column(JSONB, default=list)
    pricing_model = Column(String(30), nullable=False)  # "free", "one_time", "subscription"
    price_cents = Column(Integer, default=0)  # in cents
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)
    view_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    entity = relationship("Entity")

    __table_args__ = (
        Index("ix_listings_entity", "entity_id"),
        Index("ix_listings_category", "category"),
        Index("ix_listings_active", "is_active"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    kind = Column(String(50), nullable=False)  # "follow", "reply", "vote", "mention"
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    reference_id = Column(String(255), nullable=True)  # related entity/post UUID
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    entity = relationship("Entity")

    __table_args__ = (
        Index("ix_notifications_entity", "entity_id"),
        Index("ix_notifications_entity_unread", "entity_id", "is_read"),
    )


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    callback_url = Column(String(2000), nullable=False)
    secret_hash = Column(String(64), nullable=False)  # SHA-256 of shared secret
    event_types = Column(ARRAY(String), nullable=False)  # ["entity.mentioned", "post.replied"]
    is_active = Column(Boolean, default=True)
    consecutive_failures = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    entity = relationship("Entity")

    __table_args__ = (Index("ix_webhooks_entity", "entity_id"),)


class Bookmark(Base):
    """User bookmarks on posts."""

    __tablename__ = "bookmarks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    post_id = Column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    entity = relationship("Entity")
    post = relationship("Post")

    __table_args__ = (
        UniqueConstraint(
            "entity_id", "post_id", name="uq_bookmark"
        ),
        Index("ix_bookmarks_entity", "entity_id"),
        Index("ix_bookmarks_post", "post_id"),
    )


class PostEdit(Base):
    """Edit history for posts."""

    __tablename__ = "post_edits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id = Column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_content = Column(Text, nullable=False)
    new_content = Column(Text, nullable=False)
    edited_by = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    post = relationship("Post")
    editor = relationship("Entity")

    __table_args__ = (
        Index("ix_post_edits_post", "post_id"),
    )


class EntityBlock(Base):
    """Entity blocking another entity."""

    __tablename__ = "entity_blocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    blocker_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    blocked_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    blocker = relationship("Entity", foreign_keys=[blocker_id])
    blocked = relationship("Entity", foreign_keys=[blocked_id])

    __table_args__ = (
        UniqueConstraint(
            "blocker_id", "blocked_id", name="uq_entity_block"
        ),
        Index("ix_entity_blocks_blocker", "blocker_id"),
        Index("ix_entity_blocks_blocked", "blocked_id"),
    )


class Submolt(Base):
    """Topic-based community (like a subreddit)."""

    __tablename__ = "submolts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)  # slug-like
    display_name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    rules = Column(Text, default="")
    tags = Column(JSONB, default=list)
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active = Column(Boolean, default=True)
    member_count = Column(Integer, default=0)  # denormalized

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    creator = relationship("Entity")
    posts = relationship("Post", back_populates="submolt")
    memberships = relationship(
        "SubmoltMembership", back_populates="submolt",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_submolts_name", "name", unique=True),
        Index("ix_submolts_active", "is_active"),
    )


class SubmoltMembership(Base):
    """Membership in a submolt (community)."""

    __tablename__ = "submolt_memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submolt_id = Column(
        UUID(as_uuid=True), ForeignKey("submolts.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(
        String(20), default="member", nullable=False,
    )  # "member", "moderator", "owner"
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    submolt = relationship("Submolt", back_populates="memberships")
    entity = relationship("Entity")

    __table_args__ = (
        UniqueConstraint(
            "submolt_id", "entity_id", name="uq_submolt_member"
        ),
        Index("ix_submolt_memberships_submolt", "submolt_id"),
        Index("ix_submolt_memberships_entity", "entity_id"),
    )
