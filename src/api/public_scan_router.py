"""Public scan API — trust-tiered security scanning for any GitHub repo.

No authentication required. Rate-limited by IP. Results cached 1 hour.
Designed for framework integrations (Claude Code, Cursor, OpenClaw, etc.)
to pre-check tools before execution.

Endpoints:
    GET /public/scan/{owner}/{repo}   — scan a repo, return trust tier + JWS
    GET /public/scan/{owner}/{repo}/badge — SVG badge for README embedding
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.signing import KID, canonicalize, create_jws

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/scan", tags=["public-scan"])


# ── Trust Tiers ─────────────────────────────────────────────────────────

TRUST_TIERS = [
    # (min_score, tier_name, requests_per_min, max_tokens, require_confirmation)
    (96, "verified",    -1,   -1,   False),  # -1 = unlimited
    (81, "trusted",     60,   8192, False),
    (51, "standard",    30,   4096, False),
    (31, "minimal",     15,   2048, True),
    (11, "restricted",  5,    1024, True),
    (0,  "blocked",     0,    0,    True),
]


def _compute_tier(score: int) -> dict:
    """Map a trust score (0-100) to a tier with recommended limits."""
    for min_score, name, rpm, tokens, confirm in TRUST_TIERS:
        if score >= min_score:
            return {
                "tier": name,
                "recommended_limits": {
                    "requests_per_minute": rpm if rpm >= 0 else None,
                    "max_tokens_per_call": tokens if tokens >= 0 else None,
                    "require_user_confirmation": confirm,
                },
            }
    return {
        "tier": "blocked",
        "recommended_limits": {
            "requests_per_minute": 0,
            "max_tokens_per_call": 0,
            "require_user_confirmation": True,
        },
    }


# ── Response Models ──────────────────────────────────────────────────────

class FindingsSummary(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    total: int = 0
    categories: dict[str, int] = {}
    suppressed_lines: int = 0  # Lines with ag-scan:ignore — transparency


class RecommendedLimits(BaseModel):
    requests_per_minute: int | None = None
    max_tokens_per_call: int | None = None
    require_user_confirmation: bool = False


class ScanMetadata(BaseModel):
    files_scanned: int = 0
    primary_language: str = ""
    has_readme: bool = False
    has_license: bool = False
    has_tests: bool = False


class PublicScanResponse(BaseModel):
    repo: str
    trust_score: int  # Security scan score (0-100) — code-level analysis only
    security_score: int = 0  # Alias for trust_score (clearer naming)
    trust_tier: str
    recommended_limits: RecommendedLimits
    scan_result: str  # clean, warnings, critical, error
    findings: FindingsSummary
    positive_signals: list[str] = []
    category_scores: dict[str, int] = {}  # per-category 0-100 sub-scores
    metadata: ScanMetadata
    scanned_at: str
    cached: bool = False
    jws: str  # Signed attestation (EdDSA, RFC 7515)
    algorithm: str = "EdDSA"
    key_id: str = KID
    jwks_url: str = "https://agentgraph.co/.well-known/jwks.json"
    # Entity trust (full composite) — only available for imported entities
    entity_trust: dict | None = None
    score_note: str = (
        "trust_score is the security scan score (code analysis only). "
        "For full entity trust including identity and external signals, "
        "import this bot to AgentGraph or use the gateway: "
        "POST /api/v1/gateway/check"
    )
    # Proxy gateway hint
    gateway_info: dict = {
        "status": "available",
        "docs": "https://agentgraph.co/docs/trust-gateway",
        "description": "Trust-tiered rate limiting gateway for AI agent tool execution",
    }


# ── Helpers ──────────────────────────────────────────────────────────────

_CACHE_PREFIX = "public_scan:"
_CACHE_TTL = 3600  # 1 hour


async def _get_entity_trust(repo: str, db: AsyncSession) -> dict | None:
    """Look up full entity trust score for an imported repo.

    If repo matches an entity on AgentGraph (via source_url), return
    the composite trust score, grade, and profile URL. Otherwise None.
    """
    from src.models import Entity, TrustScore

    # Match by source_url containing the repo path
    entity = (await db.execute(
        select(Entity).where(
            Entity.is_active.is_(True),
            Entity.source_url.ilike(f"%github.com/{repo}%"),
        ).limit(1)
    )).scalar_one_or_none()

    if not entity:
        return {
            "imported": False,
            "import_url": f"https://agentgraph.co/bots/import?url=https://github.com/{repo}",
            "message": (
                "Import this bot to AgentGraph for a full trust profile "
                "with identity verification, external signals, and "
                "trust-tiered rate limits."
            ),
            "benefits": [
                "Full trust grade (A-F) combining identity + external + security",
                "Signed EdDSA attestation with entity DID",
                "Trust gateway enforcement (rate limits by tier)",
                "README badge linking to trust profile",
                "Discoverability in search, discover, and rankings",
            ],
        }

    # Entity exists — get trust score
    ts = (await db.execute(
        select(TrustScore).where(TrustScore.entity_id == entity.id)
    )).scalar_one_or_none()

    if not ts:
        return {"imported": True, "entity_id": str(entity.id), "score": None}

    score100 = round(ts.score * 100)
    grade = (
        "A+" if score100 >= 96 else "A" if score100 >= 81
        else "B" if score100 >= 61 else "C" if score100 >= 41
        else "D" if score100 >= 21 else "F"
    )

    return {
        "imported": True,
        "entity_id": str(entity.id),
        "composite_score": score100,
        "grade": grade,
        "profile_url": f"https://agentgraph.co/profile/{entity.id}",
        "trust_detail_url": f"https://agentgraph.co/trust/{entity.id}",
    }


async def _get_cached(owner: str, repo: str) -> dict | None:
    """Check Redis cache for a previous scan result."""
    from src import cache
    return await cache.get(f"{_CACHE_PREFIX}{owner}/{repo}")


async def _set_cached(owner: str, repo: str, data: dict) -> None:
    """Store scan result in Redis cache."""
    from src import cache
    await cache.set(f"{_CACHE_PREFIX}{owner}/{repo}", data, ttl=_CACHE_TTL)


def _build_scan_payload(repo: str, result_data: dict) -> dict:
    """Build the JWS attestation payload for a public scan.

    Timestamps follow the insumer WG convention:
    - scannedAt: when the security analysis actually ran (evidence freshness)
    - issuedAt:  when this JWS attestation was minted (signature freshness)
    - expiresAt: when the attestation expires (24h TTL)
    Consumers can diff scannedAt vs issuedAt to assess evidence staleness.
    """
    now = datetime.now(timezone.utc)
    return {
        "@context": "https://schema.agentgraph.co/attestation/security/v1",
        "type": "SecurityPostureAttestation",
        "issuer": {
            "id": "did:web:agentgraph.co",
            "name": "AgentGraph",
            "url": "https://agentgraph.co",
        },
        "subject": {
            "id": f"github:{repo}",
            "repo": repo,
        },
        "scannedAt": result_data.get("scanned_at", now.isoformat()),
        "issuedAt": now.isoformat(),
        "expiresAt": (now + timedelta(hours=24)).isoformat(),
        "scan": {
            "trustScore": result_data["trust_score"],
            "trustTier": result_data["trust_tier"],
            "result": result_data["scan_result"],
            "findings": result_data["findings"],
            "positiveSignals": result_data["positive_signals"],
            "filesScanned": result_data["metadata"]["files_scanned"],
            "primaryLanguage": result_data["metadata"]["primary_language"],
            "categoryScores": result_data.get("category_scores", {}),
        },
        "recommendedLimits": result_data["recommended_limits"],
    }


def _scan_result_to_dict(result: object) -> dict:
    """Convert a ScanResult dataclass to a cacheable dict."""
    # Determine scan result label
    if result.critical_count > 0:
        scan_result = "critical"
    elif result.high_count > 0:
        scan_result = "warnings"
    else:
        scan_result = "clean"

    # Category counts
    categories: dict[str, int] = {}
    for f in result.findings:
        categories[f.category] = categories.get(f.category, 0) + 1

    tier_info = _compute_tier(result.trust_score)

    return {
        "trust_score": result.trust_score,
        "trust_tier": tier_info["tier"],
        "recommended_limits": tier_info["recommended_limits"],
        "scan_result": scan_result,
        "findings": {
            "critical": result.critical_count,
            "high": result.high_count,
            "medium": result.medium_count,
            "total": len(result.findings),
            "categories": categories,
            "suppressed_lines": result.suppressed_count,
        },
        "positive_signals": list(set(result.positive_signals)),
        "metadata": {
            "files_scanned": result.files_scanned,
            "primary_language": result.primary_language,
            "has_readme": result.has_readme,
            "has_license": result.has_license,
            "has_tests": result.has_tests,
        },
        "category_scores": getattr(result, "category_scores", {}),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Endpoints ────────────────────────────────────────────────────────────

# NOTE: wallet route MUST come before /{owner}/{repo} to avoid the catch-all
# matching "wallet" as an owner name.

@router.get(
    "/wallet/{wallet_address}",
    dependencies=[Depends(rate_limit_reads)],
    response_model=None,
)
async def scan_by_wallet(
    wallet_address: str,
    chain: str = "ethereum",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Resolve a wallet address to an entity and return its trust data.

    Part of the insumer multi-attestation WG unified query interface.
    Each issuer accepts ``?wallet=&chain=`` for cross-provider lookup.

    If no entity maps to the wallet, returns ``found: false``.
    If the entity has a linked GitHub repo, triggers a scan.
    """
    from src.models import LinkedAccount, WalletBinding

    stmt = select(WalletBinding).where(
        WalletBinding.wallet_address == wallet_address,
        WalletBinding.chain == chain,
    )
    result = await db.execute(stmt)
    binding = result.scalar_one_or_none()

    if not binding:
        return {
            "found": False,
            "wallet": wallet_address,
            "chain": chain,
            "reason": "no_entity_mapping",
        }

    # Find linked GitHub account for this entity
    stmt = select(LinkedAccount).where(
        LinkedAccount.entity_id == binding.entity_id,
        LinkedAccount.provider == "github",
    )
    result = await db.execute(stmt)
    github_account = result.scalar_one_or_none()

    if not github_account or not github_account.provider_username:
        return {
            "found": True,
            "wallet": wallet_address,
            "chain": chain,
            "entity_id": str(binding.entity_id),
            "scan": None,
            "reason": "no_linked_github_repo",
        }

    # Resolve to repo and scan
    # provider_user_id typically contains "owner/repo" for GitHub
    repo_id = github_account.provider_user_id
    if "/" not in repo_id:
        return {
            "found": True,
            "wallet": wallet_address,
            "chain": chain,
            "entity_id": str(binding.entity_id),
            "scan": None,
            "reason": "github_account_not_repo",
        }
    owner, repo = repo_id.split("/", 1)

    # Delegate to the main scan endpoint
    scan_result = await public_scan(owner=owner, repo=repo)
    return {
        "found": True,
        "wallet": wallet_address,
        "chain": chain,
        "entity_id": str(binding.entity_id),
        "scan": scan_result.dict(),
    }


