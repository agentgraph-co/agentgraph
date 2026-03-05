from __future__ import annotations

import json as _json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.agent_service import (
    create_agent,
    get_agent_by_id,
    get_operator_agents,
    register_agent_direct,
    rotate_api_key,
)
from src.api.auth_service import get_entity_by_email
from src.api.deactivation import cascade_deactivate
from src.api.deps import get_current_entity, require_scope
from src.api.rate_limit import rate_limit_auth, rate_limit_reads, rate_limit_writes
from src.api.schemas import (
    AgentCreatedResponse,
    AgentDiscoveryItem,
    AgentDiscoveryResponse,
    AgentResponse,
    ApiKeyRotatedResponse,
    ClaimAgentRequest,
    ClaimAgentResponse,
    CreateAgentRequest,
    MessageResponse,
    RegisterAgentRequest,
    SetOperatorRequest,
    UpdateAgentRequest,
    UpdateAutonomyRequest,
)
from src.audit import log_action
from src.database import get_db
from src.models import (
    APIKey,
    CapabilityEndorsement,
    Entity,
    EntityRelationship,
    EntityType,
    EvolutionRecord,
    Post,
    RelationshipType,
    Review,
    TrustScore,
    Vote,
)

logger = logging.getLogger(__name__)

# --- Heartbeat schemas ---

_VALID_STATUSES = {"active", "busy", "maintenance"}


class HeartbeatRequest(BaseModel):
    status: str | None = Field(None, description="Agent status: active, busy, or maintenance")


class HeartbeatResponse(BaseModel):
    ok: bool
    last_seen_at: str


class AgentStatusResponse(BaseModel):
    agent_id: str
    is_online: bool
    last_seen_at: str | None = None
    status: str

router = APIRouter(prefix="/agents", tags=["agents"])


def _require_human(entity: Entity) -> None:
    if entity.type != EntityType.HUMAN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only humans can manage agents",
        )


def _require_owner(operator: Entity, agent: Entity) -> None:
    if agent.operator_id != operator.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this agent",
        )


def _parse_discover_cursor(cursor: str) -> uuid.UUID | None:
    """Parse a UUID cursor string, returning None on invalid input."""
    try:
        return uuid.UUID(cursor)
    except (ValueError, AttributeError):
        return None


DAILY_AGENT_LIMIT = 10


async def _check_daily_agent_limit(
    db: AsyncSession, operator_id: uuid.UUID
) -> None:
    """Raise HTTP 429 if the operator has already registered >= 10 agents today."""
    from datetime import datetime, timezone

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    agent_count_today = await db.scalar(
        select(func.count())
        .select_from(Entity)
        .where(
            Entity.operator_id == operator_id,
            Entity.type == EntityType.AGENT,
            Entity.created_at >= today_start,
        )
    )
    if (agent_count_today or 0) >= DAILY_AGENT_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Agent registration limit: maximum 10 agents per day",
        )


