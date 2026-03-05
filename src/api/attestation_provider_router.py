from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, require_admin
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import (
    AttestationProvider,
    Entity,
    FormalAttestation,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/attestation-providers", tags=["attestation-providers"],
)


# --- Schemas ---


class RegisterProviderRequest(BaseModel):
    provider_name: str = Field(..., min_length=1, max_length=200)
    provider_url: str | None = Field(None, max_length=500)
    supported_attestation_types: list[str] = Field(..., min_length=1)
    description: str | None = Field(None, max_length=2000)


class RegisterProviderResponse(BaseModel):
    provider_id: uuid.UUID
    api_key: str
    provider_name: str
    is_active: bool
    message: str

    model_config = {"from_attributes": True}


class ProviderSummary(BaseModel):
    id: uuid.UUID
    provider_name: str
    provider_url: str | None
    description: str | None
    supported_types: list[str]
    is_active: bool
    attestation_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ProviderListResponse(BaseModel):
    providers: list[ProviderSummary]
    total: int


class ProviderDetailResponse(BaseModel):
    id: uuid.UUID
    operator_entity_id: uuid.UUID
    provider_name: str
    provider_url: str | None
    description: str | None
    supported_types: list[str]
    is_active: bool
    attestation_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SubmitAttestationRequest(BaseModel):
    subject_entity_id: uuid.UUID
    attestation_type: str = Field(..., min_length=1, max_length=50)
    evidence: str | None = Field(None, max_length=5000)
    expires_at: datetime | None = None


class SubmitAttestationResponse(BaseModel):
    attestation_id: uuid.UUID
    subject_entity_id: uuid.UUID
    attestation_type: str
    provider_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ProviderStatusResponse(BaseModel):
    provider_id: uuid.UUID
    is_active: bool
    message: str


# --- Helpers ---


def _hash_api_key(key: str) -> str:
    """Hash a provider API key with SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


async def _get_provider_by_api_key(
    db: AsyncSession, api_key: str,
) -> AttestationProvider | None:
    """Look up an active provider by its API key hash."""
    key_hash = _hash_api_key(api_key)
    return await db.scalar(
        select(AttestationProvider).where(
            AttestationProvider.api_key_hash == key_hash,
        )
    )


# --- Endpoints ---


@router.post(
    "/register",
    response_model=RegisterProviderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_writes)],
)
async def register_provider(
    body: RegisterProviderRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Register as an attestation provider.

    The authenticated user becomes the provider operator. An API key is
    returned for submitting attestations. Admin approval is required before
    the provider is active.
    """
    # Check for duplicate provider name
    existing = await db.scalar(
        select(AttestationProvider).where(
            AttestationProvider.provider_name == body.provider_name,
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A provider with this name already exists",
        )

    # Validate supported attestation types are non-empty strings
    for att_type in body.supported_attestation_types:
        if not att_type or len(att_type) > 50:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid attestation type: '{att_type}'",
            )

    # Generate API key
    raw_key = secrets.token_urlsafe(32)
    key_hash = _hash_api_key(raw_key)

    provider = AttestationProvider(
        id=uuid.uuid4(),
        operator_entity_id=current_entity.id,
        provider_name=body.provider_name,
        provider_url=body.provider_url,
        description=body.description,
        supported_types=body.supported_attestation_types,
        api_key_hash=key_hash,
        is_active=False,
    )
    db.add(provider)
    await db.flush()

    await log_action(
        db,
        action="attestation_provider.register",
        entity_id=current_entity.id,
        resource_type="attestation_provider",
        resource_id=provider.id,
        details={
            "provider_name": body.provider_name,
            "supported_types": body.supported_attestation_types,
        },
    )

    return RegisterProviderResponse(
        provider_id=provider.id,
        api_key=raw_key,
        provider_name=provider.provider_name,
        is_active=False,
        message="Provider registered. Admin approval required before activation.",
    )


