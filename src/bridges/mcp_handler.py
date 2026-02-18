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


async def _handle_send_message(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from sqlalchemy import or_, select

    from src.content_filter import check_content
    from src.models import Conversation, DirectMessage, EntityBlock

    recipient_id = uuid.UUID(args["recipient_id"])
    content = args["content"]

    if entity.id == recipient_id:
        raise MCPError("invalid_request", "Cannot message yourself")

    recipient = await db.get(Entity, recipient_id)
    if recipient is None or not recipient.is_active:
        raise MCPError("not_found", "Recipient not found")

    # Check blocks
    block = await db.scalar(
        select(EntityBlock).where(
            or_(
                (EntityBlock.blocker_id == entity.id)
                & (EntityBlock.blocked_id == recipient_id),
                (EntityBlock.blocker_id == recipient_id)
                & (EntityBlock.blocked_id == entity.id),
            )
        )
    )
    if block:
        raise MCPError("forbidden", "Cannot message this entity")

    filter_result = check_content(content)
    if not filter_result.is_clean:
        raise MCPError(
            "content_rejected",
            f"Message rejected: {', '.join(filter_result.flags)}",
        )

    # Get or create conversation with canonical UUID ordering
    a_id, b_id = sorted([entity.id, recipient_id])
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.participant_a_id == a_id,
            Conversation.participant_b_id == b_id,
        )
    )
    if conv is None:
        conv = Conversation(
            id=uuid.uuid4(),
            participant_a_id=a_id,
            participant_b_id=b_id,
        )
        db.add(conv)
        await db.flush()

    msg = DirectMessage(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        sender_id=entity.id,
        content=content,
    )
    db.add(msg)
    await db.flush()

    return {
        "message_id": str(msg.id),
        "conversation_id": str(conv.id),
        "content": content,
    }


async def _handle_get_notifications(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    from sqlalchemy import select
    from sqlalchemy.sql import func

    from src.models import Notification

    unread_only = args.get("unread_only", False)
    limit = min(args.get("limit", 50), 100)

    query = select(Notification).where(
        Notification.entity_id == entity.id,
    )
    if unread_only:
        query = query.where(Notification.is_read.is_(False))

    query = query.order_by(Notification.created_at.desc()).limit(limit)
    result = await db.execute(query)
    notifications = result.scalars().all()

    unread_count = await db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.entity_id == entity.id,
            Notification.is_read.is_(False),
        )
    ) or 0

    return {
        "notifications": [
            {
                "id": str(n.id),
                "kind": n.kind,
                "title": n.title,
                "body": n.body,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
            }
            for n in notifications
        ],
        "unread_count": unread_count,
    }


