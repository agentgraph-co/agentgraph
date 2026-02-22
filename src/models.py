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
    COLLABORATION = "collaboration"
    SERVICE = "service"


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


class OrgRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


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
    avatar_url = Column(String(500), nullable=True)
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

    # Stripe Connect
    stripe_account_id = Column(String(255), nullable=True)

    # Framework bridge fields
    framework_source = Column(String(50), nullable=True)  # mcp, openclaw, langchain, native
    framework_trust_modifier = Column(Float, nullable=True, default=1.0)


    # SSO provider identity
    sso_provider_id = Column(String(255), nullable=True)

    # Organization membership
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )

    # Profile metadata
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    is_quarantined = Column(Boolean, default=False)
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
    is_pinned = Column(Boolean, default=False)
    edit_count = Column(Integer, default=0)
    flair = Column(String(50), nullable=True)  # e.g. "discussion", "question", "announcement"

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
        Index("ix_posts_vote_count", "vote_count"),
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
        Index("ix_votes_entity_post", "entity_id", "post_id"),
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

    contextual_scores = Column(JSONB, server_default="{}", default=dict)

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


class PasswordResetToken(Base):
    """Token for password reset flow."""

    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    token = Column(String(64), unique=True, nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)

    entity = relationship("Entity")

    __table_args__ = (
        Index("ix_password_reset_token", "token"),
        Index("ix_password_reset_entity", "entity_id"),
    )


class TokenBlacklist(Base):
    """Blacklisted JWT tokens (for logout)."""

    __tablename__ = "token_blacklist"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jti = Column(String(64), unique=True, nullable=False)  # JWT ID
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_token_blacklist_jti", "jti"),
        Index("ix_token_blacklist_expires", "expires_at"),
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
    reviews = relationship(
        "ListingReview", back_populates="listing",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_listings_entity", "entity_id"),
        Index("ix_listings_category", "category"),
        Index("ix_listings_active", "is_active"),
        Index("ix_listings_view_count", "view_count"),
    )


class ListingReview(Base):
    """Review/rating of a marketplace listing by an entity."""

    __tablename__ = "listing_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id = Column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    rating = Column(
        Integer,
        CheckConstraint("rating >= 1 AND rating <= 5"),
        nullable=False,
    )
    text = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    listing = relationship("Listing", back_populates="reviews")
    reviewer = relationship("Entity")

    __table_args__ = (
        UniqueConstraint(
            "listing_id", "reviewer_entity_id",
            name="uq_listing_review_per_pair",
        ),
        Index("ix_listing_reviews_listing", "listing_id"),
        Index("ix_listing_reviews_reviewer", "reviewer_entity_id"),
    )


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    ESCROW = "escrow"
    COMPLETED = "completed"
    DISPUTED = "disputed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class DisputeStatus(str, enum.Enum):
    OPEN = "open"
    NEGOTIATING = "negotiating"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class DisputeResolution(str, enum.Enum):
    RELEASE_FUNDS = "release_funds"
    CANCEL_AUTH = "cancel_auth"
    PARTIAL_REFUND = "partial_refund"


class Transaction(Base):
    """Marketplace transaction record."""

    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id = Column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="SET NULL"),
        nullable=True,
    )
    buyer_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    seller_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount_cents = Column(Integer, nullable=False, default=0)
    status = Column(
        Enum(TransactionStatus),
        default=TransactionStatus.PENDING,
        nullable=False,
    )
    listing_title = Column(String(200), nullable=False)
    listing_category = Column(String(50), nullable=False)
    notes = Column(Text, nullable=True)

    # Stripe payment fields
    stripe_payment_intent_id = Column(String(255), nullable=True)
    stripe_transfer_id = Column(String(255), nullable=True)
    platform_fee_cents = Column(Integer, nullable=True)

    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    listing = relationship("Listing")
    buyer = relationship("Entity", foreign_keys=[buyer_entity_id])
    seller = relationship("Entity", foreign_keys=[seller_entity_id])

    __table_args__ = (
        Index("ix_transactions_buyer", "buyer_entity_id"),
        Index("ix_transactions_seller", "seller_entity_id"),
        Index("ix_transactions_listing", "listing_id"),
        Index("ix_transactions_status", "status"),
        Index("ix_transactions_stripe_pi", "stripe_payment_intent_id"),
    )


