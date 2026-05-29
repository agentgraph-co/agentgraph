"""Trust Score v2 — the public ``/aggregate`` surface (design §5).

Serves a signed, methodology-transparent v2 trust-score envelope for any
subject DID we know about. Consumers re-verify the envelope against our
published JWKS without trusting this server.

P1 scope: the envelope re-shapes the existing v1 composite (resolved via
``compute_trust_score`` → ``components``) into the signed v2 envelope. The
richer per-attestation breakdown (individual CTEF / ERC-8004 / observer
contributions) lights up as those source readers land (#110 et al.); the
engine and this endpoint don't change when they do — only the RawSignals fed
in get richer.

Signing: P1 uses the existing platform Ed25519 key (kid
``agentgraph-security-v1``, published at /.well-known/jwks.json) so envelopes
are verifiable today. The spec's dedicated ``#trust-v2-2026`` key + rotation
policy (design §9.1) is a follow-up that needs a provisioned prod secret.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.models import Entity, EntityType
from src.signing import get_trust_v2_kid, get_trust_v2_signing_key
from src.trust.aggregate_sources import components_to_contributions
from src.trust.envelope_v2 import (
    EnvelopeError,
    build_envelope,
    is_fresh,
    sign_envelope,
    verify_envelope,
)
from src.trust.score import compute_trust_score

logger = logging.getLogger(__name__)

router = APIRouter(tags=["trust-aggregate"])


def _verification_method() -> str:
    """did:web verification method whose fragment is the kid published in our
    JWKS (dedicated trust-v2 key if configured, else the platform key)."""
    return f"did:web:agentgraph.co#{get_trust_v2_kid()}"


def _subject_kind(entity: Entity) -> str:
    """Map an Entity.type to a v2 subject_kind (agent | human | service)."""
    name = getattr(entity.type, "value", str(entity.type)).lower()
    if "human" in name:
        return "human"
    if "service" in name:
        return "service"
    return "agent"


async def _resolve_entity(subject_did: str, db: AsyncSession) -> Entity:
    """Resolve a subject DID to an Entity, or raise 404."""
    result = await db.execute(select(Entity).where(Entity.did_web == subject_did))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No subject found for DID {subject_did}",
        )
    return entity


_CACHE_PREFIX = "aggregate:v2:"


async def _build_signed_envelope(subject_did: str, db: AsyncSession) -> dict:
    """Resolve → compute v1 composite → map to weighted contributions → sign.

    Each contribution's weighted_contribution is the dimension's actual share of
    the v1 composite (weight × raw), so the envelope trust_score equals the v1
    score and the breakdown is honest.

    Best-effort Redis cache keyed by DID with TTL = the envelope's freshness
    window (design §5.2 "envelope cached"). Cache ops degrade gracefully — a
    Redis outage just means every request recomputes. The persistent
    ``aggregate_envelopes`` table + event-driven recompute is a follow-up
    (needs a supervised migration).
    """
    from src import cache

    cache_key = f"{_CACHE_PREFIX}{subject_did}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    entity = await _resolve_entity(subject_did, db)
    ts = await compute_trust_score(db, entity.id)
    contributions = components_to_contributions(
        ts.components,
        is_human=(entity.type == EntityType.HUMAN),
        framework_modifier=getattr(entity, "framework_trust_modifier", None),
    )
    if not contributions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No trust signals available for DID {subject_did}",
        )
    try:
        unsigned = build_envelope(
            subject_did=subject_did,
            subject_kind=_subject_kind(entity),
            contributions=contributions,
        )
    except EnvelopeError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    signed = sign_envelope(
        unsigned, get_trust_v2_signing_key(), _verification_method()
    )
    await cache.set(cache_key, signed, ttl=int(signed["freshness_ttl_seconds"]))
    return signed


@router.get("/aggregate/{subject_did:path}/contributions")
async def get_contributions(
    subject_did: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
) -> JSONResponse:
    """Return just the methodology breakdown (contributions array) for a subject.

    Convenience for UI rendering — same data as the full envelope's
    ``contributions`` field, without the signature/identity wrapper.
    """
    envelope = await _build_signed_envelope(subject_did, db)
    return JSONResponse(
        content={
            "subject_did": envelope["subject_did"],
            "trust_score": envelope["trust_score"],
            "contributions": envelope["contributions"],
        },
        headers={"Cache-Control": f"max-age={envelope['freshness_ttl_seconds']}"},
    )


@router.get("/aggregate/{subject_did:path}/verify")
async def verify_aggregate(
    subject_did: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
) -> JSONResponse:
    """Verify the current signed envelope for a subject in one round-trip.

    Recomputes + signs the envelope, then verifies signature + freshness with
    our published key — so a consumer can confirm via us, then independently
    re-verify against /.well-known/jwks.json.
    """
    envelope = await _build_signed_envelope(subject_did, db)
    signature_valid = verify_envelope(
        envelope, get_trust_v2_signing_key().public_key()
    )
    return JSONResponse(
        content={
            "subject_did": envelope["subject_did"],
            "signature_valid": signature_valid,
            "fresh": is_fresh(envelope),
            "issuer": envelope["issuer"],
            "kid": get_trust_v2_kid(),
            "jwks": "/.well-known/jwks.json",
        }
    )


@router.get("/aggregate/{subject_did:path}")
async def get_aggregate(
    subject_did: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
) -> JSONResponse:
    """Return the signed v2 trust-score envelope for a subject DID (design §3)."""
    envelope = await _build_signed_envelope(subject_did, db)
    return JSONResponse(
        content=envelope,
        headers={"Cache-Control": f"max-age={envelope['freshness_ttl_seconds']}"},
    )
