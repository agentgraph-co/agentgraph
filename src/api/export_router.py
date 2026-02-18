"""Data export endpoints for entity portability.

Provides data export of an entity's profile, posts, relationships,
and trust data in a portable JSON format. Supports GDPR data
portability requirements.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.models import (
    AuditLog,
    Bookmark,
    CapabilityEndorsement,
    Conversation,
    DirectMessage,
    Entity,
    EntityBlock,
    EntityRelationship,
    EvolutionRecord,
    Listing,
    Notification,
    Post,
    RelationshipType,
    Review,
    TrustScore,
    Vote,
)

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/me", dependencies=[Depends(rate_limit_reads)])
async def export_my_data(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Export all data for the authenticated entity.

    Returns a comprehensive JSON package containing profile,
    posts, votes, relationships, trust score, DMs, bookmarks,
    notifications, endorsements, reviews, blocks, and audit log.
    Useful for data portability and GDPR compliance.
    """
    entity_id = current_entity.id

    # Profile data
    profile = {
        "id": str(entity_id),
        "type": current_entity.type.value,
        "display_name": current_entity.display_name,
        "email": current_entity.email,
        "email_verified": current_entity.email_verified,
        "bio_markdown": current_entity.bio_markdown or "",
        "did_web": current_entity.did_web,
        "is_active": current_entity.is_active,
        "created_at": current_entity.created_at.isoformat(),
    }

    # Posts
    posts_result = await db.execute(
        select(Post)
        .where(Post.author_entity_id == entity_id)
        .order_by(Post.created_at.desc())
    )
    posts = [
        {
            "id": str(p.id),
            "content": p.content,
            "parent_post_id": (
                str(p.parent_post_id) if p.parent_post_id else None
            ),
            "submolt_id": str(p.submolt_id) if p.submolt_id else None,
            "vote_count": p.vote_count,
            "created_at": p.created_at.isoformat(),
        }
        for p in posts_result.scalars().all()
    ]

    # Votes
    votes_result = await db.execute(
        select(Vote).where(Vote.entity_id == entity_id)
    )
    votes = [
        {
            "post_id": str(v.post_id),
            "direction": v.direction.value,
            "created_at": v.created_at.isoformat(),
        }
        for v in votes_result.scalars().all()
    ]

    # Following
    following_result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    following = [
        str(r.target_entity_id)
        for r in following_result.scalars().all()
    ]

    # Followers
    followers_result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.target_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    followers = [
        str(r.source_entity_id)
        for r in followers_result.scalars().all()
    ]

    # Trust score
    ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    trust = None
    if ts:
        trust = {
            "score": ts.score,
            "components": ts.components,
            "computed_at": ts.computed_at.isoformat(),
        }

    # Evolution records (agents only)
    evolution = []
    if current_entity.type.value == "agent":
        evo_result = await db.execute(
            select(EvolutionRecord)
            .where(EvolutionRecord.entity_id == entity_id)
            .order_by(EvolutionRecord.created_at.asc())
        )
        evolution = [
            {
                "version": e.version,
                "change_type": e.change_type,
                "change_summary": e.change_summary,
                "capabilities_snapshot": e.capabilities_snapshot or [],
                "created_at": e.created_at.isoformat(),
            }
            for e in evo_result.scalars().all()
        ]

    # Listings
    listings_result = await db.execute(
        select(Listing).where(Listing.entity_id == entity_id)
    )
    listings = [
        {
            "id": str(item.id),
            "title": item.title,
            "description": item.description,
            "category": item.category,
            "pricing_model": item.pricing_model,
            "price_cents": item.price_cents,
            "is_active": item.is_active,
            "created_at": item.created_at.isoformat(),
        }
        for item in listings_result.scalars().all()
    ]

    # Bookmarks
    bookmarks_result = await db.execute(
        select(Bookmark).where(Bookmark.entity_id == entity_id)
    )
    bookmarks = [
        {
            "post_id": str(b.post_id),
            "created_at": b.created_at.isoformat(),
        }
        for b in bookmarks_result.scalars().all()
    ]

    # Notifications
    notif_result = await db.execute(
        select(Notification)
        .where(Notification.entity_id == entity_id)
        .order_by(Notification.created_at.desc())
    )
    notifications = [
        {
            "kind": n.kind,
            "title": n.title,
            "body": n.body,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat(),
        }
        for n in notif_result.scalars().all()
    ]

    # Direct messages
    conv_result = await db.execute(
        select(Conversation).where(
            or_(
                Conversation.participant_a_id == entity_id,
                Conversation.participant_b_id == entity_id,
            )
        )
    )
    conversations = conv_result.scalars().all()
    dms = []
    for conv in conversations:
        other_id = (
            conv.participant_b_id
            if conv.participant_a_id == entity_id
            else conv.participant_a_id
        )
        msg_result = await db.execute(
            select(DirectMessage)
            .where(DirectMessage.conversation_id == conv.id)
            .order_by(DirectMessage.created_at.asc())
        )
        for msg in msg_result.scalars().all():
            dms.append({
                "conversation_with": str(other_id),
                "sender_id": str(msg.sender_id),
                "content": msg.content,
                "is_read": msg.is_read,
                "created_at": msg.created_at.isoformat(),
            })

    # Endorsements given
    endorse_result = await db.execute(
        select(CapabilityEndorsement).where(
            CapabilityEndorsement.endorser_entity_id == entity_id,
        )
    )
    endorsements_given = [
        {
            "agent_id": str(e.agent_entity_id),
            "capability": e.capability,
            "tier": e.tier,
            "comment": e.comment,
            "created_at": e.created_at.isoformat(),
        }
        for e in endorse_result.scalars().all()
    ]

    # Reviews given
    review_result = await db.execute(
        select(Review).where(Review.reviewer_entity_id == entity_id)
    )
    reviews_given = [
        {
            "target_id": str(r.target_entity_id),
            "rating": r.rating,
            "text": r.text,
            "created_at": r.created_at.isoformat(),
        }
        for r in review_result.scalars().all()
    ]

    # Blocked entities
    block_result = await db.execute(
        select(EntityBlock).where(EntityBlock.blocker_id == entity_id)
    )
    blocked = [
        str(b.blocked_id) for b in block_result.scalars().all()
    ]

    # Audit log
    audit_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.entity_id == entity_id)
        .order_by(AuditLog.created_at.desc())
        .limit(500)
    )
    audit_log = [
        {
            "action": a.action,
            "ip_address": a.ip_address,
            "created_at": a.created_at.isoformat(),
        }
        for a in audit_result.scalars().all()
    ]

    return {
        "export_version": "1.1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "posts": posts,
        "post_count": len(posts),
        "votes": votes,
        "vote_count": len(votes),
        "following": following,
        "following_count": len(following),
        "followers": followers,
        "follower_count": len(followers),
        "trust_score": trust,
        "evolution_records": evolution,
        "listings": listings,
        "bookmarks": bookmarks,
        "notifications": notifications,
        "direct_messages": dms,
        "endorsements_given": endorsements_given,
        "reviews_given": reviews_given,
        "blocked_entities": blocked,
        "audit_log": audit_log,
    }
