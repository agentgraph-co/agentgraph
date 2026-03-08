from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import (
    Entity,
    FormalAttestation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attestations", tags=["attestations"])

VALID_ATTESTATION_TYPES = {
    "identity_verified",
    "capability_certified",
    "security_audited",
    "operator_verified",
    "community_endorsed",
}

ATTESTATION_TYPE_DESCRIPTIONS = {
    "identity_verified": "KYC/identity check passed",
    "capability_certified": "Capability has been tested and certified",
    "security_audited": "Security audit passed",
    "operator_verified": "Agent's operator has been verified",
    "community_endorsed": "Community endorsement",
}


# --- Schemas ---


class CreateAttestationRequest(BaseModel):
    subject_entity_id: uuid.UUID
    attestation_type: str = Field(
        ...,
        pattern=r"^(identity_verified|capability_certified|security_audited|operator_verified|community_endorsed)$",
    )
    evidence: str | None = Field(None, max_length=5000)
    expires_at: datetime | None = None


class AttestationResponse(BaseModel):
    id: uuid.UUID
    issuer_entity_id: uuid.UUID
    issuer_display_name: str
    subject_entity_id: uuid.UUID
    subject_display_name: str
    attestation_type: str
    evidence: str | None
    expires_at: datetime | None
    is_revoked: bool
    revoked_at: datetime | None
    is_expired: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AttestationListResponse(BaseModel):
    attestations: list[AttestationResponse]
    total: int


class AttestationTypeResponse(BaseModel):
    attestation_type: str
    description: str


class AttestationTypesListResponse(BaseModel):
    types: list[AttestationTypeResponse]


class RevokeResponse(BaseModel):
    message: str
    attestation_id: uuid.UUID
    revoked_at: datetime


# --- Helper ---


def _is_expired(att: FormalAttestation) -> bool:
    """Check if an attestation has expired."""
    if att.expires_at is None:
        return False
    return att.expires_at < datetime.now(timezone.utc)


def _build_response(
    att: FormalAttestation,
    issuer_name: str,
    subject_name: str,
) -> AttestationResponse:
    return AttestationResponse(
        id=att.id,
        issuer_entity_id=att.issuer_entity_id,
        issuer_display_name=issuer_name,
        subject_entity_id=att.subject_entity_id,
        subject_display_name=subject_name,
        attestation_type=att.attestation_type,
        evidence=att.evidence,
        expires_at=att.expires_at,
        is_revoked=att.is_revoked,
        revoked_at=att.revoked_at,
        is_expired=_is_expired(att),
        created_at=att.created_at,
    )


# --- Endpoints ---


@router.get(
    "/types",
    response_model=AttestationTypesListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_attestation_types():
    """List all available formal attestation types with descriptions."""
    types = [
        AttestationTypeResponse(
            attestation_type=att_type,
            description=ATTESTATION_TYPE_DESCRIPTIONS[att_type],
        )
        for att_type in sorted(VALID_ATTESTATION_TYPES)
    ]
    return AttestationTypesListResponse(types=types)


@router.post(
    "",
    response_model=AttestationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_writes)],
)
async def create_attestation(
    body: CreateAttestationRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Create a formal attestation about another entity."""
    # PROVISIONAL DID restriction: cannot issue attestations
    if current_entity.is_provisional:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Provisional DIDs cannot issue attestations. "
            "Upgrade to FULL status first.",
        )

    # Cannot self-attest
    if current_entity.id == body.subject_entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot attest for yourself",
        )

    # Validate subject exists and is active
    subject = await db.get(Entity, body.subject_entity_id)
    if subject is None or not subject.is_active:
        raise HTTPException(status_code=404, detail="Subject entity not found")

    # Validate attestation type
    if body.attestation_type not in VALID_ATTESTATION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid attestation_type. Must be one of: "
            f"{', '.join(sorted(VALID_ATTESTATION_TYPES))}",
        )

    # Content filter on evidence
    if body.evidence:
        from src.content_filter import check_content, sanitize_html

        filter_result = check_content(body.evidence)
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Evidence text rejected: {', '.join(filter_result.flags)}",
            )
        body.evidence = sanitize_html(body.evidence)

    # Check for duplicate (same issuer, subject, type)
    existing = await db.scalar(
        select(FormalAttestation).where(
            FormalAttestation.issuer_entity_id == current_entity.id,
            FormalAttestation.subject_entity_id == body.subject_entity_id,
            FormalAttestation.attestation_type == body.attestation_type,
        )
    )
    if existing:
        if not existing.is_revoked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have an active attestation of this type for this entity",
            )
        # Remove revoked attestation so a fresh one can be issued
        await db.delete(existing)
        await db.flush()

    attestation = FormalAttestation(
        id=uuid.uuid4(),
        issuer_entity_id=current_entity.id,
        subject_entity_id=body.subject_entity_id,
        attestation_type=body.attestation_type,
        evidence=body.evidence,
        expires_at=body.expires_at,
    )
    db.add(attestation)
    await db.flush()

    await log_action(
        db,
        action="formal_attestation.create",
        entity_id=current_entity.id,
        resource_type="formal_attestation",
        resource_id=attestation.id,
        details={
            "subject_entity_id": str(body.subject_entity_id),
            "attestation_type": body.attestation_type,
        },
    )

    # Dispatch webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "formal_attestation.created", {
            "attestation_id": str(attestation.id),
            "issuer_id": str(current_entity.id),
            "subject_id": str(body.subject_entity_id),
            "type": body.attestation_type,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # Send notification to subject
    try:
        from src.api.notification_router import create_notification

        await create_notification(
            db,
            entity_id=body.subject_entity_id,
            kind="attestation",
            title="New formal attestation",
            body=(
                f"{current_entity.display_name} issued a "
                f"'{body.attestation_type}' attestation about you"
            ),
            reference_id=str(attestation.id),
        )
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # Auto-promote PROVISIONAL DID if criteria now met
    if subject.is_provisional:
        try:
            from src.api.did_router import check_auto_promotion, promote_did_to_full
            from src.models import DIDDocument, DIDStatus

            reason = await check_auto_promotion(db, subject)
            if reason:
                did_doc = await db.scalar(
                    select(DIDDocument).where(
                        DIDDocument.entity_id == subject.id
                    )
                )
                if did_doc and did_doc.did_status == DIDStatus.PROVISIONAL:
                    await promote_did_to_full(db, did_doc, reason=reason)
                    logger.info(
                        "Auto-promoted DID %s to FULL: %s",
                        did_doc.did_uri,
                        reason,
                    )
        except Exception:
            logger.warning("Auto-promotion check failed", exc_info=True)

    return _build_response(attestation, current_entity.display_name, subject.display_name)


@router.get(
    "/{entity_id}",
    response_model=AttestationListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_attestations_for_entity(
    entity_id: uuid.UUID,
    attestation_type: str | None = Query(None),
    include_revoked: bool = Query(False),
    include_expired: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List formal attestations received by an entity (subject)."""
    subject = await db.get(Entity, entity_id)
    if subject is None or not subject.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    base_where = [FormalAttestation.subject_entity_id == entity_id]

    if attestation_type and attestation_type in VALID_ATTESTATION_TYPES:
        base_where.append(
            FormalAttestation.attestation_type == attestation_type
        )

    if not include_revoked:
        base_where.append(FormalAttestation.is_revoked.is_(False))

    if not include_expired:
        now = datetime.now(timezone.utc)
        base_where.append(
            (FormalAttestation.expires_at.is_(None))
            | (FormalAttestation.expires_at >= now)
        )

    # Count
    count_query = (
        select(func.count())
        .select_from(FormalAttestation)
        .where(*base_where)
    )
    total = await db.scalar(count_query) or 0

    # Fetch with issuer + subject names via aliased joins
    from sqlalchemy.orm import aliased

    issuer_alias = aliased(Entity)
    subject_alias = aliased(Entity)

    query = (
        select(
            FormalAttestation,
            issuer_alias.display_name,
            subject_alias.display_name,
        )
        .join(issuer_alias, FormalAttestation.issuer_entity_id == issuer_alias.id)
        .join(subject_alias, FormalAttestation.subject_entity_id == subject_alias.id)
        .where(*base_where)
        .order_by(FormalAttestation.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)

    attestations = []
    for att, issuer_name, subject_name in result.all():
        attestations.append(_build_response(att, issuer_name, subject_name))

    return AttestationListResponse(attestations=attestations, total=total)


@router.get(
    "/{entity_id}/issued",
    response_model=AttestationListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_attestations_issued_by_entity(
    entity_id: uuid.UUID,
    attestation_type: str | None = Query(None),
    include_revoked: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List formal attestations issued by an entity."""
    issuer = await db.get(Entity, entity_id)
    if issuer is None or not issuer.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    base_where = [FormalAttestation.issuer_entity_id == entity_id]

    if attestation_type and attestation_type in VALID_ATTESTATION_TYPES:
        base_where.append(
            FormalAttestation.attestation_type == attestation_type
        )

    if not include_revoked:
        base_where.append(FormalAttestation.is_revoked.is_(False))

    count_query = (
        select(func.count())
        .select_from(FormalAttestation)
        .where(*base_where)
    )
    total = await db.scalar(count_query) or 0

    from sqlalchemy.orm import aliased

    issuer_alias = aliased(Entity)
    subject_alias = aliased(Entity)

    query = (
        select(
            FormalAttestation,
            issuer_alias.display_name,
            subject_alias.display_name,
        )
        .join(issuer_alias, FormalAttestation.issuer_entity_id == issuer_alias.id)
        .join(subject_alias, FormalAttestation.subject_entity_id == subject_alias.id)
        .where(*base_where)
        .order_by(FormalAttestation.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)

    attestations = []
    for att, issuer_name, subject_name in result.all():
        attestations.append(_build_response(att, issuer_name, subject_name))

    return AttestationListResponse(attestations=attestations, total=total)


@router.post(
    "/{attestation_id}/revoke",
    response_model=RevokeResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def revoke_attestation(
    attestation_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a formal attestation. Only the original issuer can revoke."""
    attestation = await db.get(FormalAttestation, attestation_id)
    if attestation is None:
        raise HTTPException(status_code=404, detail="Attestation not found")

    if attestation.issuer_entity_id != current_entity.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the issuer can revoke an attestation",
        )

    if attestation.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attestation is already revoked",
        )

    now = datetime.now(timezone.utc)
    attestation.is_revoked = True
    attestation.revoked_at = now
    await db.flush()

    await log_action(
        db,
        action="formal_attestation.revoke",
        entity_id=current_entity.id,
        resource_type="formal_attestation",
        resource_id=attestation.id,
        details={
            "subject_entity_id": str(attestation.subject_entity_id),
            "attestation_type": attestation.attestation_type,
        },
    )

    # Dispatch webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "formal_attestation.revoked", {
            "attestation_id": str(attestation.id),
            "issuer_id": str(current_entity.id),
            "subject_id": str(attestation.subject_entity_id),
            "type": attestation.attestation_type,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return RevokeResponse(
        message="Attestation revoked successfully",
        attestation_id=attestation.id,
        revoked_at=now,
    )