@router.get(
    "/{owner}/{repo}",
    response_model=PublicScanResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def public_scan(
    owner: str,
    repo: str,
    force: bool = Query(False, description="Bypass cache and force a fresh scan"),
    db: AsyncSession = Depends(get_db),
) -> PublicScanResponse:
    """Scan a GitHub repo and return trust tier with recommended rate limits.

    No authentication required. Results are cached for 1 hour.
    Returns a signed JWS attestation (EdDSA, RFC 7515) verifiable
    against the public JWKS at ``/.well-known/jwks.json``.

    **Trust Tiers:**
    - ``verified`` (96-100): unlimited execution
    - ``trusted`` (81-95): 60 req/min, 8K tokens
    - ``standard`` (51-80): 30 req/min, 4K tokens
    - ``minimal`` (31-50): 15 req/min, 2K tokens, user confirmation
    - ``restricted`` (11-30): 5 req/min, 1K tokens, user confirmation
    - ``blocked`` (0-10): execution denied
    """
    full_name = f"{owner}/{repo}"

    # Validate inputs
    if not owner.isalnum() and not all(c.isalnum() or c in "-_." for c in owner):
        raise HTTPException(400, "Invalid owner")
    if not repo.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise HTTPException(400, "Invalid repo name")

    # Check cache
    if not force:
        cached = await _get_cached(owner, repo)
        if cached:
            # Re-sign (attestation expires, so sign fresh)
            payload = _build_scan_payload(full_name, cached)
            payload_bytes = canonicalize(payload)
            jws = create_jws(payload_bytes)

            # Look up entity trust (full composite) if this repo is imported
            entity_trust = await _get_entity_trust(full_name, db)

            return PublicScanResponse(
                repo=full_name,
                trust_score=cached["trust_score"],
                security_score=cached["trust_score"],
                trust_tier=cached["trust_tier"],
                recommended_limits=RecommendedLimits(**cached["recommended_limits"]),
                scan_result=cached["scan_result"],
                findings=FindingsSummary(**cached["findings"]),
                positive_signals=cached.get("positive_signals", []),
                category_scores=cached.get("category_scores", {}),
                metadata=ScanMetadata(**cached["metadata"]),
                scanned_at=cached["scanned_at"],
                cached=True,
                jws=jws,
                entity_trust=entity_trust,
            )

    # Run scan
    from src.config import settings
    from src.scanner.scan import scan_repo

    token = settings.github_token or settings.github_outreach_token
    try:
        result = await scan_repo(
            full_name=full_name,
            stars=0,
            description="",
            framework="",
            token=token,
        )
    except Exception:
        logger.exception("Public scan failed for %s", full_name)
        raise HTTPException(502, "Scan failed — GitHub API may be unavailable")

    if result.error:
        raise HTTPException(
            404 if "not found" in (result.error or "").lower() else 502,
            f"Scan error: {result.error}",
        )

    # Convert to dict and cache
    data = _scan_result_to_dict(result)
    await _set_cached(owner, repo, data)

    # Sign (JCS-canonical payload for cross-implementation verification)
    payload = _build_scan_payload(full_name, data)
    payload_bytes = canonicalize(payload)
    jws = create_jws(payload_bytes)

    # Look up entity trust (full composite) if this repo is imported
    entity_trust = await _get_entity_trust(full_name, db)

    return PublicScanResponse(
        repo=full_name,
        trust_score=data["trust_score"],
        security_score=data["trust_score"],
        trust_tier=data["trust_tier"],
        recommended_limits=RecommendedLimits(**data["recommended_limits"]),
        scan_result=data["scan_result"],
        findings=FindingsSummary(**data["findings"]),
        positive_signals=data["positive_signals"],
        category_scores=data.get("category_scores", {}),
        metadata=ScanMetadata(**data["metadata"]),
        scanned_at=data["scanned_at"],
        cached=False,
        jws=jws,
        entity_trust=entity_trust,
    )


@router.get(
    "/{owner}/{repo}/badge",
    dependencies=[Depends(rate_limit_reads)],
    response_class=Response,
)
async def scan_badge(
    owner: str,
    repo: str,
) -> Response:
    """Return an SVG trust-tier badge for README embedding.

    Usage in markdown:
    ```
    ![Trust Score](https://agentgraph.co/api/v1/public/scan/owner/repo/badge)
    ```
    """
    # Use cached data if available, otherwise show "not scanned"
    cached = await _get_cached(owner, repo)

    if cached:
        score = cached["trust_score"]
        tier = cached["trust_tier"]
    else:
        score = None
        tier = "not scanned"

    # Color mapping
    colors = {
        "verified": "#22c55e",
        "trusted": "#3b82f6",
        "standard": "#eab308",
        "minimal": "#f97316",
        "restricted": "#ef4444",
        "blocked": "#991b1b",
        "not scanned": "#6b7280",
    }
    color = colors.get(tier, "#6b7280")
    label = f"{score}/100 {tier}" if score is not None else "not scanned"
    label_width = len(label) * 7 + 10
    total_width = 80 + label_width

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20">
  <rect width="80" height="20" fill="#555" rx="3"/>
  <rect x="80" width="{label_width}" height="20" fill="{color}" rx="3"/>
  <rect x="80" width="4" height="20" fill="{color}"/>
  <text x="40" y="14" fill="#fff" font-family="Verdana,sans-serif" font-size="11"
        text-anchor="middle">trust score</text>
  <text x="{80 + label_width // 2}" y="14" fill="#fff" font-family="Verdana,sans-serif"
        font-size="11" text-anchor="middle">{label}</text>
</svg>'''

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=3600, s-maxage=86400",
            "Access-Control-Allow-Origin": "*",
        },
    )
