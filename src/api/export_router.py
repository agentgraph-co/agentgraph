"""Data export endpoints for entity portability.

Provides data export of an entity's profile, posts, relationships,
and trust data in a portable JSON format. Supports GDPR data
portability requirements.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.database import get_db
from src.models import (
    Entity,
    EntityRelationship,
    EvolutionRecord,
    Listing,
    Post,
    RelationshipType,
    TrustScore,
    Vote,
)

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/me")
async def export_my_data(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Export all data for the authenticated entity.

    Returns a comprehensive JSON package containing profile,
    posts, votes, relationships, trust score, and more.
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
            "parent_post_id": str(p.parent_post_id) if p.parent_post_id else None,
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

    return {
        "export_version": "1.0",
        "exported_at": current_entity.created_at.isoformat(),
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
    }
