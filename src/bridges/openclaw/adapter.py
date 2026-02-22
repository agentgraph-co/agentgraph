"""OpenClaw adapter — translates OpenClaw skill calls to AIP messages.

Maps OpenClaw skill invocations to AgentGraph internal API operations,
similar to how the MCP handler bridges MCP tool calls.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity


class OpenClawError(Exception):
    """Raised when an OpenClaw skill call fails."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


async def translate_skill_call(
    skill_name: str,
    arguments: dict[str, Any],
    entity: Entity,
    db: AsyncSession,
) -> dict[str, Any]:
    """Translate an OpenClaw skill call into an AgentGraph API operation.

    Args:
        skill_name: The OpenClaw skill name
        arguments: The skill arguments
        entity: The authenticated entity making the call
        db: Database session

    Returns:
        Skill result as a dict

    Raises:
        OpenClawError: If the skill call fails
    """
    handler = _SKILL_HANDLERS.get(skill_name)
    if handler is None:
        raise OpenClawError(
            "skill_not_found",
            f"Unknown OpenClaw skill: {skill_name}",
        )

    return await handler(arguments, entity, db)


async def _handle_read_feed(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    """Read the feed via OpenClaw skill."""
    from sqlalchemy import select

    from src.models import Post

    limit = min(args.get("limit", 20), 100)
    result = await db.execute(
        select(Post)
        .where(Post.is_hidden.is_(False))
        .order_by(Post.created_at.desc())
        .limit(limit)
    )
    posts = result.scalars().all()
    return {
        "posts": [
            {
                "id": str(p.id),
                "content": p.content,
                "author_id": str(p.author_entity_id),
                "vote_count": p.vote_count,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in posts
        ],
        "count": len(posts),
    }


async def _handle_create_post(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    """Create a post via OpenClaw skill."""
    import uuid

    from src.content_filter import check_content
    from src.models import Post

    content = args.get("content", "")
    if not content or len(content) > 10000:
        raise OpenClawError("invalid_content", "Content must be 1-10000 characters")

    filter_result = check_content(content)
    if not filter_result.is_clean:
        raise OpenClawError(
            "content_rejected",
            "Post rejected: " + ", ".join(filter_result.flags),
        )

    post = Post(
        id=uuid.uuid4(),
        author_entity_id=entity.id,
        content=content,
    )
    db.add(post)
    await db.flush()
    return {
        "id": str(post.id),
        "content": post.content,
        "author_id": str(entity.id),
    }


async def _handle_search_agents(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    """Search for agents via OpenClaw skill."""
    from sqlalchemy import select

    from src.models import EntityType
    from src.utils import like_pattern

    query = args.get("query", "")
    limit = min(args.get("limit", 20), 100)

    stmt = (
        select(Entity)
        .where(
            Entity.is_active.is_(True),
            Entity.type == EntityType.AGENT,
            Entity.display_name.ilike(like_pattern(query)),
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    entities = result.scalars().all()
    return {
        "agents": [
            {
                "id": str(e.id),
                "display_name": e.display_name,
                "type": e.type.value if e.type else None,
                "capabilities": e.capabilities or [],
            }
            for e in entities
        ],
        "count": len(entities),
    }


async def _handle_get_trust(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    """Get trust score via OpenClaw skill."""
    import uuid as uuid_mod

    from sqlalchemy import select

    from src.models import TrustScore

    target_id = args.get("entity_id")
    if not target_id:
        raise OpenClawError("missing_entity_id", "entity_id is required")

    try:
        target_uuid = uuid_mod.UUID(target_id)
    except ValueError:
        raise OpenClawError("invalid_entity_id", "entity_id must be a valid UUID")

    result = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == target_uuid)
    )
    if result is None:
        return {"entity_id": target_id, "score": None, "components": {}}

    return {
        "entity_id": target_id,
        "score": result.score,
        "components": result.components or {},
    }


async def _handle_follow_entity(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    """Follow an entity via OpenClaw skill."""
    import uuid as uuid_mod

    from sqlalchemy import select

    from src.models import EntityRelationship, RelationshipType

    target_id = args.get("target_id")
    if not target_id:
        raise OpenClawError("missing_target_id", "target_id is required")

    try:
        target_uuid = uuid_mod.UUID(target_id)
    except ValueError:
        raise OpenClawError("invalid_target_id", "target_id must be a valid UUID")

    if target_uuid == entity.id:
        raise OpenClawError("self_follow", "Cannot follow yourself")

    # Check target exists
    target = await db.get(Entity, target_uuid)
    if target is None or not target.is_active:
        raise OpenClawError("target_not_found", "Target entity not found")

    # Check if already following
    existing = await db.scalar(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id == entity.id,
            EntityRelationship.target_entity_id == target_uuid,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    if existing:
        return {"status": "already_following", "target_id": target_id}

    rel = EntityRelationship(
        id=uuid_mod.uuid4(),
        source_entity_id=entity.id,
        target_entity_id=target_uuid,
        type=RelationshipType.FOLLOW,
    )
    db.add(rel)
    await db.flush()
    return {"status": "following", "target_id": target_id}


# Map of OpenClaw skill names to handler functions
_SKILL_HANDLERS = {
    "read_feed": _handle_read_feed,
    "create_post": _handle_create_post,
    "search_agents": _handle_search_agents,
    "get_trust": _handle_get_trust,
    "follow_entity": _handle_follow_entity,
}


def get_supported_skills() -> list[str]:
    """Return list of supported OpenClaw skill names."""
    return list(_SKILL_HANDLERS.keys())
