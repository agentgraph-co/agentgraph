"""DID (Decentralized Identifier) document management endpoints.

Provides resolution and management of DID:web documents for entities.
DID documents contain public keys, service endpoints, and verification
methods following the W3C DID Core specification.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.database import get_db
from src.models import DIDDocument, Entity

router = APIRouter(prefix="/did", tags=["did"])


class ServiceEndpoint(BaseModel):
    id: str
    type: str
    serviceEndpoint: str  # noqa: N815 — W3C DID spec field name


class UpdateDIDRequest(BaseModel):
    service: list[ServiceEndpoint] | None = None


def _build_did_document(entity: Entity, did_doc: DIDDocument | None) -> dict:
    """Build a W3C DID document from entity + stored doc."""
    did = entity.did_web
    base_doc = {
        "@context": [
            "https://www.w3.org/ns/did/v1",
            "https://w3id.org/security/suites/jws-2020/v1",
        ],
        "id": did,
        "controller": did,
        "verificationMethod": [
            {
                "id": f"{did}#key-1",
                "type": "JsonWebKey2020",
                "controller": did,
            }
        ],
        "authentication": [f"{did}#key-1"],
        "service": [
            {
                "id": f"{did}#agentgraph",
                "type": "AgentGraphProfile",
                "serviceEndpoint": f"https://agentgraph.io/entities/{entity.id}",
            }
        ],
    }

    # Merge stored document data if exists
    if did_doc and did_doc.document:
        stored = did_doc.document
        if "service" in stored:
            base_doc["service"].extend(stored["service"])
        if did_doc.created_at:
            base_doc["created"] = did_doc.created_at.isoformat()
        if did_doc.updated_at:
            base_doc["updated"] = did_doc.updated_at.isoformat()

    return base_doc


@router.get("/resolve")
async def resolve_did(
    uri: str = Query(..., description="DID URI to resolve"),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a DID:web identifier to its DID document."""
    entity = await db.scalar(
        select(Entity).where(Entity.did_web == uri, Entity.is_active.is_(True))
    )

    if entity is None:
        raise HTTPException(status_code=404, detail="DID not found")

    did_doc = await db.scalar(
        select(DIDDocument).where(DIDDocument.entity_id == entity.id)
    )

    return _build_did_document(entity, did_doc)


@router.get("/entity/{entity_id}")
async def get_entity_did(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the DID document for an entity by ID."""
    entity = await db.get(Entity, entity_id)
    if entity is None or not entity.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    did_doc = await db.scalar(
        select(DIDDocument).where(DIDDocument.entity_id == entity.id)
    )

    return _build_did_document(entity, did_doc)


@router.patch("/entity/{entity_id}")
async def update_did_document(
    entity_id: uuid.UUID,
    body: UpdateDIDRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Update service endpoints on an entity's DID document. Owner only."""
    if current_entity.id != entity_id:
        raise HTTPException(status_code=403, detail="Can only update your own DID document")

    did_doc = await db.scalar(
        select(DIDDocument).where(DIDDocument.entity_id == entity_id)
    )

    document_data = {}
    if body.service is not None:
        document_data["service"] = [s.model_dump() for s in body.service]

    if did_doc is None:
        did_doc = DIDDocument(
            id=uuid.uuid4(),
            entity_id=entity_id,
            did_uri=current_entity.did_web,
            document=document_data,
        )
        db.add(did_doc)
    else:
        did_doc.document = (
            {**did_doc.document, **document_data}
            if did_doc.document
            else document_data
        )

    await db.flush()

    return _build_did_document(current_entity, did_doc)
