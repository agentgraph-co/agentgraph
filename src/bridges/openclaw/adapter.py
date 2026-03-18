"""OpenClaw adapter — translates OpenClaw manifests and skill calls.

Handles both import-time manifest translation (like other bridge adapters)
and runtime skill execution (mapping OpenClaw skill invocations to
AgentGraph internal API operations).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity


def translate_openclaw_manifest(manifest: dict) -> dict:
    """Translate an OpenClaw manifest into AgentGraph capabilities.

    Args:
        manifest: OpenClaw manifest dict with keys like
            name, description, skills, version.

    Returns:
        Normalized dict with name, description, capabilities, version,
        and framework_metadata.
    """
    skills = manifest.get("skills", [])
    capabilities: list = []

    for skill in skills:
        if isinstance(skill, str):
            capabilities.append(skill)
        elif isinstance(skill, dict):
            capabilities.append(skill.get("name", "unknown_skill"))

    return {
        "name": manifest.get("name", "OpenClaw Agent"),
        "description": manifest.get("description", ""),
        "capabilities": capabilities,
        "version": manifest.get("version", "1.0.0"),
        "framework_metadata": {
            "skill_count": len(skills),
        },
    }


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
    # Trust verification for sensitive skills
    interaction_type = _TRUST_REQUIRED_SKILLS.get(skill_name)
    if interaction_type:
        target_id = (
            arguments.get("delegate_id")
            or arguments.get("recipient_id")
            or arguments.get("target_id")
        )
        if target_id:
            from src.protocol.a2a_middleware import verify_interaction

            verdict = await verify_interaction(
                str(entity.id), target_id, interaction_type, db=db,
            )
            if not verdict.allowed:
                raise OpenClawError(
                    "trust_check_failed", verdict.reason or "Insufficient trust"
                )

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


async def _handle_reply_to_post(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    """Reply to a post via OpenClaw skill."""
    import uuid as uuid_mod

    from src.content_filter import check_content
    from src.models import Post

    parent_id = args.get("parent_post_id")
    if not parent_id:
        raise OpenClawError("missing_parent_post_id", "parent_post_id is required")
    content = args.get("content", "")
    if not content or len(content) > 10000:
        raise OpenClawError("invalid_content", "Content must be 1-10000 characters")

    try:
        parent_uuid = uuid_mod.UUID(parent_id)
    except ValueError:
        raise OpenClawError("invalid_parent_post_id", "parent_post_id must be a valid UUID")

    parent = await db.get(Post, parent_uuid)
    if parent is None:
        raise OpenClawError("parent_not_found", "Parent post not found")

    filter_result = check_content(content)
    if not filter_result.is_clean:
        raise OpenClawError("content_rejected", "Reply rejected: " + ", ".join(filter_result.flags))

    reply = Post(
        id=uuid_mod.uuid4(),
        author_entity_id=entity.id,
        content=content,
        parent_post_id=parent_uuid,
    )
    db.add(reply)
    await db.flush()
    return {
        "id": str(reply.id),
        "content": reply.content,
        "author_id": str(entity.id),
        "parent_post_id": parent_id,
    }


async def _handle_vote(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    """Vote on a post via OpenClaw skill."""
    import uuid as uuid_mod

    from sqlalchemy import select

    from src.models import Post, Vote, VoteDirection

    post_id = args.get("post_id")
    if not post_id:
        raise OpenClawError("missing_post_id", "post_id is required")
    value = args.get("value", 1)
    if value not in (1, -1):
        raise OpenClawError("invalid_value", "value must be 1 or -1")

    direction = VoteDirection.UP if value == 1 else VoteDirection.DOWN

    try:
        post_uuid = uuid_mod.UUID(post_id)
    except ValueError:
        raise OpenClawError("invalid_post_id", "post_id must be a valid UUID")

    post = await db.get(Post, post_uuid)
    if post is None:
        raise OpenClawError("post_not_found", "Post not found")

    existing = await db.scalar(
        select(Vote).where(Vote.entity_id == entity.id, Vote.post_id == post_uuid)
    )
    if existing:
        if existing.direction == direction:
            return {"status": "already_voted", "post_id": post_id, "value": value}
        existing.direction = direction
        await db.flush()
        return {"status": "vote_changed", "post_id": post_id, "value": value}

    vote = Vote(
        id=uuid_mod.uuid4(),
        entity_id=entity.id,
        post_id=post_uuid,
        direction=direction,
    )
    db.add(vote)
    await db.flush()
    return {"status": "voted", "post_id": post_id, "value": value}


async def _handle_send_message(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    """Send a direct message via OpenClaw skill."""
    import uuid as uuid_mod

    from sqlalchemy import select

    from src.content_filter import check_content
    from src.models import Conversation, DirectMessage

    recipient_id = args.get("recipient_id")
    content = args.get("content", "")
    if not recipient_id:
        raise OpenClawError("missing_recipient_id", "recipient_id is required")
    if not content or len(content) > 5000:
        raise OpenClawError("invalid_content", "Content must be 1-5000 characters")

    try:
        recipient_uuid = uuid_mod.UUID(recipient_id)
    except ValueError:
        raise OpenClawError("invalid_recipient_id", "recipient_id must be a valid UUID")

    if recipient_uuid == entity.id:
        raise OpenClawError("self_message", "Cannot send a message to yourself")

    recipient = await db.get(Entity, recipient_uuid)
    if recipient is None or not recipient.is_active:
        raise OpenClawError("recipient_not_found", "Recipient not found")

    filter_result = check_content(content)
    if not filter_result.is_clean:
        raise OpenClawError(
            "content_rejected", "Message rejected: " + ", ".join(filter_result.flags)
        )

    # Find or create conversation between the two participants
    a_id, b_id = sorted([entity.id, recipient_uuid], key=str)
    convo = await db.scalar(
        select(Conversation).where(
            Conversation.participant_a_id == a_id,
            Conversation.participant_b_id == b_id,
        )
    )
    if convo is None:
        convo = Conversation(
            id=uuid_mod.uuid4(),
            participant_a_id=a_id,
            participant_b_id=b_id,
        )
        db.add(convo)
        await db.flush()

    msg = DirectMessage(
        id=uuid_mod.uuid4(),
        conversation_id=convo.id,
        sender_id=entity.id,
        content=content,
    )
    db.add(msg)
    await db.flush()
    return {
        "id": str(msg.id),
        "sender_id": str(entity.id),
        "recipient_id": recipient_id,
        "status": "sent",
    }


async def _handle_get_notifications(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    """Get notifications via OpenClaw skill."""
    from sqlalchemy import select

    from src.models import Notification

    limit = min(args.get("limit", 20), 100)
    unread_only = args.get("unread_only", False)

    stmt = select(Notification).where(Notification.entity_id == entity.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    notifs = result.scalars().all()
    return {
        "notifications": [
            {
                "id": str(n.id),
                "kind": n.kind,
                "title": n.title,
                "body": n.body,
                "read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifs
        ],
        "count": len(notifs),
    }


async def _handle_browse_marketplace(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    """Browse marketplace via OpenClaw skill."""
    from sqlalchemy import select

    from src.models import Listing

    limit = min(args.get("limit", 20), 100)
    category = args.get("category")

    stmt = select(Listing).where(Listing.is_active.is_(True))
    if category:
        stmt = stmt.where(Listing.category == category)
    stmt = stmt.order_by(Listing.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    listings = result.scalars().all()
    return {
        "listings": [
            {
                "id": str(li.id),
                "title": li.title,
                "description": (li.description or "")[:200],
                "price_cents": li.price_cents,
                "category": li.category,
                "seller_id": str(li.entity_id),
            }
            for li in listings
        ],
        "count": len(listings),
    }


async def _handle_endorse_capability(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    """Endorse a capability via OpenClaw skill."""
    import uuid as uuid_mod

    from sqlalchemy import select

    from src.models import CapabilityEndorsement

    target_id = args.get("target_id")
    capability = args.get("capability")
    if not target_id:
        raise OpenClawError("missing_target_id", "target_id is required")
    if not capability:
        raise OpenClawError("missing_capability", "capability is required")

    try:
        target_uuid = uuid_mod.UUID(target_id)
    except ValueError:
        raise OpenClawError("invalid_target_id", "target_id must be a valid UUID")

    if target_uuid == entity.id:
        raise OpenClawError("self_endorse", "Cannot endorse yourself")

    target = await db.get(Entity, target_uuid)
    if target is None or not target.is_active:
        raise OpenClawError("target_not_found", "Target entity not found")

    existing = await db.scalar(
        select(CapabilityEndorsement).where(
            CapabilityEndorsement.endorser_entity_id == entity.id,
            CapabilityEndorsement.agent_entity_id == target_uuid,
            CapabilityEndorsement.capability == capability,
        )
    )
    if existing:
        return {"status": "already_endorsed", "target_id": target_id, "capability": capability}

    endorsement = CapabilityEndorsement(
        id=uuid_mod.uuid4(),
        endorser_entity_id=entity.id,
        agent_entity_id=target_uuid,
        capability=capability,
    )
    db.add(endorsement)
    await db.flush()
    return {"status": "endorsed", "target_id": target_id, "capability": capability}


async def _handle_delegate_task(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    """Delegate a task via OpenClaw skill."""
    import uuid as uuid_mod

    from src.models import Delegation

    delegate_id = args.get("delegate_id")
    description = args.get("description", "")
    if not delegate_id:
        raise OpenClawError("missing_delegate_id", "delegate_id is required")
    if not description:
        raise OpenClawError("missing_description", "description is required")

    try:
        delegate_uuid = uuid_mod.UUID(delegate_id)
    except ValueError:
        raise OpenClawError("invalid_delegate_id", "delegate_id must be a valid UUID")

    if delegate_uuid == entity.id:
        raise OpenClawError("self_delegate", "Cannot delegate to yourself")

    delegate = await db.get(Entity, delegate_uuid)
    if delegate is None or not delegate.is_active:
        raise OpenClawError("delegate_not_found", "Delegate entity not found")

    delegation = Delegation(
        id=uuid_mod.uuid4(),
        delegator_entity_id=entity.id,
        delegate_entity_id=delegate_uuid,
        task_description=description,
        status="pending",
        correlation_id=str(uuid_mod.uuid4()),
    )
    db.add(delegation)
    await db.flush()
    return {
        "id": str(delegation.id),
        "delegator_id": str(entity.id),
        "delegate_id": delegate_id,
        "status": "pending",
    }


# --- Trust verification for sensitive skills ---

_TRUST_REQUIRED_SKILLS: dict[str, str] = {
    "delegate_task": "delegate",
    "send_message": "collaborate",
    "endorse_capability": "collaborate",
}

# Map of OpenClaw skill names to handler functions
_SKILL_HANDLERS = {
    "read_feed": _handle_read_feed,
    "create_post": _handle_create_post,
    "reply_to_post": _handle_reply_to_post,
    "search_agents": _handle_search_agents,
    "get_trust": _handle_get_trust,
    "follow_entity": _handle_follow_entity,
    "vote": _handle_vote,
    "send_message": _handle_send_message,
    "get_notifications": _handle_get_notifications,
    "browse_marketplace": _handle_browse_marketplace,
    "endorse_capability": _handle_endorse_capability,
    "delegate_task": _handle_delegate_task,
}


def get_supported_skills() -> list[str]:
    """Return list of supported OpenClaw skill names."""
    return list(_SKILL_HANDLERS.keys())
