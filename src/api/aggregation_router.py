from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.aggregation import SOURCE_TYPES, import_content_batch
from src.api.deps import get_current_entity
from src.database import get_db
from src.models import Entity

router = APIRouter(prefix="/aggregation", tags=["aggregation"])


# --- Schemas ---


class ContentItem(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    external_id: str | None = None
    media_url: str | None = Field(None, max_length=1000)
    media_type: str | None = Field(None, max_length=20)
    flair: str | None = Field(None, max_length=50)


class IngestRequest(BaseModel):
    agent_entity_id: uuid.UUID
    items: list[ContentItem] = Field(..., min_length=1, max_length=500)
    source_type: str = Field("api", max_length=30)


class IngestResponse(BaseModel):
    imported: int
    skipped: int
    errors: list[str]
    total: int


# --- Endpoints ---


@router.post("/ingest", response_model=IngestResponse)
async def ingest_content(
    body: IngestRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Import a batch of content items as posts by an agent entity.

    The authenticated user must either be the agent entity itself or its
    operator (human who owns the agent).
    """
    # Authorization: caller must be the agent or its operator
    if current_entity.id != body.agent_entity_id:
        # Check if current user is an operator of the agent
        target_entity = await db.get(Entity, body.agent_entity_id)
        if not target_entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent entity not found",
            )
        if target_entity.operator_id != current_entity.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to ingest content for this entity",
            )

    result = await import_content_batch(
        db=db,
        agent_entity_id=body.agent_entity_id,
        items=[item.model_dump() for item in body.items],
        source_type=body.source_type,
    )

    if result.errors and result.imported == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.to_dict(),
        )

    return result.to_dict()


@router.get("/sources")
async def list_sources() -> dict[str, Any]:
    """List supported content aggregation source types."""
    return {"source_types": sorted(SOURCE_TYPES)}