@router.post(
    "/register",
    response_model=AgentCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_auth)],
)
async def register_agent(
    body: RegisterAgentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register an agent directly via API without requiring a human operator.

    Optionally link to an existing human operator by providing their email.
    Returns the agent details and a plaintext API key (shown once).
    """
    operator = None
    if body.operator_email:
        operator = await get_entity_by_email(db, body.operator_email)
        if operator is None or operator.type != EntityType.HUMAN:
            raise HTTPException(
                status_code=400,
                detail="Operator email not found or not a human account",
            )
        if not operator.is_active:
            raise HTTPException(
                status_code=400,
                detail="Operator account is deactivated",
            )

        # Enforce per-operator daily agent registration limit
        await _check_daily_agent_limit(db, operator.id)

    from src.content_filter import check_content, sanitize_html, sanitize_text

    filter_result = check_content(body.display_name)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Display name rejected: {', '.join(filter_result.flags)}",
        )
    body.display_name = sanitize_text(body.display_name)
    if body.bio_markdown:
        filter_result = check_content(body.bio_markdown)
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Bio rejected: {', '.join(filter_result.flags)}",
            )
        body.bio_markdown = sanitize_html(body.bio_markdown)

    agent, plaintext_key = await register_agent_direct(
        db,
        display_name=body.display_name,
        capabilities=body.capabilities,
        autonomy_level=body.autonomy_level,
        bio_markdown=body.bio_markdown,
        operator=operator,
    )
    await log_action(
        db,
        action="agent.register_direct",
        entity_id=agent.id,
        resource_type="entity",
        resource_id=agent.id,
        details={
            "display_name": body.display_name,
            "has_operator": operator is not None,
        },
    )
    await log_action(
        db,
        action="api_key.create",
        entity_id=agent.id,
        resource_type="api_key",
        resource_id=agent.id,
        details={"method": "register_direct"},
    )
    return AgentCreatedResponse(
        agent=AgentResponse.model_validate(agent),
        api_key=plaintext_key,
        claim_token=agent.claim_token,
    )


@router.post(
    "",
    response_model=AgentCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_writes), require_scope("agents:create")],
)
async def create_agent_endpoint(
    body: CreateAgentRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    _require_human(current_entity)

    # Enforce per-operator daily agent registration limit
    await _check_daily_agent_limit(db, current_entity.id)

    from src.content_filter import check_content, sanitize_html, sanitize_text

    filter_result = check_content(body.display_name)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Display name rejected: {', '.join(filter_result.flags)}",
        )
    body.display_name = sanitize_text(body.display_name)
    if body.bio_markdown:
        filter_result = check_content(body.bio_markdown)
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Bio rejected: {', '.join(filter_result.flags)}",
            )
        body.bio_markdown = sanitize_html(body.bio_markdown)

    agent, plaintext_key = await create_agent(
        db,
        operator=current_entity,
        display_name=body.display_name,
        capabilities=body.capabilities,
        autonomy_level=body.autonomy_level,
        bio_markdown=body.bio_markdown,
    )
    await log_action(
        db,
        action="agent.create",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=agent.id,
        details={"display_name": body.display_name},
    )
    await log_action(
        db,
        action="api_key.create",
        entity_id=current_entity.id,
        resource_type="api_key",
        resource_id=agent.id,
        details={"method": "create_agent", "agent_id": str(agent.id)},
    )
    return AgentCreatedResponse(
        agent=AgentResponse.model_validate(agent),
        api_key=plaintext_key,
    )


@router.get("", dependencies=[Depends(rate_limit_reads)])
async def list_agents(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    _require_human(current_entity)
    base = select(Entity).where(
        Entity.operator_id == current_entity.id,
        Entity.type == EntityType.AGENT,
    )
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar() or 0
    result = await db.execute(base.limit(limit).offset(offset))
    agents = result.scalars().all()
    return {
        "agents": [AgentResponse.model_validate(a) for a in agents],
        "total": total,
    }


@router.get(
    "/discover",
    response_model=AgentDiscoveryResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def discover_agents(
    db: AsyncSession = Depends(get_db),
    framework: str | None = Query(
        None,
        description="Filter by framework_source (e.g. 'openclaw', 'crewai', 'langchain')",
    ),
    capability: str | None = Query(
        None,
        description="Filter agents whose capabilities JSONB array contains this string",
    ),
    is_active: bool = Query(True, description="Filter by active status"),
    sort: str = Query(
        "trust_score",
        pattern="^(trust_score|created_at|display_name)$",
        description="Sort field: trust_score (default), created_at, display_name",
    ),
    cursor: str | None = Query(None, description="UUID cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size (max 100)"),
) -> AgentDiscoveryResponse:
    """Public agent discovery endpoint. No authentication required.

    Returns agents with their trust scores, supporting filtering by
    framework, capability, and active status, with cursor-based pagination.
    """
    # Base query: agents only, LEFT JOIN trust_scores for latest score
    query = (
        select(Entity, TrustScore.score.label("trust_score_value"))
        .outerjoin(TrustScore, TrustScore.entity_id == Entity.id)
        .where(Entity.type == EntityType.AGENT)
    )

    # Filter: is_active
    query = query.where(Entity.is_active == is_active)

    # Filter: framework_source
    if framework is not None:
        query = query.where(
            func.lower(Entity.framework_source) == framework.lower()
        )

    # Filter: capability — check if the JSONB array contains the string
    # Uses the PostgreSQL @> (contains) operator
    if capability is not None:
        cap_literal = func.cast(_json.dumps([capability]), JSONB)
        query = query.where(Entity.capabilities.op("@>")(cap_literal))

    # Sorting
    if sort == "trust_score":
        # Nulls last: agents without a trust score appear at the end
        query = query.order_by(
            TrustScore.score.desc().nullslast(),
            Entity.created_at.desc(),
            Entity.id.desc(),
        )
    elif sort == "created_at":
        query = query.order_by(
            Entity.created_at.desc(),
            Entity.id.desc(),
        )
    elif sort == "display_name":
        query = query.order_by(
            func.lower(Entity.display_name).asc(),
            Entity.id.asc(),
        )

    # Cursor-based pagination
    if cursor:
        cursor_id = _parse_discover_cursor(cursor)
        if cursor_id is None:
            raise HTTPException(status_code=400, detail="Invalid cursor")
        query = query.where(Entity.id < cursor_id)

    # Fetch one extra row to determine if there are more pages
    query = query.limit(limit + 1)

    result = await db.execute(query)
    rows = result.all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    agents_list: list[AgentDiscoveryItem] = []
    for row in rows:
        entity = row[0]
        score_value = row[1]

        # Truncate bio_markdown to 200 characters
        bio = entity.bio_markdown or ""
        if len(bio) > 200:
            bio = bio[:200] + "..."

        agents_list.append(AgentDiscoveryItem(
            id=entity.id,
            display_name=entity.display_name,
            type=entity.type.value if hasattr(entity.type, "value") else str(entity.type),
            framework_source=entity.framework_source,
            capabilities=entity.capabilities or [],
            autonomy_level=entity.autonomy_level,
            trust_score=round(score_value, 4) if score_value is not None else None,
            is_active=entity.is_active,
            is_provisional=entity.is_provisional,
            created_at=entity.created_at,
            last_seen_at=entity.last_seen_at,
            bio_markdown=bio,
        ))

    next_cursor = None
    if has_more and agents_list:
        next_cursor = str(agents_list[-1].id)

    return AgentDiscoveryResponse(agents=agents_list, next_cursor=next_cursor)


@router.get(
    "/my-fleet",
    dependencies=[Depends(rate_limit_reads)],
)
async def get_fleet_summary(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get operator's agent fleet with aggregate metrics."""
    _require_human(current_entity)

    agents = await get_operator_agents(db, current_entity.id)
    if not agents:
        return {
            "operator_id": str(current_entity.id),
            "agent_count": 0,
            "agents": [],
            "totals": {
                "posts": 0,
                "votes_received": 0,
                "followers": 0,
                "endorsements": 0,
            },
        }

    agent_ids = [a.id for a in agents]

    # Aggregate posts per agent
    post_result = await db.execute(
        select(
            Post.author_entity_id,
            func.count().label("cnt"),
        )
        .where(
            Post.author_entity_id.in_(agent_ids),
            Post.is_hidden.is_(False),
        )
        .group_by(Post.author_entity_id)
    )
    post_counts = dict(post_result.all())

    # Aggregate votes received per agent
    vote_result = await db.execute(
        select(
            Post.author_entity_id,
            func.coalesce(func.sum(Post.vote_count), 0).label("total_votes"),
        )
        .where(
            Post.author_entity_id.in_(agent_ids),
            Post.is_hidden.is_(False),
        )
        .group_by(Post.author_entity_id)
    )
    vote_counts = dict(vote_result.all())

    # Aggregate followers per agent (exclude deactivated followers)
    follower_result = await db.execute(
        select(
            EntityRelationship.target_entity_id,
            func.count().label("cnt"),
        )
        .join(
            Entity,
            EntityRelationship.source_entity_id == Entity.id,
        )
        .where(
            EntityRelationship.target_entity_id.in_(agent_ids),
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
        )
        .group_by(EntityRelationship.target_entity_id)
    )
    follower_counts = dict(follower_result.all())

    # Aggregate endorsements per agent (exclude deactivated endorsers)
    endorse_result = await db.execute(
        select(
            CapabilityEndorsement.agent_entity_id,
            func.count().label("cnt"),
        )
        .join(
            Entity,
            CapabilityEndorsement.endorser_entity_id == Entity.id,
        )
        .where(
            CapabilityEndorsement.agent_entity_id.in_(agent_ids),
            Entity.is_active.is_(True),
        )
        .group_by(CapabilityEndorsement.agent_entity_id)
    )
    endorse_counts = dict(endorse_result.all())

    agent_list = []
    total_posts = 0
    total_votes = 0
    total_followers = 0
    total_endorsements = 0

    for agent in agents:
        p = post_counts.get(agent.id, 0)
        v = vote_counts.get(agent.id, 0)
        f = follower_counts.get(agent.id, 0)
        e = endorse_counts.get(agent.id, 0)
        total_posts += p
        total_votes += v
        total_followers += f
        total_endorsements += e

        agent_list.append({
            "id": str(agent.id),
            "display_name": agent.display_name,
            "autonomy_level": agent.autonomy_level,
            "is_active": agent.is_active,
            "posts": p,
            "votes_received": v,
            "followers": f,
            "endorsements": e,
            "created_at": agent.created_at.isoformat(),
        })

    return {
        "operator_id": str(current_entity.id),
        "agent_count": len(agents),
        "agents": agent_list,
        "totals": {
            "posts": total_posts,
            "votes_received": total_votes,
            "followers": total_followers,
            "endorsements": total_endorsements,
        },
    }


@router.get(
    "/{agent_id}/api-keys",
    dependencies=[Depends(rate_limit_reads)],
)
async def list_api_keys(
    agent_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List API keys for an agent. Operator only. Hashes are never exposed."""
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)
    _require_owner(current_entity, agent)

    total = await db.scalar(
        select(func.count()).select_from(APIKey).where(APIKey.entity_id == agent_id)
    ) or 0

    result = await db.execute(
        select(APIKey)
        .where(APIKey.entity_id == agent_id)
        .order_by(APIKey.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    keys = result.scalars().all()

    return {
        "agent_id": str(agent_id),
        "keys": [
            {
                "id": str(k.id),
                "label": k.label,
                "scopes": k.scopes or [],
                "is_active": k.is_active,
                "created_at": k.created_at.isoformat(),
                "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
                "key_prefix": k.key_hash[:8],
            }
            for k in keys
        ],
        "total": total,
    }


@router.patch(
    "/{agent_id}/api-keys/{key_id}",
    dependencies=[Depends(rate_limit_writes), require_scope("agents:keys")],
)
async def update_api_key(
    agent_id: uuid.UUID,
    key_id: uuid.UUID,
    label: str = Query(..., min_length=1, max_length=100),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Update label on an API key. Operator only."""
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)
    _require_owner(current_entity, agent)

    api_key = await db.get(APIKey, key_id)
    if api_key is None or api_key.entity_id != agent_id:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.label = label
    await db.flush()
    return {"message": f"Key label updated to '{label}'", "key_id": str(key_id)}


@router.delete(
    "/{agent_id}/api-keys/{key_id}",
    dependencies=[Depends(rate_limit_writes), require_scope("agents:keys")],
)
async def revoke_api_key(
    agent_id: uuid.UUID,
    key_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a specific API key. Operator only."""
    from datetime import datetime, timezone

    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)
    _require_owner(current_entity, agent)

    api_key = await db.get(APIKey, key_id)
    if api_key is None or api_key.entity_id != agent_id:
        raise HTTPException(status_code=404, detail="API key not found")

    if not api_key.is_active:
        raise HTTPException(status_code=409, detail="Key already revoked")

    api_key.is_active = False
    api_key.revoked_at = datetime.now(timezone.utc)
    await log_action(
        db,
        action="api_key.revoke",
        entity_id=current_entity.id,
        resource_type="api_key",
        resource_id=key_id,
        details={"agent_id": str(agent_id)},
    )
    await db.flush()
    return {"message": "API key revoked", "key_id": str(key_id)}


@router.get("/{agent_id}", response_model=AgentResponse, dependencies=[Depends(rate_limit_reads)])
async def get_agent(
    agent_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)
    _require_owner(current_entity, agent)
    return AgentResponse.model_validate(agent)


@router.patch(
    "/{agent_id}",
    response_model=AgentResponse,
    dependencies=[Depends(rate_limit_writes), require_scope("agents:update")],
)
async def update_agent(
    agent_id: uuid.UUID,
    body: UpdateAgentRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)
    _require_owner(current_entity, agent)

    from src.content_filter import check_content, sanitize_html, sanitize_text

    update_data = body.model_dump(exclude_unset=True)
    if "display_name" in update_data and update_data["display_name"]:
        filter_result = check_content(update_data["display_name"])
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Display name rejected: {', '.join(filter_result.flags)}",
            )
        update_data["display_name"] = sanitize_text(update_data["display_name"])
    if "bio_markdown" in update_data and update_data["bio_markdown"]:
        filter_result = check_content(update_data["bio_markdown"])
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Bio rejected: {', '.join(filter_result.flags)}",
            )
        update_data["bio_markdown"] = sanitize_html(update_data["bio_markdown"])

    for field, value in update_data.items():
        setattr(agent, field, value)
    await db.flush()
    await db.refresh(agent)

    await log_action(
        db,
        action="agent.update",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=agent_id,
        details={"fields": list(update_data.keys())},
    )

    return AgentResponse.model_validate(agent)


@router.post(
    "/{agent_id}/rotate-key", response_model=ApiKeyRotatedResponse,
    dependencies=[Depends(rate_limit_writes), require_scope("agents:keys")],
)
async def rotate_key(
    agent_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)
    _require_owner(current_entity, agent)

    new_key = await rotate_api_key(db, agent)
    await log_action(
        db,
        action="api_key.rotate",
        entity_id=current_entity.id,
        resource_type="api_key",
        resource_id=agent.id,
        details={"agent_id": str(agent.id)},
    )
    return ApiKeyRotatedResponse(
        api_key=new_key,
        message="API key rotated. Old key is now revoked.",
    )


@router.delete(
    "/{agent_id}", response_model=MessageResponse,
    dependencies=[Depends(rate_limit_writes), require_scope("agents:update")],
)
async def deactivate_agent(
    agent_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)
    _require_owner(current_entity, agent)

    agent.is_active = False
    await log_action(
        db,
        action="agent.deactivate",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=agent.id,
    )
    await db.flush()

    await cascade_deactivate(
        db, agent.id, performed_by=current_entity.id,
    )

    return MessageResponse(message="Agent deactivated")


@router.get(
    "/{agent_id}/public",
    response_model=AgentResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_agent_public(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get an agent's public profile (no authentication required)."""
    agent = await get_agent_by_id(db, agent_id)
    if agent is None or not agent.is_active:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@router.patch(
    "/{agent_id}/set-operator",
    response_model=AgentResponse,
    dependencies=[Depends(rate_limit_writes), require_scope("agents:update")],
)
async def set_operator(
    agent_id: uuid.UUID,
    body: SetOperatorRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Link an agent to a human operator.

    The agent must either have no operator (unlinked) or the current user
    must be the existing operator (transfer).
    """
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)

    # Only allow if agent is unlinked or caller is current operator
    if agent.operator_id is not None and agent.operator_id != current_entity.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent already linked to another operator",
        )

    new_operator = await get_entity_by_email(db, body.operator_email)
    if new_operator is None or new_operator.type != EntityType.HUMAN:
        raise HTTPException(
            status_code=400,
            detail="Operator email not found or not a human account",
        )

    old_operator_id = agent.operator_id
    agent.operator_id = new_operator.id

    # Remove old operator relationship if exists
    if old_operator_id is not None:
        old_rel = await db.execute(
            select(EntityRelationship).where(
                EntityRelationship.source_entity_id == old_operator_id,
                EntityRelationship.target_entity_id == agent.id,
                EntityRelationship.type == RelationshipType.OPERATOR_AGENT,
            )
        )
        old = old_rel.scalar_one_or_none()
        if old:
            await db.delete(old)

    # Create new operator relationship
    rel = EntityRelationship(
        id=uuid.uuid4(),
        source_entity_id=new_operator.id,
        target_entity_id=agent.id,
        type=RelationshipType.OPERATOR_AGENT,
    )
    db.add(rel)

    await log_action(
        db,
        action="agent.set_operator",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=agent.id,
        details={
            "old_operator_id": str(old_operator_id) if old_operator_id else None,
            "new_operator_id": str(new_operator.id),
        },
    )
    await db.flush()
    return AgentResponse.model_validate(agent)


@router.delete(
    "/{agent_id}/operator",
    response_model=AgentResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def release_operator(
    agent_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Release an agent from its operator (unlink)."""
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)
    _require_owner(current_entity, agent)

    if agent.operator_id is None:
        raise HTTPException(status_code=400, detail="Agent has no operator")

    # Remove operator relationship
    from sqlalchemy import select

    from src.models import EntityRelationship, RelationshipType

    old_rel = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id == current_entity.id,
            EntityRelationship.target_entity_id == agent.id,
            EntityRelationship.type == RelationshipType.OPERATOR_AGENT,
        )
    )
    old = old_rel.scalar_one_or_none()
    if old:
        await db.delete(old)

    agent.operator_id = None

    await log_action(
        db,
        action="agent.release_operator",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=agent.id,
    )
    await db.flush()
    return AgentResponse.model_validate(agent)


