"""Cross-linking router for related content in AgentGraph.

Enables creation, retrieval, and deletion of cross-references between
content items (posts, entities, evolution records, listings).
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, require_not_frozen, require_not_quarantined
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import ContentLink, Entity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crosslinks", tags=["crosslinks"])

VALID_CONTENT_TYPES = {"post", "entity", "evolution_record", "listing"}
VALID_LINK_TYPES = {"mentions", "references", "related", "replies_about"}

# UUID regex pattern for detecting references in post content
_UUID_PATTERN = re.compile(
    r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
    re.IGNORECASE,
)
# @mention pattern (matches @display_name)
_MENTION_PATTERN = re.compile(r"@(\w+)")


# --- Schemas ---


class CreateCrosslinkRequest(BaseModel):
    source_type: str = Field(..., pattern="^(post|entity|evolution_record|listing)$")
    source_id: uuid.UUID
    target_type: str = Field(..., pattern="^(post|entity|evolution_record|listing)$")
    target_id: uuid.UUID
    link_type: str = Field(..., pattern="^(mentions|references|related|replies_about)$")


class CrosslinkResponse(BaseModel):
    id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    link_type: str
    created_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class CrosslinkListResponse(BaseModel):
    crosslinks: list[CrosslinkResponse]
    count: int


# --- Helper: auto-detect cross-links from post content ---


async def auto_detect_crosslinks(
    db: AsyncSession,
    post_id: uuid.UUID,
    content: str,
    author_id: uuid.UUID,
) -> list[ContentLink]:
    """Scan post content for @mentions and UUID references, auto-create cross-links.

    Returns the list of ContentLink objects created.
    """
    created_links: list[ContentLink] = []

    # 1. Detect @mentions -> link post to mentioned entities
    mentions = _MENTION_PATTERN.findall(content)
    if mentions:
        for mention_name in mentions:
            # Look up entity by display_name (case-insensitive)
            result = await db.execute(
                select(Entity).where(
                    Entity.display_name.ilike(mention_name),
                    Entity.is_active.is_(True),
                    Entity.id != author_id,
                ).limit(1)
            )
            entity = result.scalar_one_or_none()
            if entity is None:
                continue

            # Check for existing link to avoid duplicates
            existing = await db.execute(
                select(ContentLink).where(
                    ContentLink.source_type == "post",
                    ContentLink.source_id == post_id,
                    ContentLink.target_type == "entity",
                    ContentLink.target_id == entity.id,
                    ContentLink.link_type == "mentions",
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            link = ContentLink(
                id=uuid.uuid4(),
                source_type="post",
                source_id=post_id,
                target_type="entity",
                target_id=entity.id,
                link_type="mentions",
                created_by=author_id,
            )
            db.add(link)
            created_links.append(link)

    # 2. Detect UUID references in content -> link post to referenced content
    uuid_refs = _UUID_PATTERN.findall(content)
    if uuid_refs:
        from src.models import EvolutionRecord, Listing, Post

        for ref_str in uuid_refs:
            try:
                ref_id = uuid.UUID(ref_str)
            except ValueError:
                continue

            # Skip self-references
            if ref_id == post_id:
                continue

            # Check if UUID matches a post
            target_type = None
            post_obj = await db.get(Post, ref_id)
            if post_obj is not None:
                target_type = "post"
            else:
                entity_obj = await db.get(Entity, ref_id)
                if entity_obj is not None:
                    target_type = "entity"
                else:
                    evo_obj = await db.get(EvolutionRecord, ref_id)
                    if evo_obj is not None:
                        target_type = "evolution_record"
                    else:
                        listing_obj = await db.get(Listing, ref_id)
                        if listing_obj is not None:
                            target_type = "listing"

            if target_type is None:
                continue

            # Check for existing link
            existing = await db.execute(
                select(ContentLink).where(
                    ContentLink.source_type == "post",
                    ContentLink.source_id == post_id,
                    ContentLink.target_type == target_type,
                    ContentLink.target_id == ref_id,
                    ContentLink.link_type == "references",
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            link = ContentLink(
                id=uuid.uuid4(),
                source_type="post",
                source_id=post_id,
                target_type=target_type,
                target_id=ref_id,
                link_type="references",
                created_by=author_id,
            )
            db.add(link)
            created_links.append(link)

    if created_links:
        await db.flush()

    return created_links


# --- Endpoints ---


@router.post(
    "",
    response_model=CrosslinkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit_writes),
        Depends(require_not_quarantined),
        Depends(require_not_frozen),
    ],
)
async def create_crosslink(
    body: CreateCrosslinkRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Create a cross-link between two content items."""
    # Prevent self-links (same type + same id)
    if body.source_type == body.target_type and body.source_id == body.target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create a cross-link from content to itself",
        )

    # Check for duplicate
    existing = await db.execute(
        select(ContentLink).where(
            ContentLink.source_type == body.source_type,
            ContentLink.source_id == body.source_id,
            ContentLink.target_type == body.target_type,
            ContentLink.target_id == body.target_id,
            ContentLink.link_type == body.link_type,
        ).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This cross-link already exists",
        )

    link = ContentLink(
        id=uuid.uuid4(),
        source_type=body.source_type,
        source_id=body.source_id,
        target_type=body.target_type,
        target_id=body.target_id,
        link_type=body.link_type,
        created_by=current_entity.id,
    )
    db.add(link)
    await db.flush()

    await log_action(
        db,
        action="crosslink.created",
        entity_id=current_entity.id,
        resource_type="content_link",
        resource_id=link.id,
        details={
            "source_type": body.source_type,
            "source_id": str(body.source_id),
            "target_type": body.target_type,
            "target_id": str(body.target_id),
            "link_type": body.link_type,
        },
    )

    return link


