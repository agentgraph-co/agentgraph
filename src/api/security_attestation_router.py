"""Signed security posture attestations (A2A trust.signals[] compatible)."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.models import Entity, FrameworkSecurityScan, TrustScore
from src.signing import KID, canonicalize, create_jws

logger = logging.getLogger(__name__)

router = APIRouter(tags=["attestations"])

# ── response models ───────────────────────────────────────────────────


class AttestationIssuer(BaseModel):
    id: str
    name: str
    url: str


class AttestationSubject(BaseModel):
    id: str
    entity_id: str
    display_name: str


class ScanFindings(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    total: int = 0


class ScanChecks(BaseModel):
    no_critical_findings: bool = True
    no_high_findings: bool = True
    has_readme: bool = False
    has_license: bool = False
    has_tests: bool = False


class ScanData(BaseModel):
    result: str
    scanned_at: str
    framework: str
    trust_score: int = 0
    findings: ScanFindings
    positive_signals: list[str] = []
    checks: ScanChecks
    files_scanned: int = 0
    primary_language: str = ""


class TrustData(BaseModel):
    overall: float | None = None
    scan_component: float | None = None


class AttestationPayload(BaseModel):
    context: str
    type: str
    issuer: AttestationIssuer
    subject: AttestationSubject
    issued_at: str
    expires_at: str
    scan: ScanData
    trust: TrustData


class SecurityAttestationResponse(BaseModel):
    jws: str
    payload: dict
    algorithm: str = "EdDSA"
    key_id: str = KID
    jwks_url: str = "https://agentgraph.co/.well-known/jwks.json"


# ── helpers ───────────────────────────────────────────────────────────

def _build_payload(
    entity: Entity,
    scan: FrameworkSecurityScan,
    trust: TrustScore | None,
) -> dict:
    """Build the attestation payload dict."""
    now = datetime.now(timezone.utc)
    vulns = scan.vulnerabilities if isinstance(scan.vulnerabilities, dict) else {}

    # Extract finding counts — handle both dict and list formats
    critical = vulns.get("critical_count", 0)
    high = vulns.get("high_count", 0)
    medium = vulns.get("medium_count", 0)

    # If vulnerabilities is a list of findings, count by severity
    if isinstance(scan.vulnerabilities, list):
        findings = [
            f for f in scan.vulnerabilities if isinstance(f, dict)
        ]
        critical = sum(1 for f in findings if f.get("severity") == "critical")
        high = sum(1 for f in findings if f.get("severity") == "high")
        medium = sum(1 for f in findings if f.get("severity") == "medium")

    total = critical + high + medium

    did_uri = f"did:web:agentgraph.co:entities:{entity.id}"

    return {
        "@context": "https://schema.agentgraph.co/attestation/security/v1",
        "type": "SecurityPostureAttestation",
        "issuer": {
            "id": "did:web:agentgraph.co",
            "name": "AgentGraph",
            "url": "https://agentgraph.co",
        },
        "subject": {
            "id": did_uri,
            "entity_id": str(entity.id),
            "display_name": entity.display_name,
        },
        "scannedAt": scan.scanned_at.isoformat() if scan.scanned_at else now.isoformat(),
        "issuedAt": now.isoformat(),
        "expiresAt": (now + timedelta(hours=24)).isoformat(),
        "scan": {
            "result": scan.scan_result,
            "framework": scan.framework,
            "trustScore": vulns.get("trust_score", 0) if isinstance(vulns, dict) else 0,
            "findings": {
                "critical": critical,
                "high": high,
                "medium": medium,
                "total": total,
            },
            "positiveSignals": vulns.get("positive_signals", []) if isinstance(vulns, dict) else [],
            "checks": {
                "no_critical_findings": critical == 0,
                "no_high_findings": high == 0,
                "has_readme": vulns.get("has_readme", False) if isinstance(vulns, dict) else False,
                "has_license": (
                    vulns.get("has_license", False)
                    if isinstance(vulns, dict) else False
                ),
                "has_tests": vulns.get("has_tests", False) if isinstance(vulns, dict) else False,
            },
            "filesScanned": vulns.get("files_scanned", 0) if isinstance(vulns, dict) else 0,
            "primaryLanguage": vulns.get("primary_language", "") if isinstance(vulns, dict) else "",
        },
        "trust": {
            "overall": round(trust.score, 4) if trust else None,
            "scanComponent": (
                round((trust.components or {}).get("scan_score", 0), 4)
                if trust else None
            ),
        },
    }


# ── endpoint ──────────────────────────────────────────────────────────


@router.get(
    "/entities/{entity_id}/attestation/security",
    response_model=SecurityAttestationResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_security_attestation(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SecurityAttestationResponse:
    """Return a signed security posture attestation for *entity_id*.

    The response follows the insumer multi-attestation format and can be
    verified using the public key at ``/.well-known/jwks.json``.
    """
    # Look up entity
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.is_active.is_(True)),
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Latest security scan
    scan_result = await db.execute(
        select(FrameworkSecurityScan)
        .where(FrameworkSecurityScan.entity_id == entity_id)
        .order_by(FrameworkSecurityScan.scanned_at.desc())
        .limit(1),
    )
    scan = scan_result.scalar_one_or_none()
    if not scan:
        raise HTTPException(
            status_code=404,
            detail="No security scan available for this entity",
        )

    # Trust score (optional — attestation still valid without it)
    trust_result = await db.execute(
        select(TrustScore).where(TrustScore.entity_id == entity_id),
    )
    trust = trust_result.scalar_one_or_none()

    # Build & sign as compact JWS (RFC 7515)
    payload = _build_payload(entity, scan, trust)
    payload_bytes = canonicalize(payload)
    jws = create_jws(payload_bytes)

    return SecurityAttestationResponse(
        jws=jws,
        payload=payload,
        algorithm="EdDSA",
        key_id=KID,
        jwks_url="https://agentgraph.co/.well-known/jwks.json",
    )