@router.post(
    "/claim",
    response_model=ClaimAgentResponse,
    dependencies=[Depends(rate_limit_writes), require_scope("agents:update")],
)
async def claim_agent(
    body: ClaimAgentRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Claim a provisional agent by providing the claim token.

    Only human operators can claim agents. The agent is upgraded from
    provisional to full status, gaining unrestricted capabilities and
    higher rate limits.
    """
    _require_human(current_entity)

    # Look up agent by claim token
    result = await db.execute(
        select(Entity).where(
            Entity.claim_token == body.claim_token,
            Entity.is_provisional.is_(True),
            Entity.type == EntityType.AGENT,
        )
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(
            status_code=404,
            detail="Invalid or expired claim token",
        )

    if not agent.is_active:
        raise HTTPException(status_code=400, detail="Agent is deactivated")

    # Check expiration
    if agent.provisional_expires_at is not None:
        from datetime import datetime, timezone

        if datetime.now(timezone.utc) > agent.provisional_expires_at:
            raise HTTPException(
                status_code=410,
                detail="Claim token has expired. Agent must re-register.",
            )

    # Upgrade: provisional → full
    agent.is_provisional = False
    agent.claim_token = None
    agent.provisional_expires_at = None
    agent.operator_id = current_entity.id

    # Upgrade API key scopes
    key_result = await db.execute(
        select(APIKey).where(
            APIKey.entity_id == agent.id,
            APIKey.is_active.is_(True),
        )
    )
    for key in key_result.scalars().all():
        key.scopes = ["agent:read", "agent:write", "webhooks:manage"]

    # Create operator-agent relationship
    existing_rel = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id == current_entity.id,
            EntityRelationship.target_entity_id == agent.id,
            EntityRelationship.type == RelationshipType.OPERATOR_AGENT,
        )
    )
    if existing_rel.scalar_one_or_none() is None:
        rel = EntityRelationship(
            id=uuid.uuid4(),
            source_entity_id=current_entity.id,
            target_entity_id=agent.id,
            type=RelationshipType.OPERATOR_AGENT,
        )
        db.add(rel)

    await log_action(
        db,
        action="agent.claim",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=agent.id,
        details={
            "operator_id": str(current_entity.id),
            "was_provisional": True,
        },
    )
    await db.flush()
    await db.refresh(agent)

    return ClaimAgentResponse(
        agent=AgentResponse.model_validate(agent),
        message="Agent claimed successfully. Full capabilities unlocked.",
    )


@router.patch(
    "/{agent_id}/autonomy",
    response_model=AgentResponse,
    dependencies=[Depends(rate_limit_writes), require_scope("agents:update")],
)
async def update_autonomy(
    agent_id: uuid.UUID,
    body: UpdateAutonomyRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Update an agent's autonomy level (operator only). Audit-logged."""
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)
    _require_owner(current_entity, agent)

    old_level = agent.autonomy_level
    agent.autonomy_level = body.autonomy_level

    await log_action(
        db,
        action="agent.autonomy_update",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=agent.id,
        details={
            "old_autonomy_level": old_level,
            "new_autonomy_level": body.autonomy_level,
        },
    )
    await db.flush()
    return AgentResponse.model_validate(agent)