@router.get(
    "/{content_type}/{content_id}",
    response_model=CrosslinkListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_crosslinks(
    content_type: str,
    content_id: uuid.UUID,
    link_type: str | None = Query(None, pattern="^(mentions|references|related|replies_about)$"),
    direction: str = Query("both", pattern="^(source|target|both)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get all cross-links for a piece of content (both directions by default)."""
    if content_type not in VALID_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid content type. Must be one of: "
                f"{', '.join(sorted(VALID_CONTENT_TYPES))}"
            ),
        )

    # Build direction filter
    if direction == "source":
        direction_filter = (
            (ContentLink.source_type == content_type)
            & (ContentLink.source_id == content_id)
        )
    elif direction == "target":
        direction_filter = (
            (ContentLink.target_type == content_type)
            & (ContentLink.target_id == content_id)
        )
    else:  # both
        direction_filter = or_(
            (ContentLink.source_type == content_type)
            & (ContentLink.source_id == content_id),
            (ContentLink.target_type == content_type)
            & (ContentLink.target_id == content_id),
        )

    query = select(ContentLink).where(direction_filter)

    if link_type is not None:
        query = query.where(ContentLink.link_type == link_type)

    query = query.order_by(ContentLink.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    links = result.scalars().all()

    return CrosslinkListResponse(
        crosslinks=[
            CrosslinkResponse(
                id=link.id,
                source_type=link.source_type,
                source_id=link.source_id,
                target_type=link.target_type,
                target_id=link.target_id,
                link_type=link.link_type,
                created_by=link.created_by,
                created_at=link.created_at,
            )
            for link in links
        ],
        count=len(links),
    )


@router.delete(
    "/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(rate_limit_writes),
        Depends(require_not_quarantined),
        Depends(require_not_frozen),
    ],
)
async def delete_crosslink(
    link_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Delete a cross-link. Only the creator or an admin can delete."""
    link = await db.get(ContentLink, link_id)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cross-link not found",
        )

    # Authorization: creator or admin only
    if link.created_by != current_entity.id and not current_entity.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the creator or an admin can delete this cross-link",
        )

    await log_action(
        db,
        action="crosslink.deleted",
        entity_id=current_entity.id,
        resource_type="content_link",
        resource_id=link.id,
        details={
            "source_type": link.source_type,
            "source_id": str(link.source_id),
            "target_type": link.target_type,
            "target_id": str(link.target_id),
            "link_type": link.link_type,
        },
    )

    await db.delete(link)
    await db.flush()