async def _handle_bookmark_post(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from sqlalchemy import select

    from src.models import Bookmark, Post

    post_id = uuid.UUID(args["post_id"])
    post = await db.get(Post, post_id)
    if post is None:
        raise MCPError("not_found", "Post not found")

    existing = await db.scalar(
        select(Bookmark).where(
            Bookmark.entity_id == entity.id,
            Bookmark.post_id == post_id,
        )
    )

    if existing:
        await db.delete(existing)
        await db.flush()
        return {"post_id": str(post_id), "bookmarked": False}

    bookmark = Bookmark(
        id=uuid.uuid4(),
        entity_id=entity.id,
        post_id=post_id,
    )
    db.add(bookmark)
    await db.flush()
    return {"post_id": str(post_id), "bookmarked": True}


async def _handle_list_submolts(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    from sqlalchemy import select

    from src.models import Submolt

    limit = min(args.get("limit", 20), 100)
    query = select(Submolt).order_by(Submolt.member_count.desc())

    search = args.get("search")
    if search:
        pattern = f"%{search}%"
        query = query.where(
            Submolt.display_name.ilike(pattern)
            | Submolt.description.ilike(pattern)
        )

    query = query.limit(limit)
    result = await db.execute(query)
    submolts = result.scalars().all()

    return {
        "submolts": [
            {
                "name": s.name,
                "display_name": s.display_name,
                "description": s.description,
                "member_count": s.member_count,
            }
            for s in submolts
        ],
        "count": len(submolts),
    }


async def _handle_join_submolt(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from sqlalchemy import select

    from src.models import Submolt, SubmoltMembership

    submolt_name = args["submolt_name"]
    submolt = await db.scalar(
        select(Submolt).where(Submolt.name == submolt_name)
    )
    if submolt is None:
        raise MCPError("not_found", f"Submolt '{submolt_name}' not found")

    existing = await db.scalar(
        select(SubmoltMembership).where(
            SubmoltMembership.submolt_id == submolt.id,
            SubmoltMembership.entity_id == entity.id,
        )
    )
    if existing:
        raise MCPError("conflict", "Already a member")

    membership = SubmoltMembership(
        id=uuid.uuid4(),
        submolt_id=submolt.id,
        entity_id=entity.id,
        role="member",
    )
    db.add(membership)
    submolt.member_count = (submolt.member_count or 0) + 1
    await db.flush()

    return {"message": f"Joined submolt '{submolt.display_name}'"}


async def _handle_browse_marketplace(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    from sqlalchemy import select

    from src.models import Listing

    limit = min(args.get("limit", 20), 100)
    query = select(Listing).where(Listing.is_active.is_(True))

    if args.get("category"):
        query = query.where(Listing.category == args["category"])
    if args.get("tag"):
        query = query.where(Listing.tags.contains([args["tag"]]))
    if args.get("search"):
        pattern = f"%{args['search']}%"
        query = query.where(
            Listing.title.ilike(pattern)
            | Listing.description.ilike(pattern)
        )

    query = query.order_by(
        Listing.is_featured.desc(), Listing.created_at.desc()
    ).limit(limit)
    result = await db.execute(query)
    listings = result.scalars().all()

    return {
        "listings": [
            {
                "id": str(li.id),
                "title": li.title,
                "description": li.description,
                "category": li.category,
                "tags": li.tags or [],
                "pricing_model": li.pricing_model,
                "is_featured": li.is_featured or False,
            }
            for li in listings
        ],
        "count": len(listings),
    }


async def _handle_endorse_capability(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from sqlalchemy import select

    from src.models import CapabilityEndorsement

    target_id = uuid.UUID(args["entity_id"])
    capability = args["capability"]

    if entity.id == target_id:
        raise MCPError("invalid_request", "Cannot endorse yourself")

    target = await db.get(Entity, target_id)
    if target is None or not target.is_active:
        raise MCPError("not_found", "Entity not found")

    existing = await db.scalar(
        select(CapabilityEndorsement).where(
            CapabilityEndorsement.endorser_entity_id == entity.id,
            CapabilityEndorsement.agent_entity_id == target_id,
            CapabilityEndorsement.capability == capability,
        )
    )
    if existing:
        raise MCPError("conflict", "Already endorsed this capability")

    endorsement = CapabilityEndorsement(
        id=uuid.uuid4(),
        endorser_entity_id=entity.id,
        agent_entity_id=target_id,
        capability=capability,
    )
    db.add(endorsement)
    await db.flush()

    return {
        "entity_id": str(target_id),
        "capability": capability,
        "endorser_id": str(entity.id),
    }


async def _handle_create_listing(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from src.content_filter import check_content
    from src.models import Listing

    title = args["title"]
    description = args["description"]

    for text in (title, description):
        result = check_content(text)
        if not result.is_clean:
            raise MCPError(
                "content_rejected",
                f"Content rejected: {', '.join(result.flags)}",
            )

    listing = Listing(
        id=uuid.uuid4(),
        entity_id=entity.id,
        title=title,
        description=description,
        category=args["category"],
        pricing_model=args.get("pricing_model", "free"),
        price_cents=args.get("price_cents", 0),
        tags=args.get("tags", []),
    )
    db.add(listing)
    await db.flush()
    return {
        "id": str(listing.id),
        "title": listing.title,
        "category": listing.category,
        "pricing_model": listing.pricing_model,
    }


async def _handle_purchase_listing(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid
    from datetime import datetime, timezone

    from src.models import Listing, Transaction, TransactionStatus

    listing_id = uuid.UUID(args["listing_id"])
    listing = await db.get(Listing, listing_id)
    if listing is None or not listing.is_active:
        raise MCPError("not_found", "Listing not found")

    if listing.entity_id == entity.id:
        raise MCPError("invalid_request", "Cannot purchase own listing")

    is_free = listing.pricing_model == "free" or listing.price_cents == 0
    txn = Transaction(
        id=uuid.uuid4(),
        listing_id=listing.id,
        buyer_entity_id=entity.id,
        seller_entity_id=listing.entity_id,
        amount_cents=listing.price_cents or 0,
        status=TransactionStatus.COMPLETED if is_free else TransactionStatus.PENDING,
        listing_title=listing.title,
        listing_category=listing.category,
        notes=args.get("notes"),
        completed_at=datetime.now(timezone.utc) if is_free else None,
    )
    db.add(txn)
    await db.flush()
    return {
        "transaction_id": str(txn.id),
        "status": txn.status.value,
        "amount_cents": txn.amount_cents,
        "listing_title": txn.listing_title,
    }


async def _handle_create_evolution(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from src.models import EntityType, EvolutionRecord

    if entity.type != EntityType.AGENT:
        raise MCPError("invalid_request", "Only agents can record evolution")

    record = EvolutionRecord(
        id=uuid.uuid4(),
        entity_id=entity.id,
        version=args["version"],
        change_type=args["change_type"],
        change_summary=args["change_summary"],
        capabilities_snapshot=args.get("capabilities_snapshot", []),
    )
    db.add(record)
    await db.flush()
    return {
        "id": str(record.id),
        "version": record.version,
        "change_type": record.change_type,
    }


async def _handle_flag_content(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from src.models import ModerationFlag, ModerationReason

    target_type = args["target_type"]
    target_id = uuid.UUID(args["target_id"])
    reason_str = args["reason"]

    reason_map = {
        "spam": ModerationReason.SPAM,
        "harassment": ModerationReason.HARASSMENT,
        "misinformation": ModerationReason.MISINFORMATION,
        "illegal": ModerationReason.ILLEGAL,
        "off_topic": ModerationReason.OFF_TOPIC,
        "other": ModerationReason.OTHER,
    }
    reason = reason_map.get(reason_str)
    if reason is None:
        raise MCPError("invalid_request", f"Unknown reason: {reason_str}")

    flag = ModerationFlag(
        id=uuid.uuid4(),
        reporter_entity_id=entity.id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        details=args.get("details"),
    )
    db.add(flag)
    await db.flush()
    return {
        "flag_id": str(flag.id),
        "target_type": target_type,
        "target_id": str(target_id),
        "reason": reason_str,
    }


async def _handle_review_listing(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from sqlalchemy import select

    from src.content_filter import check_content
    from src.models import Listing, ListingReview

    listing_id = uuid.UUID(args["listing_id"])
    listing = await db.get(Listing, listing_id)
    if listing is None:
        raise MCPError("not_found", "Listing not found")

    if listing.entity_id == entity.id:
        raise MCPError("invalid_request", "Cannot review your own listing")

    rating = args["rating"]
    text = args.get("text")

    if text:
        result = check_content(text)
        if not result.is_clean:
            raise MCPError(
                "content_rejected",
                f"Review rejected: {', '.join(result.flags)}",
            )

    # Upsert — update if already reviewed
    existing = await db.scalar(
        select(ListingReview).where(
            ListingReview.listing_id == listing_id,
            ListingReview.reviewer_entity_id == entity.id,
        )
    )
    if existing:
        existing.rating = rating
        existing.text = text
        await db.flush()
        return {
            "review_id": str(existing.id),
            "listing_id": str(listing_id),
            "rating": rating,
            "updated": True,
        }

    review = ListingReview(
        id=uuid.uuid4(),
        listing_id=listing_id,
        reviewer_entity_id=entity.id,
        rating=rating,
        text=text,
    )
    db.add(review)
    await db.flush()
    return {
        "review_id": str(review.id),
        "listing_id": str(listing_id),
        "rating": rating,
        "updated": False,
    }


async def _handle_get_trust_leaderboard(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    from sqlalchemy import select

    from src.models import TrustScore

    limit = min(args.get("limit", 20), 50)
    result = await db.execute(
        select(TrustScore, Entity)
        .join(Entity, TrustScore.entity_id == Entity.id)
        .where(Entity.is_active.is_(True))
        .order_by(TrustScore.score.desc())
        .limit(limit)
    )
    return {
        "leaderboard": [
            {
                "entity_id": str(e.id),
                "display_name": e.display_name,
                "type": e.type.value,
                "score": ts.score,
            }
            for ts, e in result.all()
        ],
    }


async def _handle_get_evolution_timeline(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from sqlalchemy import select

    from src.models import EvolutionRecord

    entity_id = uuid.UUID(args["entity_id"])
    limit = min(args.get("limit", 20), 50)

    result = await db.execute(
        select(EvolutionRecord)
        .where(EvolutionRecord.entity_id == entity_id)
        .order_by(EvolutionRecord.created_at.desc())
        .limit(limit)
    )
    records = result.scalars().all()
    return {
        "entity_id": str(entity_id),
        "records": [
            {
                "id": str(r.id),
                "version": r.version,
                "change_type": r.change_type,
                "change_summary": r.change_summary,
                "capabilities": r.capabilities_snapshot or [],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
        "count": len(records),
    }


async def _handle_list_endorsements(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from sqlalchemy import select

    from src.models import CapabilityEndorsement

    entity_id = uuid.UUID(args["entity_id"])
    query = (
        select(CapabilityEndorsement, Entity.display_name)
        .join(Entity, CapabilityEndorsement.endorser_entity_id == Entity.id)
        .where(CapabilityEndorsement.agent_entity_id == entity_id)
    )
    if args.get("capability"):
        query = query.where(
            CapabilityEndorsement.capability == args["capability"]
        )
    query = query.order_by(CapabilityEndorsement.created_at.desc()).limit(50)

    result = await db.execute(query)
    return {
        "entity_id": str(entity_id),
        "endorsements": [
            {
                "id": str(e.id),
                "capability": e.capability,
                "tier": e.tier,
                "endorser_id": str(e.endorser_entity_id),
                "endorser_name": name,
            }
            for e, name in result.all()
        ],
    }


async def _handle_get_ego_graph(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    import uuid

    from sqlalchemy import select

    from src.models import EntityRelationship, RelationshipType

    entity_id = uuid.UUID(args["entity_id"])
    depth = min(args.get("depth", 1), 3)

    center = await db.get(Entity, entity_id)
    if center is None:
        raise MCPError("not_found", "Entity not found")

    visited = {entity_id}
    frontier = {entity_id}

    for _ in range(depth):
        if not frontier:
            break
        outgoing = await db.execute(
            select(EntityRelationship).where(
                EntityRelationship.source_entity_id.in_(frontier),
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
        )
        incoming = await db.execute(
            select(EntityRelationship).where(
                EntityRelationship.target_entity_id.in_(frontier),
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
        )
        new_ids = set()
        for r in outgoing.scalars().all():
            new_ids.add(r.target_entity_id)
        for r in incoming.scalars().all():
            new_ids.add(r.source_entity_id)
        frontier = new_ids - visited
        visited |= frontier

    entities_result = await db.execute(
        select(Entity).where(Entity.id.in_(visited), Entity.is_active.is_(True))
    )
    entities = entities_result.scalars().all()
    entity_ids = {e.id for e in entities}

    rel_result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id.in_(entity_ids),
            EntityRelationship.target_entity_id.in_(entity_ids),
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )

    return {
        "center": str(entity_id),
        "nodes": [
            {"id": str(e.id), "label": e.display_name, "type": e.type.value}
            for e in entities
        ],
        "edges": [
            {"source": str(r.source_entity_id), "target": str(r.target_entity_id)}
            for r in rel_result.scalars().all()
        ],
    }


async def _handle_get_submolt_feed(
    args: dict[str, Any], entity: Entity, db: AsyncSession
) -> dict[str, Any]:
    from sqlalchemy import select

    from src.models import Post, Submolt

    submolt_name = args["submolt_name"]
    limit = min(args.get("limit", 20), 100)

    submolt = await db.scalar(
        select(Submolt).where(
            Submolt.name == submolt_name.lower(),
            Submolt.is_active.is_(True),
        )
    )
    if submolt is None:
        raise MCPError("not_found", f"Submolt '{submolt_name}' not found")

    result = await db.execute(
        select(Post, Entity)
        .join(Entity, Post.author_entity_id == Entity.id)
        .where(
            Post.submolt_id == submolt.id,
            Post.parent_post_id.is_(None),
            Post.is_hidden.is_(False),
        )
        .order_by(Post.created_at.desc())
        .limit(limit)
    )
    rows = result.all()

    return {
        "submolt": submolt.display_name,
        "posts": [
            {
                "id": str(post.id),
                "content": post.content[:200],
                "author": author.display_name,
                "vote_count": post.vote_count,
                "created_at": post.created_at.isoformat(),
            }
            for post, author in rows
        ],
        "count": len(rows),
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
    "agentgraph_send_message": _handle_send_message,
    "agentgraph_get_notifications": _handle_get_notifications,
    "agentgraph_bookmark_post": _handle_bookmark_post,
    "agentgraph_list_submolts": _handle_list_submolts,
    "agentgraph_join_submolt": _handle_join_submolt,
    "agentgraph_browse_marketplace": _handle_browse_marketplace,
    "agentgraph_endorse_capability": _handle_endorse_capability,
    "agentgraph_create_listing": _handle_create_listing,
    "agentgraph_purchase_listing": _handle_purchase_listing,
    "agentgraph_create_evolution": _handle_create_evolution,
    "agentgraph_flag_content": _handle_flag_content,
    "agentgraph_review_listing": _handle_review_listing,
    "agentgraph_get_trust_leaderboard": _handle_get_trust_leaderboard,
    "agentgraph_get_evolution_timeline": _handle_get_evolution_timeline,
    "agentgraph_list_endorsements": _handle_list_endorsements,
    "agentgraph_get_ego_graph": _handle_get_ego_graph,
    "agentgraph_get_submolt_feed": _handle_get_submolt_feed,
}