class Dispute(Base):
    """Escrow dispute between buyer and seller."""

    __tablename__ = "disputes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(
        UUID(as_uuid=True), ForeignKey("transactions.id"),
        unique=True, nullable=False,
    )
    opened_by = Column(
        UUID(as_uuid=True), ForeignKey("entities.id"),
        nullable=False,
    )
    reason = Column(Text, nullable=False)
    status = Column(
        String(20), default="open", nullable=False,
    )
    resolution = Column(String(20), nullable=True)
    resolution_amount_cents = Column(Integer, nullable=True)
    resolved_by = Column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True,
    )
    admin_note = Column(Text, nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    transaction = relationship("Transaction")
    opener = relationship("Entity", foreign_keys=[opened_by])
    resolver = relationship("Entity", foreign_keys=[resolved_by])

    __table_args__ = (
        Index("ix_disputes_status", "status"),
        Index("ix_disputes_transaction", "transaction_id"),
        Index("ix_disputes_opened_by", "opened_by"),
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


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # Per-kind toggles (all default True = opt-in)
    follow_enabled = Column(Boolean, default=True)
    reply_enabled = Column(Boolean, default=True)
    vote_enabled = Column(Boolean, default=True)
    mention_enabled = Column(Boolean, default=True)
    endorsement_enabled = Column(Boolean, default=True)
    review_enabled = Column(Boolean, default=True)
    moderation_enabled = Column(Boolean, default=True)
    message_enabled = Column(Boolean, default=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    entity = relationship("Entity")


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    callback_url = Column(String(2000), nullable=False)
    secret_hash = Column(String(64), nullable=False)  # SHA-256 of shared secret
    signing_key = Column(String(64), nullable=True)  # Raw secret for HMAC signing
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


class CapabilityEndorsement(Base):
    """Endorsement/verification of an agent's capability by another entity."""

    __tablename__ = "capability_endorsements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    endorser_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    capability = Column(String(200), nullable=False)
    tier = Column(
        String(30), default="community_verified", nullable=False,
    )  # "self_declared", "community_verified", "formally_audited"
    comment = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    agent = relationship("Entity", foreign_keys=[agent_entity_id])
    endorser = relationship("Entity", foreign_keys=[endorser_entity_id])

    __table_args__ = (
        UniqueConstraint(
            "agent_entity_id", "endorser_entity_id", "capability",
            name="uq_capability_endorsement",
        ),
        Index("ix_cap_endorse_agent", "agent_entity_id"),
        Index("ix_cap_endorse_endorser", "endorser_entity_id"),
        Index("ix_cap_endorse_capability", "capability"),
    )


class TrustAttestation(Base):
    """Community attestation of trust for an entity."""

    __tablename__ = "trust_attestations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attester_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    attestation_type = Column(
        String(20), nullable=False,
    )  # "competent", "reliable", "safe", "responsive"
    context = Column(String(100), nullable=True)  # e.g. "code_review", "data_analysis"
    weight = Column(Float, nullable=False, default=0.5)  # attester's trust score at creation
    comment = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    attester = relationship("Entity", foreign_keys=[attester_entity_id])
    target = relationship("Entity", foreign_keys=[target_entity_id])

    __table_args__ = (
        UniqueConstraint(
            "attester_entity_id", "target_entity_id", "attestation_type",
            name="uq_trust_attestation",
        ),
        Index("ix_trust_attestations_target", "target_entity_id"),
        Index("ix_trust_attestations_attester", "attester_entity_id"),
    )


class Review(Base):
    """Review/rating of an entity by another entity."""

    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    rating = Column(
        Integer,
        CheckConstraint("rating >= 1 AND rating <= 5"),
        nullable=False,
    )
    text = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    target = relationship("Entity", foreign_keys=[target_entity_id])
    reviewer = relationship("Entity", foreign_keys=[reviewer_entity_id])

    __table_args__ = (
        UniqueConstraint(
            "target_entity_id", "reviewer_entity_id",
            name="uq_review_per_pair",
        ),
        Index("ix_reviews_target", "target_entity_id"),
        Index("ix_reviews_reviewer", "reviewer_entity_id"),
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


class Conversation(Base):
    """A direct message conversation between two entities."""

    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participant_a_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    participant_b_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    last_message_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    participant_a = relationship("Entity", foreign_keys=[participant_a_id])
    participant_b = relationship("Entity", foreign_keys=[participant_b_id])
    messages = relationship(
        "DirectMessage", back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="DirectMessage.created_at",
    )

    __table_args__ = (
        UniqueConstraint(
            "participant_a_id", "participant_b_id",
            name="uq_conversation_pair",
        ),
        Index("ix_conversations_a", "participant_a_id"),
        Index("ix_conversations_b", "participant_b_id"),
        Index("ix_conversations_last_msg", "last_message_at"),
    )


class DirectMessage(Base):
    """A direct message within a conversation."""

    __tablename__ = "direct_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("Entity")

    __table_args__ = (
        Index("ix_dm_conversation", "conversation_id"),
        Index("ix_dm_sender", "sender_id"),
        Index("ix_dm_created_at", "created_at"),
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


class AnalyticsEvent(Base):
    """Lightweight conversion funnel event for guest-to-register tracking."""

    __tablename__ = "analytics_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(50), nullable=False)  # guest_page_view, guest_cta_click, etc.
    session_id = Column(String(64), nullable=False)  # anonymous localStorage UUID
    page = Column(String(200), nullable=False)  # URL path where event occurred
    intent = Column(String(50), nullable=True)  # vote, follow, reply, etc.
    referrer = Column(String(500), nullable=True)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    extra_metadata = Column(JSONB, default=dict)  # arbitrary event data
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_analytics_event_type", "event_type"),
        Index("ix_analytics_created_at", "created_at"),
        Index("ix_analytics_session_id", "session_id"),
    )


class ModerationAppeal(Base):
    """Appeal against a moderation decision."""

    __tablename__ = "moderation_appeals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flag_id = Column(
        UUID(as_uuid=True), ForeignKey("moderation_flags.id", ondelete="CASCADE"),
        nullable=False,
    )
    appellant_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason = Column(Text, nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # pending/upheld/overturned
    resolved_by = Column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True,
    )
    resolution_note = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    flag = relationship("ModerationFlag")
    appellant = relationship("Entity", foreign_keys=[appellant_id])
    resolver = relationship("Entity", foreign_keys=[resolved_by])

    __table_args__ = (
        Index("ix_appeal_flag", "flag_id"),
        Index("ix_appeal_status", "status"),
    )


class FrameworkSecurityScan(Base):
    """Security scan record for framework-imported agents."""

    __tablename__ = "framework_security_scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    framework = Column(String(50), nullable=False)  # mcp, openclaw, langchain
    scan_result = Column(String(20), nullable=False)  # clean, warnings, critical
    vulnerabilities = Column(JSONB, default=list)
    scanned_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    entity = relationship("Entity")

    __table_args__ = (
        Index("ix_framework_scans_entity", "entity_id"),
        Index("ix_framework_scans_framework", "framework"),
        Index("ix_framework_scans_scanned_at", "scanned_at"),
    )


class VerificationBadge(Base):
    """Formal verification badge issued to an entity."""

    __tablename__ = "verification_badges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    badge_type = Column(
        String(50), nullable=False,
    )  # email_verified, identity_verified, capability_audited, agentgraph_verified
    issued_by = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    proof_url = Column(String(1000), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    entity = relationship("Entity", foreign_keys=[entity_id])
    issuer = relationship("Entity", foreign_keys=[issued_by])

    __table_args__ = (
        Index("ix_verification_badges_entity", "entity_id"),
        Index("ix_verification_badges_type", "badge_type"),
        Index("ix_verification_badges_active", "is_active"),
    )


class AuditRecord(Base):
    """Formal audit record for an entity."""

    __tablename__ = "audit_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    auditor_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    audit_type = Column(
        String(30), nullable=False,
    )  # security, capability, compliance
    result = Column(
        String(20), nullable=False,
    )  # pass, fail, partial
    findings = Column(JSONB, default=dict, nullable=True)
    report_url = Column(String(1000), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    target = relationship("Entity", foreign_keys=[target_entity_id])
    auditor = relationship("Entity", foreign_keys=[auditor_entity_id])

    __table_args__ = (
        Index("ix_audit_records_target", "target_entity_id"),
        Index("ix_audit_records_auditor", "auditor_entity_id"),
        Index("ix_audit_records_type", "audit_type"),
    )


class PropagationAlert(Base):
    """Network-wide safety alert record."""

    __tablename__ = "propagation_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_type = Column(String(50), nullable=False)  # "freeze", "quarantine", "network_alert"
    severity = Column(String(20), nullable=False)  # "info", "warning", "critical"
    message = Column(Text, nullable=False)
    issued_by = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True)
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    issuer = relationship("Entity", foreign_keys=[issued_by])

    __table_args__ = (
        Index("ix_propagation_alerts_type", "alert_type"),
        Index("ix_propagation_alerts_resolved", "is_resolved"),
        Index("ix_propagation_alerts_created", "created_at"),
    )


class Organization(Base):
    """Organization for grouping entities under enterprise management."""

    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    settings = Column(JSONB, default=dict)  # org-level config
    tier = Column(String(20), default="free", nullable=False)  # "free", "pro", "enterprise"
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    creator = relationship("Entity", foreign_keys=[created_by])
    memberships = relationship(
        "OrganizationMembership", back_populates="organization", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_organizations_name", "name", unique=True),
        Index("ix_organizations_active", "is_active"),
        Index("ix_organizations_tier", "tier"),
    )


class OrganizationMembership(Base):
    """Membership linking an entity to an organization with a specific role."""

    __tablename__ = "organization_memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(Enum(OrgRole), default=OrgRole.MEMBER, nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="memberships")
    entity = relationship("Entity")

    __table_args__ = (
        UniqueConstraint("organization_id", "entity_id", name="uq_org_membership"),
        Index("ix_org_memberships_org", "organization_id"),
        Index("ix_org_memberships_entity", "entity_id"),
    )


class AnomalyAlert(Base):
    """Anomaly detection alert for suspicious entity behavior."""

    __tablename__ = "anomaly_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    alert_type = Column(
        String(50), nullable=False,
    )  # "trust_velocity", "relationship_churn", "cluster_anomaly"
    severity = Column(
        String(20), nullable=False,
    )  # "low", "medium", "high"
    z_score = Column(Float, nullable=False)
    details = Column(JSONB, default=dict)
    is_resolved = Column(Boolean, default=False)
    resolved_by = Column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    entity = relationship("Entity", foreign_keys=[entity_id])
    resolver = relationship("Entity", foreign_keys=[resolved_by])

    __table_args__ = (
        Index("ix_anomaly_alerts_entity", "entity_id"),
        Index("ix_anomaly_alerts_type", "alert_type"),
        Index("ix_anomaly_alerts_resolved", "is_resolved"),
        Index("ix_anomaly_alerts_created", "created_at"),
    )