@router.get(
    "/{agent_id}/stats",
    dependencies=[Depends(rate_limit_reads)],
)
async def get_agent_stats(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get performance metrics for an agent. Public endpoint."""
    from datetime import datetime, timedelta, timezone

    agent = await db.get(Entity, agent_id)
    if agent is None or not agent.is_active:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.type != EntityType.AGENT:
        raise HTTPException(status_code=400, detail="Entity is not an agent")

    now = datetime.now(timezone.utc)
    thirty_ago = now - timedelta(days=30)

    # Post counts (top-level and replies)
    total_posts = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == agent_id,
            Post.is_hidden.is_(False),
            Post.parent_post_id.is_(None),
        )
    ) or 0

    total_replies = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == agent_id,
            Post.is_hidden.is_(False),
            Post.parent_post_id.isnot(None),
        )
    ) or 0

    posts_30d = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == agent_id,
            Post.is_hidden.is_(False),
            Post.created_at >= thirty_ago,
        )
    ) or 0

    # Votes cast
    votes_cast = await db.scalar(
        select(func.count()).select_from(Vote).where(
            Vote.entity_id == agent_id,
        )
    ) or 0

    # Votes received on agent's posts
    votes_received = await db.scalar(
        select(func.coalesce(func.sum(Post.vote_count), 0)).where(
            Post.author_entity_id == agent_id,
            Post.is_hidden.is_(False),
        )
    ) or 0

    # Endorsements received (exclude deactivated endorsers)
    endorsement_count = await db.scalar(
        select(func.count())
        .select_from(CapabilityEndorsement)
        .join(Entity, CapabilityEndorsement.endorser_entity_id == Entity.id)
        .where(
            CapabilityEndorsement.agent_entity_id == agent_id,
            Entity.is_active.is_(True),
        )
    ) or 0

    # Reviews received (exclude deactivated reviewers)
    review_result = await db.execute(
        select(
            func.avg(Review.rating),
            func.count(Review.id),
        )
        .join(Entity, Review.reviewer_entity_id == Entity.id)
        .where(
            Review.target_entity_id == agent_id,
            Entity.is_active.is_(True),
        )
    )
    review_row = review_result.one()
    avg_rating = round(float(review_row[0]), 2) if review_row[0] is not None else None
    review_count = review_row[1]

    # Follower count (exclude deactivated followers)
    follower_count = await db.scalar(
        select(func.count())
        .select_from(EntityRelationship)
        .join(Entity, EntityRelationship.source_entity_id == Entity.id)
        .where(
            EntityRelationship.target_entity_id == agent_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
        )
    ) or 0

    # Evolution count
    evolution_count = await db.scalar(
        select(func.count()).select_from(EvolutionRecord).where(
            EvolutionRecord.entity_id == agent_id,
        )
    ) or 0

    # Account age
    account_age_days = (now - agent.created_at.replace(tzinfo=timezone.utc)).days

    return {
        "agent_id": str(agent_id),
        "display_name": agent.display_name,
        "autonomy_level": agent.autonomy_level,
        "account_age_days": account_age_days,
        "posts": {
            "total": total_posts,
            "replies": total_replies,
            "last_30d": posts_30d,
        },
        "votes": {
            "cast": votes_cast,
            "received": votes_received,
        },
        "endorsements": endorsement_count,
        "reviews": {
            "count": review_count,
            "average_rating": avg_rating,
        },
        "followers": follower_count,
        "evolutions": evolution_count,
    }


# --- Agent heartbeat & status ---

_HEARTBEAT_REDIS_TTL = 600  # 10 minutes
_ONLINE_THRESHOLD = timedelta(minutes=5)


@router.post(
    "/{agent_id}/heartbeat",
    response_model=HeartbeatResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def agent_heartbeat(
    agent_id: uuid.UUID,
    body: HeartbeatRequest | None = None,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Record an agent heartbeat. Authenticated via API key or JWT.

    The caller must be the agent itself (API key auth) or the agent's
    human operator (JWT auth).  Optionally accepts a status string
    (``active``, ``busy``, or ``maintenance``).
    """
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.type != EntityType.AGENT:
        raise HTTPException(status_code=400, detail="Entity is not an agent")

    # Allow the agent itself OR its human operator
    is_self = current_entity.id == agent.id
    is_operator = (
        current_entity.type == EntityType.HUMAN
        and agent.operator_id == current_entity.id
    )
    if not is_self and not is_operator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorised to heartbeat this agent",
        )

    # Validate optional status
    agent_status_value: str | None = None
    if body is not None and body.status is not None:
        if body.status not in _VALID_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(sorted(_VALID_STATUSES))}",
            )
        agent_status_value = body.status

    now = datetime.now(timezone.utc)

    # Persist to DB
    agent.last_seen_at = now
    if agent_status_value is not None:
        agent.agent_status = agent_status_value
    await db.flush()
    await db.refresh(agent)

    # Store in Redis for fast reads
    try:
        from src.redis_client import get_redis

        r = get_redis()
        redis_value = _json.dumps({
            "status": agent_status_value or agent.agent_status or "active",
            "last_seen_at": now.isoformat(),
        })
        await r.set(f"agent:status:{agent_id}", redis_value, ex=_HEARTBEAT_REDIS_TTL)
    except Exception:
        logger.warning("Failed to write agent heartbeat to Redis", exc_info=True)

    return HeartbeatResponse(
        ok=True,
        last_seen_at=now.isoformat(),
    )


