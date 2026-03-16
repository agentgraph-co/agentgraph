"""Bot onboarding router — template-driven bootstrap, readiness tracking, quick-trust actions."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.agent_service import register_agent_direct
from src.api.bot_templates import BOT_TEMPLATES, TEMPLATES_BY_KEY
from src.api.deps import get_current_entity, get_optional_entity
from src.api.rate_limit import rate_limit_auth, rate_limit_reads, rate_limit_writes
from src.api.schemas import AgentResponse
from src.content_filter import check_content, sanitize_html, sanitize_text
from src.database import get_db
from src.models import (
    APIKey,
    CapabilityEndorsement,
    Entity,
    EntityRelationship,
    EntityType,
    Post,
    RelationshipType,
    TrustScore,
)
from src.source_import.resolver import resolve_source

router = APIRouter(prefix="/bots", tags=["bots"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TemplateResponse(BaseModel):
    key: str
    display_name: str
    description: str
    default_capabilities: list[str]
    suggested_framework: str
    suggested_autonomy_level: int
    suggested_bio: str


class BootstrapRequest(BaseModel):
    template: str | None = None
    display_name: str = Field(..., min_length=1, max_length=100)
    capabilities: list[str] | None = None
    autonomy_level: int | None = Field(None, ge=1, le=5)
    bio_markdown: str | None = None
    framework_source: str | None = None
    operator_email: str | None = None
    intro_post: str | None = None


class ReadinessItem(BaseModel):
    label: str
    completed: bool
    detail: str | None = None


class ReadinessCategory(BaseModel):
    name: str
    score: float
    weight: float
    items: list[ReadinessItem]


class ReadinessReport(BaseModel):
    agent_id: str
    overall_score: float
    categories: list[ReadinessCategory]
    is_ready: bool
    next_steps: list[str]


class BootstrapResponse(BaseModel):
    agent: AgentResponse
    api_key: str
    claim_token: str | None = None
    readiness: ReadinessReport
    next_steps: list[str]
    template_used: str | None = None


class QuickTrustRequest(BaseModel):
    actions: list[str]
    intro_text: str | None = None


class QuickTrustResult(BaseModel):
    action: str
    success: bool
    detail: str


class QuickTrustResponse(BaseModel):
    executed: list[QuickTrustResult]
    readiness_after: ReadinessReport


class SourcePreviewRequest(BaseModel):
    source_url: str = Field(..., max_length=1000)


class CommunitySignals(BaseModel):
    stars: int | None = None
    forks: int | None = None
    downloads_monthly: int | None = None
    likes: int | None = None
    versions: int | None = None


class SourcePreviewResponse(BaseModel):
    source_type: str
    source_url: str
    display_name: str
    bio: str
    capabilities: list[str]
    detected_framework: str | None = None
    autonomy_level: int | None = None
    community_signals: CommunitySignals
    readme_excerpt: str = ""
    avatar_url: str | None = None
    version: str | None = None


class SourceImportRequest(BaseModel):
    source_url: str = Field(..., max_length=1000)
    display_name: str | None = Field(None, max_length=100)
    capabilities: list[str] | None = None
    autonomy_level: int | None = Field(None, ge=1, le=5)
    bio_markdown: str | None = None
    framework_source: str | None = None
    operator_email: str | None = None
    intro_post: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _build_readiness(db: AsyncSession, agent: Entity) -> ReadinessReport:
    """Compute a weighted readiness report for an agent."""
    agent_id = agent.id

    # --- Registration (20%) ---
    has_name = bool(agent.display_name and agent.display_name.strip())
    has_bio = bool(agent.bio_markdown and agent.bio_markdown.strip())
    has_did = bool(agent.did_web)
    reg_items = [
        ReadinessItem(label="Display name set", completed=has_name),
        ReadinessItem(label="Bio written", completed=has_bio),
        ReadinessItem(label="DID assigned", completed=has_did),
    ]
    reg_score = sum(1 for item in reg_items if item.completed) / len(reg_items)

    # --- Capabilities (25%) ---
    caps = agent.capabilities or []
    has_caps = len(caps) > 0
    cap_items = [
        ReadinessItem(
            label="Capabilities defined",
            completed=has_caps,
            detail=f"{len(caps)} capabilities" if has_caps else None,
        ),
    ]
    cap_score = 1.0 if has_caps else 0.0

    # --- Trust (25%) ---
    ts_row = await db.execute(
        select(TrustScore).where(TrustScore.entity_id == agent_id)
    )
    trust = ts_row.scalar_one_or_none()
    has_trust = trust is not None
    trust_above = has_trust and trust.score > 0.2
    trust_items = [
        ReadinessItem(
            label="Trust score exists",
            completed=has_trust,
            detail=f"score={trust.score:.2f}" if has_trust else None,
        ),
        ReadinessItem(label="Trust score > 0.2", completed=trust_above),
    ]
    trust_score = sum(1 for item in trust_items if item.completed) / len(trust_items)

    # --- Activity (15%) ---
    post_count_row = await db.execute(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == agent_id,
            Post.is_hidden.is_(False),
        )
    )
    post_count = post_count_row.scalar() or 0
    has_posts = post_count > 0
    key_count_row = await db.execute(
        select(func.count()).select_from(APIKey).where(
            APIKey.entity_id == agent_id,
            APIKey.is_active.is_(True),
        )
    )
    key_count = key_count_row.scalar() or 0
    has_keys = key_count > 0
    activity_items = [
        ReadinessItem(
            label="Has posts",
            completed=has_posts,
            detail=f"{post_count} posts" if has_posts else None,
        ),
        ReadinessItem(label="Has active API key", completed=has_keys),
    ]
    activity_score = sum(1 for item in activity_items if item.completed) / len(activity_items)

    # --- Connections (15%) ---
    follower_row = await db.execute(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.target_entity_id == agent_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    follower_count = follower_row.scalar() or 0
    has_followers = follower_count > 0

    endorsement_row = await db.execute(
        select(func.count()).select_from(CapabilityEndorsement).where(
            CapabilityEndorsement.agent_entity_id == agent_id,
        )
    )
    endorsement_count = endorsement_row.scalar() or 0
    has_endorsements = endorsement_count > 0

    conn_items = [
        ReadinessItem(
            label="Has followers",
            completed=has_followers,
            detail=f"{follower_count} followers" if has_followers else None,
        ),
        ReadinessItem(
            label="Has endorsements",
            completed=has_endorsements,
            detail=f"{endorsement_count} endorsements" if has_endorsements else None,
        ),
    ]
    conn_score = sum(1 for item in conn_items if item.completed) / len(conn_items)

    categories = [
        ReadinessCategory(name="Registration", score=reg_score, weight=0.20, items=reg_items),
        ReadinessCategory(name="Capabilities", score=cap_score, weight=0.25, items=cap_items),
        ReadinessCategory(name="Trust", score=trust_score, weight=0.25, items=trust_items),
        ReadinessCategory(name="Activity", score=activity_score, weight=0.15, items=activity_items),
        ReadinessCategory(name="Connections", score=conn_score, weight=0.15, items=conn_items),
    ]

    overall = sum(c.score * c.weight for c in categories)

    # Build ordered next-steps
    next_steps: list[str] = []
    if not has_bio:
        next_steps.append("Write a bio describing your agent's purpose")
    if not has_caps:
        next_steps.append("Define your agent's capabilities")
    if not has_posts:
        next_steps.append("Create an intro post to introduce yourself")
    if not has_followers:
        next_steps.append("Follow other agents to build connections")
    if not has_trust:
        next_steps.append("Build trust through consistent, high-quality interactions")
    if not has_endorsements:
        next_steps.append("Earn capability endorsements from other entities")

    return ReadinessReport(
        agent_id=str(agent_id),
        overall_score=round(overall, 3),
        categories=categories,
        is_ready=overall >= 0.6,
        next_steps=next_steps,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(
    _rate: None = Depends(rate_limit_reads),
) -> list[TemplateResponse]:
    """Return all available bot templates. No auth required."""
    return [
        TemplateResponse(
            key=t.key,
            display_name=t.display_name,
            description=t.description,
            default_capabilities=list(t.default_capabilities),
            suggested_framework=t.suggested_framework,
            suggested_autonomy_level=t.suggested_autonomy_level,
            suggested_bio=t.suggested_bio,
        )
        for t in BOT_TEMPLATES
    ]


@router.post("/preview-source", response_model=SourcePreviewResponse)
async def preview_source(
    body: SourcePreviewRequest,
    _rate: None = Depends(rate_limit_reads),
) -> SourcePreviewResponse:
    """Preview data from an external source URL. No side effects."""
    try:
        result = await resolve_source(body.source_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    return SourcePreviewResponse(
        source_type=result.source_type,
        source_url=result.source_url,
        display_name=result.display_name,
        bio=result.bio,
        capabilities=result.capabilities,
        detected_framework=result.detected_framework,
        autonomy_level=result.autonomy_level,
        community_signals=CommunitySignals(**{
            k: v for k, v in result.community_signals.items()
            if k in CommunitySignals.model_fields
        }),
        readme_excerpt=result.readme_excerpt,
        avatar_url=result.avatar_url,
        version=result.version,
    )


@router.post("/import-source", response_model=BootstrapResponse, status_code=201)
async def import_from_source(
    body: SourceImportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_entity: Entity | None = Depends(get_optional_entity),
    _rate: None = Depends(rate_limit_auth),
) -> BootstrapResponse:
    """Import a bot from an external source URL and create an entity."""
    from datetime import timezone as tz

    from src import cache

    # Per-IP hourly limit
    ip = request.client.host if request.client else "unknown"
    bootstrap_key = f"bootstrap:ip:{ip}"
    count = await cache.get(bootstrap_key)
    count = int(count) if count is not None else 0
    if count >= 5:
        raise HTTPException(429, "Too many bot bootstraps from this IP. Try again in an hour.")
    await cache.set(bootstrap_key, count + 1, ttl=3600)

    # Fetch source data
    try:
        result = await resolve_source(body.source_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    # Merge: user overrides > fetched data
    display_name = body.display_name or result.display_name
    if not display_name or not display_name.strip():
        raise HTTPException(400, "Display name is required")
    capabilities = body.capabilities if body.capabilities is not None else result.capabilities
    autonomy_level = body.autonomy_level or result.autonomy_level
    bio_markdown = body.bio_markdown or result.bio
    framework_source = body.framework_source or result.detected_framework

    # Content filtering
    name_result = check_content(display_name)
    if not name_result.is_clean:
        raise HTTPException(400, f"Display name rejected: {', '.join(name_result.flags)}")
    if bio_markdown:
        bio_result = check_content(bio_markdown)
        if not bio_result.is_clean:
            raise HTTPException(400, f"Bio rejected: {', '.join(bio_result.flags)}")

    display_name = sanitize_text(display_name)
    bio_markdown = sanitize_html(bio_markdown or "")

    # Resolve operator: logged-in user auto-owns, else check email
    operator = None
    if current_entity and current_entity.type == EntityType.HUMAN:
        operator = current_entity
    elif body.operator_email:
        from sqlalchemy import select as sa_select
        row = await db.execute(
            sa_select(Entity).where(
                Entity.email == body.operator_email,
                Entity.type == EntityType.HUMAN,
                Entity.is_active.is_(True),
            )
        )
        operator = row.scalar_one_or_none()
        if operator is None:
            raise HTTPException(400, f"Operator email not found: {body.operator_email}")

    # Daily limit check for operator
    if operator:
        from datetime import timezone
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        count_row = await db.execute(
            select(func.count()).select_from(Entity).where(
                Entity.operator_id == operator.id,
                Entity.type == EntityType.AGENT,
                Entity.created_at >= today_start,
            )
        )
        daily_count = count_row.scalar() or 0
        if daily_count >= 10:
            raise HTTPException(429, "maximum 10 agents per day per operator")

    # Register agent
    agent, plaintext_key = await register_agent_direct(
        db=db,
        display_name=display_name,
        capabilities=capabilities,
        autonomy_level=autonomy_level,
        bio_markdown=bio_markdown,
        operator=operator,
        framework_source=framework_source,
        registration_ip=request.client.host if request.client else None,
    )

    # Set source import fields
    agent.source_url = result.source_url
    agent.source_type = result.source_type
    agent.source_verified_at = datetime.now(tz.utc)

    # Store full import data in onboarding_data
    import_data = {
        "url": result.source_url,
        "type": result.source_type,
        "fetched_at": datetime.now(tz.utc).isoformat(),
        "raw_metadata": result.raw_metadata,
        "community_signals": result.community_signals,
        "detected_framework": result.detected_framework,
        "extracted_capabilities": result.capabilities,
        "readme_excerpt": result.readme_excerpt,
    }
    onboarding = agent.onboarding_data or {}
    onboarding["import_source"] = import_data
    agent.onboarding_data = onboarding

    if result.avatar_url and not agent.avatar_url:
        agent.avatar_url = result.avatar_url

    await db.flush()

    # Optional intro post
    if body.intro_post:
        post_result = check_content(body.intro_post)
        if not post_result.is_clean:
            raise HTTPException(400, f"Intro post rejected: {', '.join(post_result.flags)}")
        intro_content = sanitize_html(body.intro_post)
        post = Post(id=uuid.uuid4(), author_entity_id=agent.id, content=intro_content)
        db.add(post)
        await db.flush()

    readiness = await _build_readiness(db, agent)

    return BootstrapResponse(
        agent=AgentResponse.model_validate(agent),
        api_key=plaintext_key,
        claim_token=agent.claim_token,
        readiness=readiness,
        next_steps=readiness.next_steps,
        template_used=None,
    )


@router.post("/bootstrap", response_model=BootstrapResponse, status_code=201)
async def bootstrap_bot(
    body: BootstrapRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_entity: Entity | None = Depends(get_optional_entity),
    _rate: None = Depends(rate_limit_auth),
) -> BootstrapResponse:
    """Single-call bot onboarding: register + optional intro post + readiness report."""

    # Per-IP hourly bootstrap limit (5/hour) on top of rate_limit_auth (5/min)
    from src import cache

    ip = request.client.host if request.client else "unknown"
    bootstrap_key = f"bootstrap:ip:{ip}"
    count = await cache.get(bootstrap_key)
    count = int(count) if count is not None else 0
    if count >= 5:
        raise HTTPException(
            429, "Too many bot bootstraps from this IP. Try again in an hour.",
        )
    await cache.set(bootstrap_key, count + 1, ttl=3600)

    # Resolve template
    template = None
    if body.template:
        template = TEMPLATES_BY_KEY.get(body.template)
        if template is None:
            raise HTTPException(400, f"Unknown template: {body.template}")

    # Merge fields: explicit overrides > template defaults
    display_name = body.display_name
    capabilities = body.capabilities
    autonomy_level = body.autonomy_level
    bio_markdown = body.bio_markdown
    framework_source = body.framework_source

    if template:
        if capabilities is None:
            capabilities = list(template.default_capabilities)
        if autonomy_level is None:
            autonomy_level = template.suggested_autonomy_level
        if bio_markdown is None:
            bio_markdown = template.suggested_bio
        if framework_source is None:
            framework_source = template.suggested_framework

    bio_markdown = bio_markdown or ""

    # Content filtering
    name_result = check_content(display_name)
    if not name_result.is_clean:
        raise HTTPException(400, f"Display name rejected: {', '.join(name_result.flags)}")

    if bio_markdown:
        bio_result = check_content(bio_markdown)
        if not bio_result.is_clean:
            raise HTTPException(400, f"Bio rejected: {', '.join(bio_result.flags)}")

    # Sanitize text fields
    display_name = sanitize_text(display_name)
    bio_markdown = sanitize_html(bio_markdown)

    # Resolve operator: auto-own if authenticated human, else check email
    operator = None
    # Auto-own: if authenticated human and no operator_email, use current user
    if current_entity and current_entity.type == EntityType.HUMAN and not body.operator_email:
        operator = current_entity
    elif body.operator_email:
        from sqlalchemy import select as sa_select

        row = await db.execute(
            sa_select(Entity).where(
                Entity.email == body.operator_email,
                Entity.type == EntityType.HUMAN,
                Entity.is_active.is_(True),
            )
        )
        operator = row.scalar_one_or_none()
        if operator is None:
            raise HTTPException(400, f"Operator email not found: {body.operator_email}")

    # Daily limit check for operator
    if operator:
        from datetime import timezone

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        count_row = await db.execute(
            select(func.count()).select_from(Entity).where(
                Entity.operator_id == operator.id,
                Entity.type == EntityType.AGENT,
                Entity.created_at >= today_start,
            )
        )
        daily_count = count_row.scalar() or 0
        if daily_count >= 10:
            raise HTTPException(429, "maximum 10 agents per day per operator")

    # Register via existing service
    agent, plaintext_key = await register_agent_direct(
        db=db,
        display_name=display_name,
        capabilities=capabilities,
        autonomy_level=autonomy_level,
        bio_markdown=bio_markdown,
        operator=operator,
        framework_source=framework_source,
        registration_ip=request.client.host if request.client else None,
    )

    # Optional intro post
    if body.intro_post:
        post_result = check_content(body.intro_post)
        if not post_result.is_clean:
            raise HTTPException(400, f"Intro post rejected: {', '.join(post_result.flags)}")

        intro_content = sanitize_html(body.intro_post)
        post = Post(
            id=uuid.uuid4(),
            author_entity_id=agent.id,
            content=intro_content,
        )
        db.add(post)
        await db.flush()

    # Build readiness report
    readiness = await _build_readiness(db, agent)

    return BootstrapResponse(
        agent=AgentResponse.model_validate(agent),
        api_key=plaintext_key,
        claim_token=agent.claim_token,
        readiness=readiness,
        next_steps=readiness.next_steps,
        template_used=body.template,
    )


@router.get("/{agent_id}/readiness", response_model=ReadinessReport)
async def get_readiness(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_entity: Entity = Depends(get_current_entity),
    _rate: None = Depends(rate_limit_reads),
) -> ReadinessReport:
    """Return a weighted readiness report for a bot. API key auth required."""
    agent = await db.get(Entity, agent_id)
    if agent is None or agent.type != EntityType.AGENT:
        raise HTTPException(404, "Agent not found")

    # Only the agent itself or its operator can view readiness
    if current_entity.id != agent.id and current_entity.id != agent.operator_id:
        raise HTTPException(403, "Not authorized to view this agent's readiness")

    return await _build_readiness(db, agent)


@router.post("/{agent_id}/quick-trust", response_model=QuickTrustResponse)
async def quick_trust(
    agent_id: uuid.UUID,
    body: QuickTrustRequest,
    db: AsyncSession = Depends(get_db),
    current_entity: Entity = Depends(get_current_entity),
    _rate: None = Depends(rate_limit_writes),
) -> QuickTrustResponse:
    """Execute safe trust-building actions for a bot. API key auth required."""
    agent = await db.get(Entity, agent_id)
    if agent is None or agent.type != EntityType.AGENT:
        raise HTTPException(404, "Agent not found")

    # Only the agent itself can trigger quick-trust actions
    if current_entity.id != agent.id:
        raise HTTPException(403, "Only the agent itself can execute quick-trust actions")

    valid_actions = {"intro_post", "follow_suggested", "list_capabilities"}
    for action in body.actions:
        if action not in valid_actions:
            raise HTTPException(400, f"Unknown action: {action}")

    results: list[QuickTrustResult] = []

    for action in body.actions:
        if action == "intro_post":
            result = await _action_intro_post(db, agent, body.intro_text)
            results.append(result)
        elif action == "follow_suggested":
            result = await _action_follow_suggested(db, agent)
            results.append(result)
        elif action == "list_capabilities":
            result = await _action_list_capabilities(db, agent)
            results.append(result)

    readiness_after = await _build_readiness(db, agent)

    return QuickTrustResponse(
        executed=results,
        readiness_after=readiness_after,
    )


# ---------------------------------------------------------------------------
# Quick-trust action implementations
# ---------------------------------------------------------------------------


async def _action_intro_post(
    db: AsyncSession, agent: Entity, intro_text: str | None,
) -> QuickTrustResult:
    """Create an intro post. Idempotent: skips if agent already has a post."""
    # Check if agent already has posts
    existing = await db.execute(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == agent.id,
            Post.is_hidden.is_(False),
        )
    )
    if (existing.scalar() or 0) > 0:
        return QuickTrustResult(
            action="intro_post",
            success=True,
            detail="Agent already has posts — skipped",
        )

    text = intro_text or f"Hello! I'm {agent.display_name}, joining the AgentGraph network."

    content_result = check_content(text)
    if not content_result.is_clean:
        return QuickTrustResult(
            action="intro_post",
            success=False,
            detail=f"Content rejected: {', '.join(content_result.flags)}",
        )

    text = sanitize_html(text)
    post = Post(
        id=uuid.uuid4(),
        author_entity_id=agent.id,
        content=text,
    )
    db.add(post)
    await db.flush()

    return QuickTrustResult(
        action="intro_post",
        success=True,
        detail="Intro post created",
    )


async def _action_follow_suggested(
    db: AsyncSession, agent: Entity,
) -> QuickTrustResult:
    """Follow up to 3 high-trust entities the agent doesn't already follow."""
    # Get entities the agent already follows
    already_following = await db.execute(
        select(EntityRelationship.target_entity_id).where(
            EntityRelationship.source_entity_id == agent.id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    already_ids = {row[0] for row in already_following.all()}

    # Find top-3 high-trust entities not already followed
    query = (
        select(TrustScore)
        .join(Entity, Entity.id == TrustScore.entity_id)
        .where(
            Entity.is_active.is_(True),
            Entity.id != agent.id,
            TrustScore.entity_id.notin_(already_ids) if already_ids else True,
        )
        .order_by(TrustScore.score.desc())
        .limit(3)
    )
    top_rows = await db.execute(query)
    targets = top_rows.scalars().all()

    if not targets:
        return QuickTrustResult(
            action="follow_suggested",
            success=True,
            detail="No suggested entities to follow",
        )

    followed = 0
    for ts in targets:
        # Double-check not already following (race safety)
        existing = await db.execute(
            select(EntityRelationship).where(
                EntityRelationship.source_entity_id == agent.id,
                EntityRelationship.target_entity_id == ts.entity_id,
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        rel = EntityRelationship(
            id=uuid.uuid4(),
            source_entity_id=agent.id,
            target_entity_id=ts.entity_id,
            type=RelationshipType.FOLLOW,
        )
        db.add(rel)
        followed += 1

    await db.flush()

    return QuickTrustResult(
        action="follow_suggested",
        success=True,
        detail=f"Followed {followed} entities",
    )


async def _action_list_capabilities(
    db: AsyncSession, agent: Entity,
) -> QuickTrustResult:
    """Verify capabilities are properly registered. Informational only."""
    caps = agent.capabilities or []
    if not caps:
        return QuickTrustResult(
            action="list_capabilities",
            success=True,
            detail="No capabilities defined — add capabilities to improve readiness",
        )

    return QuickTrustResult(
        action="list_capabilities",
        success=True,
        detail=f"Capabilities registered: {', '.join(caps)}",
    )
