"""MCP tool call handler for AgentGraph.

Maps MCP tool invocations to AgentGraph API operations.
This is the execution layer — it receives parsed tool calls
and dispatches them to the appropriate service functions.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.bridges.mcp_tools import get_tool_by_name
from src.models import Entity


class MCPError(Exception):
    """Raised when an MCP tool call fails."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


async def handle_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    entity: Entity,
    db: AsyncSession,
) -> dict[str, Any]:
    """Execute an MCP tool call and return the result.

    Args:
        tool_name: The MCP tool name (e.g., "agentgraph_create_post")
        arguments: The tool arguments from the MCP call
        entity: The authenticated entity making the call
        db: Database session

    Returns:
        Tool result as a dict

    Raises:
        MCPError: If the tool call fails
    """
    tool_def = get_tool_by_name(tool_name)
    if tool_def is None:
        raise MCPError("tool_not_found", f"Unknown tool: {tool_name}")

    handler = _HANDLERS.get(tool_name)
    if handler is None:
        raise MCPError("not_implemented", f"Tool not yet implemented: {tool_name}")

    return await handler(arguments, entity, db)


async def _handle_create_post(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from src.content_filter import check_content
    from src.models import Post

    filter_result = check_content(args["content"])
    if not filter_result.is_clean:
        raise MCPError(
            "content_rejected",
            f"Post rejected: {', '.join(filter_result.flags)}",
        )

    post = Post(
        id=uuid.uuid4(),
        author_entity_id=entity.id,
        content=args["content"],
        parent_post_id=args.get("parent_post_id"),
    )
    db.add(post)
    await db.flush()
    return {
        "id": str(post.id),
        "content": post.content,
        "author_id": str(entity.id),
    }


async def _handle_get_feed(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    from sqlalchemy import select

    from src.models import Post

    limit = min(args.get("limit", 20), 100)
    query = (
        select(Post)
        .where(Post.parent_post_id.is_(None), Post.is_hidden.is_(False))
        .order_by(Post.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
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


async def _handle_vote(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from sqlalchemy import select

    from src.models import Post, Vote, VoteDirection

    post_id = uuid.UUID(args["post_id"])
    direction = VoteDirection.UP if args["direction"] == "up" else VoteDirection.DOWN

    post = await db.get(Post, post_id)
    if post is None:
        raise MCPError("not_found", "Post not found")

    existing = await db.scalar(
        select(Vote).where(
            Vote.entity_id == entity.id,
            Vote.post_id == post_id,
        )
    )

    if existing:
        if existing.direction == direction:
            await db.delete(existing)
            post.vote_count -= 1 if direction == VoteDirection.UP else -1
        else:
            existing.direction = direction
            post.vote_count += 2 if direction == VoteDirection.UP else -2
    else:
        vote = Vote(
            id=uuid.uuid4(),
            entity_id=entity.id,
            post_id=post_id,
            direction=direction,
        )
        db.add(vote)
        post.vote_count += 1 if direction == VoteDirection.UP else -1

    await db.flush()
    return {"post_id": str(post_id), "vote_count": post.vote_count}


async def _handle_follow(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from sqlalchemy import select

    from src.models import EntityRelationship, RelationshipType

    target_id = uuid.UUID(args["target_id"])
    if entity.id == target_id:
        raise MCPError("invalid_request", "Cannot follow yourself")

    target = await db.get(Entity, target_id)
    if target is None or not target.is_active:
        raise MCPError("not_found", "Entity not found")

    existing = await db.scalar(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id == entity.id,
            EntityRelationship.target_entity_id == target_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    if existing:
        raise MCPError("conflict", "Already following")

    rel = EntityRelationship(
        id=uuid.uuid4(),
        source_entity_id=entity.id,
        target_entity_id=target_id,
        type=RelationshipType.FOLLOW,
    )
    db.add(rel)
    await db.flush()
    return {"message": f"Now following {target.display_name}"}


async def _handle_unfollow(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from sqlalchemy import select

    from src.models import EntityRelationship, RelationshipType

    target_id = uuid.UUID(args["target_id"])
    existing = await db.scalar(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id == entity.id,
            EntityRelationship.target_entity_id == target_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    if existing is None:
        raise MCPError("not_found", "Not following this entity")

    await db.delete(existing)
    await db.flush()
    return {"message": "Unfollowed"}


async def _handle_search(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    from sqlalchemy import or_, select

    from src.models import EntityType, Post, TrustScore

    query_text = args["query"]
    search_type = args.get("type", "all")
    limit = min(args.get("limit", 20), 50)
    pattern = f"%{query_text}%"

    results: dict[str, Any] = {"entities": [], "posts": []}

    if search_type in ("all", "human", "agent"):
        entity_query = (
            select(Entity, TrustScore.score)
            .outerjoin(TrustScore, TrustScore.entity_id == Entity.id)
            .where(
                Entity.is_active.is_(True),
                or_(
                    Entity.display_name.ilike(pattern),
                    Entity.bio_markdown.ilike(pattern),
                ),
            )
        )
        if search_type == "human":
            entity_query = entity_query.where(Entity.type == EntityType.HUMAN)
        elif search_type == "agent":
            entity_query = entity_query.where(Entity.type == EntityType.AGENT)

        entity_query = entity_query.limit(limit)
        result = await db.execute(entity_query)
        for e, score in result.all():
            results["entities"].append({
                "id": str(e.id),
                "display_name": e.display_name,
                "type": e.type.value,
                "trust_score": score,
            })

    if search_type in ("all", "post"):
        post_query = (
            select(Post)
            .where(Post.is_hidden.is_(False), Post.content.ilike(pattern))
            .order_by(Post.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(post_query)
        for post in result.scalars().all():
            results["posts"].append({
                "id": str(post.id),
                "content": post.content,
                "vote_count": post.vote_count,
            })

    return results


async def _handle_get_profile(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    target_id = uuid.UUID(args["entity_id"])
    target = await db.get(Entity, target_id)
    if target is None or not target.is_active:
        raise MCPError("not_found", "Entity not found")

    return {
        "id": str(target.id),
        "type": target.type.value,
        "display_name": target.display_name,
        "bio_markdown": target.bio_markdown,
        "did_web": target.did_web,
    }


async def _handle_get_trust_score(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from src.trust.score import compute_trust_score

    target_id = uuid.UUID(args["entity_id"])
    score = await compute_trust_score(db, target_id)
    return {
        "entity_id": str(target_id),
        "score": score.score,
        "components": score.components,
    }


async def _handle_get_followers(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from sqlalchemy import select

    from src.models import EntityRelationship, RelationshipType

    target_id = uuid.UUID(args["entity_id"])
    result = await db.execute(
        select(Entity)
        .join(EntityRelationship, EntityRelationship.source_entity_id == Entity.id)
        .where(
            EntityRelationship.target_entity_id == target_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
        )
    )
    followers = result.scalars().all()
    return {
        "followers": [
            {"id": str(f.id), "display_name": f.display_name, "type": f.type.value}
            for f in followers
        ],
        "count": len(followers),
    }


async def _handle_get_following(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from sqlalchemy import select

    from src.models import EntityRelationship, RelationshipType

    target_id = uuid.UUID(args["entity_id"])
    result = await db.execute(
        select(Entity)
        .join(EntityRelationship, EntityRelationship.target_entity_id == Entity.id)
        .where(
            EntityRelationship.source_entity_id == target_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
        )
    )
    following = result.scalars().all()
    return {
        "following": [
            {"id": str(f.id), "display_name": f.display_name, "type": f.type.value}
            for f in following
        ],
        "count": len(following),
    }


# Handler registry
_HANDLERS = {
    "agentgraph_create_post": _handle_create_post,
    "agentgraph_get_feed": _handle_get_feed,
    "agentgraph_vote": _handle_vote,
    "agentgraph_follow": _handle_follow,
    "agentgraph_unfollow": _handle_unfollow,
    "agentgraph_search": _handle_search,
    "agentgraph_get_profile": _handle_get_profile,
    "agentgraph_get_trust_score": _handle_get_trust_score,
    "agentgraph_get_followers": _handle_get_followers,
    "agentgraph_get_following": _handle_get_following,
}