@router.get(
    "/{agent_id}/status",
    response_model=AgentStatusResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_agent_status(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get an agent's online status. Public, no authentication required.

    Checks Redis first for a cached heartbeat, then falls back to the
    database.  An agent is considered online if its ``last_seen_at``
    timestamp is within the last 5 minutes.
    """
    # Try Redis first
    cached = None
    try:
        from src.redis_client import get_redis

        r = get_redis()
        raw = await r.get(f"agent:status:{agent_id}")
        if raw is not None:
            cached = _json.loads(raw)
    except Exception:
        logger.warning("Failed to read agent status from Redis", exc_info=True)

    if cached is not None:
        last_seen = datetime.fromisoformat(cached["last_seen_at"])
        is_online = (datetime.now(timezone.utc) - last_seen) < _ONLINE_THRESHOLD
        return AgentStatusResponse(
            agent_id=str(agent_id),
            is_online=is_online,
            last_seen_at=cached["last_seen_at"],
            status=cached["status"] if is_online else "offline",
        )

    # Fall back to DB
    agent = await db.get(Entity, agent_id)
    if agent is None or not agent.is_active:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.type != EntityType.AGENT:
        raise HTTPException(status_code=400, detail="Entity is not an agent")

    if agent.last_seen_at is not None:
        if agent.last_seen_at.tzinfo is None:
            last_seen = agent.last_seen_at.replace(tzinfo=timezone.utc)
        else:
            last_seen = agent.last_seen_at
        is_online = (datetime.now(timezone.utc) - last_seen) < _ONLINE_THRESHOLD
        if is_online and agent.agent_status:
            resolved_status = agent.agent_status
        elif is_online:
            resolved_status = "active"
        else:
            resolved_status = "offline"
        return AgentStatusResponse(
            agent_id=str(agent_id),
            is_online=is_online,
            last_seen_at=last_seen.isoformat(),
            status=resolved_status,
        )

    # Never seen
    return AgentStatusResponse(
        agent_id=str(agent_id),
        is_online=False,
        last_seen_at=None,
        status="offline",
    )
