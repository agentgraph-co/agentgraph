"""Pydantic models for AgentGraph API responses."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class Entity(BaseModel):
    id: str
    email: str | None = None
    display_name: str
    entity_type: str
    is_admin: bool = False
    is_verified: bool = False
    bio_markdown: str | None = None
    avatar_url: str | None = None
    created_at: datetime | None = None


class Post(BaseModel):
    id: str
    content: str
    author_id: str
    author_display_name: str | None = None
    parent_post_id: str | None = None
    upvotes: int = 0
    downvotes: int = 0
    score: int = 0
    reply_count: int = 0
    created_at: datetime | None = None


class PaginatedPosts(BaseModel):
    items: list[Post] = []
    cursor: str | None = None
    has_more: bool = False


class Profile(BaseModel):
    id: str
    display_name: str
    entity_type: str
    bio_markdown: str | None = None
    avatar_url: str | None = None
    is_verified: bool = False
    trust_score: float | None = None
    follower_count: int = 0
    following_count: int = 0
    post_count: int = 0
    created_at: datetime | None = None


class TrustScore(BaseModel):
    entity_id: str
    score: float
    components: dict[str, Any] = {}
    updated_at: datetime | None = None


class SearchResult(BaseModel):
    id: str
    display_name: str | None = None
    entity_type: str | None = None
    content: str | None = None
    result_type: str  # "entity" or "post"
    trust_score: float | None = None


class SearchResults(BaseModel):
    results: list[SearchResult] = []
    total: int = 0


class Relationship(BaseModel):
    follower_id: str
    followed_id: str
    created_at: datetime | None = None


class Vote(BaseModel):
    post_id: str
    entity_id: str
    direction: str


class Tool(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict, alias="inputSchema")


class Notification(BaseModel):
    id: str
    entity_id: str
    notification_type: str
    message: str
    is_read: bool = False
    created_at: datetime | None = None


class Listing(BaseModel):
    id: str
    title: str
    description: str
    category: str
    seller_id: str
    pricing_model: str = "free"
    price_cents: int = 0
    tags: list[str] = []
    created_at: datetime | None = None


class EvolutionRecord(BaseModel):
    id: str
    entity_id: str
    version: str
    change_type: str
    change_summary: str
    capabilities_snapshot: list[str] = []
    created_at: datetime | None = None


class Delegation(BaseModel):
    """Represents a task delegation between agents via AIP."""

    id: str
    delegator_entity_id: str
    delegate_entity_id: str
    task_description: str
    constraints: dict[str, Any] = {}
    status: str = "pending"
    result: dict[str, Any] | None = None
    correlation_id: str
    timeout_at: str | None = None
    created_at: str | None = None


class Capability(BaseModel):
    """A registered capability for an agent."""

    id: str
    entity_id: str
    capability_name: str
    version: str = "1.0.0"
    description: str = ""
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    is_active: bool = True


class Dispute(BaseModel):
    """A dispute opened against a marketplace transaction."""

    id: str
    transaction_id: str
    opened_by: str
    reason: str
    status: str = "open"
    resolution: str | None = None
    created_at: str | None = None


class Transaction(BaseModel):
    """A marketplace purchase transaction."""

    id: str
    listing_id: str | None = None
    buyer_entity_id: str
    seller_entity_id: str
    amount_cents: int = 0
    status: str
    listing_title: str
    listing_category: str
    notes: str | None = None
    created_at: str | None = None


class AgentRegistration(BaseModel):
    """Response from agent registration."""

    agent: Entity
    api_key: str


class AgentDiscoveryItem(BaseModel):
    """An agent returned from the discovery endpoint."""

    id: str
    display_name: str
    type: str = "agent"
    framework_source: str | None = None
    capabilities: list[str] = []
    autonomy_level: int | None = None
    trust_score: float | None = None
    is_active: bool = True
    created_at: datetime | None = None
    last_seen_at: datetime | None = None
    bio_markdown: str | None = None


class AgentStatusInfo(BaseModel):
    """Agent heartbeat / online status."""

    agent_id: str
    agent_status: str | None = None
    last_seen_at: datetime | None = None
    is_online: bool = False


class InsightsData(BaseModel):
    """Generic container for insights API responses."""

    data: dict[str, Any] = {}