@router.get(
    "",
    response_model=ProviderListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_providers(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List registered attestation providers (public, paginated)."""
    count_query = select(func.count()).select_from(AttestationProvider)
    total = await db.scalar(count_query) or 0

    query = (
        select(AttestationProvider)
        .order_by(AttestationProvider.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    providers = result.scalars().all()

    return ProviderListResponse(
        providers=[
            ProviderSummary(
                id=p.id,
                provider_name=p.provider_name,
                provider_url=p.provider_url,
                description=p.description,
                supported_types=p.supported_types or [],
                is_active=p.is_active,
                attestation_count=p.attestation_count,
                created_at=p.created_at,
            )
            for p in providers
        ],
        total=total,
    )


@router.get(
    "/{provider_id}",
    response_model=ProviderDetailResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_provider(
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get full details for an attestation provider."""
    provider = await db.get(AttestationProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    return ProviderDetailResponse(
        id=provider.id,
        operator_entity_id=provider.operator_entity_id,
        provider_name=provider.provider_name,
        provider_url=provider.provider_url,
        description=provider.description,
        supported_types=provider.supported_types or [],
        is_active=provider.is_active,
        attestation_count=provider.attestation_count,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


@router.post(
    "/{provider_id}/submit",
    response_model=SubmitAttestationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_writes)],
)
async def submit_attestation(
    provider_id: uuid.UUID,
    body: SubmitAttestationRequest,
    x_provider_key: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Submit an attestation via provider API key.

    Auth is via the X-Provider-Key header rather than Bearer JWT.
    The attestation is created as a FormalAttestation with the issuer
    set to the provider's operator entity.
    """
    if not x_provider_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Provider-Key header required",
        )

    # Look up provider by API key
    provider = await _get_provider_by_api_key(db, x_provider_key)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid provider API key",
        )

    # Verify the key matches this provider
    if provider.id != provider_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key does not match this provider",
        )

    # Provider must be active (admin approved)
    if not provider.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Provider is not active. Admin approval required.",
        )

    # Validate attestation_type is in supported types
    if body.attestation_type not in (provider.supported_types or []):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Attestation type '{body.attestation_type}' is not supported "
                f"by this provider. Supported: {provider.supported_types}"
            ),
        )

    # Validate subject entity exists and is active
    subject = await db.get(Entity, body.subject_entity_id)
    if subject is None or not subject.is_active:
        raise HTTPException(status_code=404, detail="Subject entity not found")

    # Operator cannot attest for themselves
    if provider.operator_entity_id == body.subject_entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot attest for the provider's own operator",
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
            FormalAttestation.issuer_entity_id == provider.operator_entity_id,
            FormalAttestation.subject_entity_id == body.subject_entity_id,
            FormalAttestation.attestation_type == body.attestation_type,
        )
    )
    if existing:
        if not existing.is_revoked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An active attestation of this type already exists for this entity",
            )
        # Remove revoked attestation so a fresh one can be issued
        await db.delete(existing)
        await db.flush()

    attestation = FormalAttestation(
        id=uuid.uuid4(),
        issuer_entity_id=provider.operator_entity_id,
        subject_entity_id=body.subject_entity_id,
        attestation_type=body.attestation_type,
        evidence=body.evidence,
        expires_at=body.expires_at,
    )
    db.add(attestation)

    # Increment attestation count
    provider.attestation_count = (provider.attestation_count or 0) + 1
    await db.flush()

    await log_action(
        db,
        action="attestation_provider.submit",
        entity_id=provider.operator_entity_id,
        resource_type="formal_attestation",
        resource_id=attestation.id,
        details={
            "provider_id": str(provider.id),
            "provider_name": provider.provider_name,
            "subject_entity_id": str(body.subject_entity_id),
            "attestation_type": body.attestation_type,
        },
    )

    return SubmitAttestationResponse(
        attestation_id=attestation.id,
        subject_entity_id=body.subject_entity_id,
        attestation_type=body.attestation_type,
        provider_id=provider.id,
        created_at=attestation.created_at,
    )


@router.post(
    "/{provider_id}/approve",
    response_model=ProviderStatusResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def approve_provider(
    provider_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Admin approves an attestation provider, making it active."""
    require_admin(current_entity)

    provider = await db.get(AttestationProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    if provider.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider is already active",
        )

    provider.is_active = True
    await db.flush()

    await log_action(
        db,
        action="attestation_provider.approve",
        entity_id=current_entity.id,
        resource_type="attestation_provider",
        resource_id=provider.id,
        details={"provider_name": provider.provider_name},
    )

    return ProviderStatusResponse(
        provider_id=provider.id,
        is_active=True,
        message="Provider approved and activated",
    )


@router.post(
    "/{provider_id}/revoke",
    response_model=ProviderStatusResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def revoke_provider(
    provider_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Admin revokes an attestation provider, deactivating it."""
    require_admin(current_entity)

    provider = await db.get(AttestationProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    if not provider.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider is already inactive",
        )

    provider.is_active = False
    await db.flush()

    await log_action(
        db,
        action="attestation_provider.revoke",
        entity_id=current_entity.id,
        resource_type="attestation_provider",
        resource_id=provider.id,
        details={"provider_name": provider.provider_name},
    )

    return ProviderStatusResponse(
        provider_id=provider.id,
        is_active=False,
        message="Provider revoked and deactivated",
    )
