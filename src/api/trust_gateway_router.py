"""Trust Gateway Proxy — enforcement layer between agents and tools.

The public scan API is advisory ("what's the trust tier?"). The gateway
proxy adds enforcement ("block this request because trust is too low").

Framework-agnostic HTTP middleware that:
1. Receives a request with a target tool/repo identifier
2. Queries the trust tier (from cache or live scan)
3. Applies configurable policy (allow/rate-limit/block)
4. Returns a decision with signed attestation

This is NOT a full HTTP proxy — it's a trust-check endpoint that agent
frameworks call before connecting to a tool. The framework enforces
the decision.

Endpoints:
    POST /gateway/check    — check trust + get enforcement decision
    POST /gateway/policy   — configure per-user enforcement policy
    GET  /gateway/stats    — usage statistics
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.signing import canonicalize, create_jws

# ── Usage Metrics (Redis-backed counters) ──

_METRICS_PREFIX = "gw:metrics:"


async def _increment_metric(key: str, amount: int = 1) -> None:
    """Increment a Redis counter for gateway metrics."""
    try:
        from src.redis_client import get_redis
        r = get_redis()
        await r.incrby(f"{_METRICS_PREFIX}{key}", amount)
    except Exception:
        pass


async def _get_metric(key: str) -> int:
    """Get a Redis counter value."""
    try:
        from src.redis_client import get_redis
        r = get_redis()
        val = await r.get(f"{_METRICS_PREFIX}{key}")
        return int(val) if val else 0
    except Exception:
        return 0

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gateway", tags=["trust-gateway"])


# ── Request / Response Models ──

class GatewayCheckRequest(BaseModel):
    """Request to check trust for a tool before execution."""
    repo: str  # owner/repo format (e.g. "crewAIInc/crewAI")
    action: str = "execute"  # what the agent wants to do
    min_tier: str = "standard"  # minimum acceptable tier
    context: str | None = None  # optional context (e.g. "data_analysis")
    include_external: bool = False  # opt-in: query external providers (adds latency)


class ExternalSignal(BaseModel):
    """A trust signal from an external provider."""
    provider: str
    type: str
    score: float | None = None
    tier: str | None = None
    verified: bool = False
    error: str | None = None


class GatewayDecision(BaseModel):
    """Enforcement decision returned by the gateway."""
    allowed: bool
    repo: str
    trust_score: int  # security scan score (0-100)
    trust_tier: str
    grade: str  # A+/A/B/C/D/F
    decision_reason: str
    recommended_limits: dict
    category_scores: dict = {}
    # External provider signals (aggregated)
    external_signals: list[ExternalSignal] = []
    # Signed decision for audit trail
    jws: str | None = None
    checked_at: str
    # Latency
    check_ms: float


class GatewayPolicyRequest(BaseModel):
    """Configure enforcement policy for a user/org."""
    min_tier: str = "standard"  # minimum tier to allow execution
    block_categories: list[str] = []  # block if any category fails (e.g. ["secret_hygiene"])
    max_category_threshold: int = 40  # block if any category below this
    require_scan: bool = True  # block unscanned tools
    log_only: bool = False  # log decisions but don't block


# ── Tier Ordering ──

TIER_ORDER = {
    "verified": 6,
    "trusted": 5,
    "standard": 4,
    "minimal": 3,
    "restricted": 2,
    "blocked": 1,
}

GRADE_MAP = {
    "A+": "verified", "A": "trusted", "B": "standard",
    "C": "standard", "D": "minimal", "F": "blocked",
}


def _score_to_grade(score: int) -> str:
    if score >= 96:
        return "A+"
    if score >= 81:
        return "A"
    if score >= 61:
        return "B"
    if score >= 41:
        return "C"
    if score >= 21:
        return "D"
    return "F"


def _tier_meets_minimum(actual_tier: str, min_tier: str) -> bool:
    """Check if the actual tier meets or exceeds the minimum."""
    return TIER_ORDER.get(actual_tier, 0) >= TIER_ORDER.get(min_tier, 0)


# ── Endpoints ──

@router.post(
    "/check",
    response_model=GatewayDecision,
    dependencies=[Depends(rate_limit_reads)],
)
async def gateway_check(
    request: GatewayCheckRequest,
    db: AsyncSession = Depends(get_db),
) -> GatewayDecision:
    """Check trust tier for a tool and return an enforcement decision.

    Agent frameworks call this before connecting to a tool. The response
    includes whether the connection should be allowed, rate limits to apply,
    and a signed JWS decision for audit trails.

    Example::

        POST /api/v1/gateway/check
        {"repo": "crewAIInc/crewAI", "min_tier": "standard"}

        → {"allowed": true, "trust_tier": "verified", "grade": "A+", ...}
    """
    start = time.monotonic()

    # Track metrics
    await _increment_metric("checks:total")

    # Parse owner/repo
    if "/" not in request.repo:
        raise HTTPException(400, "repo must be in owner/repo format")
    owner, repo = request.repo.split("/", 1)

    # Query the public scan API (uses cache internally)
    from src.api.public_scan_router import public_scan
    try:
        scan_result = await public_scan(owner=owner, repo=repo, db=db)
    except HTTPException as e:
        # Scan failed — treat as blocked
        elapsed = (time.monotonic() - start) * 1000
        return GatewayDecision(
            allowed=False,
            repo=request.repo,
            trust_score=0,
            trust_tier="blocked",
            grade="F",
            decision_reason=f"Scan failed: {e.detail}",
            recommended_limits={
                "requests_per_minute": 0,
                "max_tokens_per_call": 0,
                "require_user_confirmation": True,
            },
            checked_at=datetime.now(timezone.utc).isoformat(),
            check_ms=round(elapsed, 1),
        )

    score = scan_result.trust_score
    tier = scan_result.trust_tier
    grade = _score_to_grade(score)
    limits = scan_result.recommended_limits.dict()
    category_scores = scan_result.category_scores or {}

    # Query external providers only if opted in (adds 10-30s latency)
    external_signals: list[ExternalSignal] = []
    if request.include_external:
        try:
            from src.trust.external_providers import query_all_providers
            attestations = await query_all_providers(request.repo)
            for att in attestations:
                if att.error is None:  # Only include successful results
                    external_signals.append(ExternalSignal(
                        provider=att.provider_name,
                        type=att.attestation_type,
                        score=att.score,
                        tier=att.tier,
                        verified=att.verified,
                    ))
        except Exception:
            pass  # Best-effort

    # Enforcement decision
    allowed = _tier_meets_minimum(tier, request.min_tier)
    reason = f"Tier {tier} meets minimum {request.min_tier}" if allowed else (
        f"Tier {tier} below minimum {request.min_tier}"
    )

    # Check category-level blocks
    if allowed and category_scores:
        for cat, cat_score in category_scores.items():
            if cat_score < 40:  # hard floor for any category
                allowed = False
                reason = f"Category {cat} score {cat_score} below threshold 40"
                break

    # Sign the decision for audit trail
    # Track decision metrics
    await _increment_metric(f"decisions:{'allowed' if allowed else 'blocked'}")
    await _increment_metric(f"tiers:{tier}")
    await _increment_metric(f"grades:{grade}")

    decision_payload = {
        "type": "GatewayDecision",
        "repo": request.repo,
        "action": request.action,
        "allowed": allowed,
        "trust_score": score,
        "trust_tier": tier,
        "grade": grade,
        "reason": reason,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    jws = create_jws(canonicalize(decision_payload))

    elapsed = (time.monotonic() - start) * 1000

    return GatewayDecision(
        allowed=allowed,
        repo=request.repo,
        trust_score=score,
        trust_tier=tier,
        grade=grade,
        decision_reason=reason,
        recommended_limits=limits,
        category_scores=category_scores,
        external_signals=external_signals,
        jws=jws,
        checked_at=datetime.now(timezone.utc).isoformat(),
        check_ms=round(elapsed, 1),
    )


@router.get(
    "/stats",
    dependencies=[Depends(rate_limit_reads)],
)
async def gateway_stats() -> dict:
    """Gateway usage statistics.

    Returns aggregate stats about trust checks performed.
    Useful for monitoring and dashboards.
    """
    # TODO: implement Redis-backed counters for:
    # - total checks today/week/month
    # - checks by tier
    # - checks by decision (allowed/blocked)
    # - average latency
    # - top repos checked
    # Fetch live metrics
    total = await _get_metric("checks:total")
    allowed = await _get_metric("decisions:allowed")
    blocked = await _get_metric("decisions:blocked")

    tier_counts = {}
    for t in TIER_ORDER:
        c = await _get_metric(f"tiers:{t}")
        if c > 0:
            tier_counts[t] = c

    grade_counts = {}
    for g in ["A+", "A", "B", "C", "D", "F"]:
        c = await _get_metric(f"grades:{g}")
        if c > 0:
            grade_counts[g] = c

    return {
        "status": "operational",
        "version": "v1",
        "description": "Trust-tiered enforcement gateway for AI agent tool execution",
        "docs": "https://agentgraph.co/docs/trust-gateway",
        "endpoints": {
            "check": "POST /api/v1/gateway/check",
            "webhook_rescan": "POST /api/v1/gateway/webhook/rescan",
            "stats": "GET /api/v1/gateway/stats",
        },
        "metrics": {
            "total_checks": total,
            "allowed": allowed,
            "blocked": blocked,
            "by_tier": tier_counts,
            "by_grade": grade_counts,
        },
        "supported_tiers": list(TIER_ORDER.keys()),
        "grade_scale": {
            "A+": "96-100 (Exceptional)",
            "A": "81-95 (Trusted)",
            "B": "61-80 (Good)",
            "C": "41-60 (Fair)",
            "D": "21-40 (Caution)",
            "F": "0-20 (Fail)",
        },
        "external_providers": ["RNWY", "MoltBridge", "AgentID"],
    }


# ── Webhook Endpoints ──


class WebhookSubscribeRequest(BaseModel):
    """Subscribe to outbound scan-change notifications for a repo."""
    repo: str  # owner/repo format
    callback_url: str  # URL to POST notifications to
    provider: str  # e.g. "moltbridge"
    signing_secret: str | None = None  # optional HMAC-SHA256 shared secret


class WebhookSubscribeResponse(BaseModel):
    """Confirmation of a webhook subscription."""
    subscribed: bool
    repo: str
    callback_url: str
    provider: str
    message: str


@router.post(
    "/webhook/subscribe",
    response_model=WebhookSubscribeResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def webhook_subscribe(
    request: WebhookSubscribeRequest,
) -> WebhookSubscribeResponse:
    """Register an outbound webhook for scan-score-change notifications.

    When the security scan score changes for the specified repo, AgentGraph
    will POST a signed payload to the callback URL containing:
    ``{repo, new_score, old_score, changed_at, jws}``.

    Example::

        POST /api/v1/gateway/webhook/subscribe
        {"repo": "owner/repo", "callback_url": "https://api.moltbridge.ai/webhooks/scan",
         "provider": "moltbridge"}
    """
    if "/" not in request.repo:
        return WebhookSubscribeResponse(
            subscribed=False,
            repo=request.repo,
            callback_url=request.callback_url,
            provider=request.provider,
            message="repo must be in owner/repo format",
        )

    if not request.callback_url.startswith("https://"):
        return WebhookSubscribeResponse(
            subscribed=False,
            repo=request.repo,
            callback_url=request.callback_url,
            provider=request.provider,
            message="callback_url must use HTTPS",
        )

    from src.trust.outbound_webhooks import register_subscription

    try:
        await register_subscription(
            repo=request.repo,
            callback_url=request.callback_url,
            provider=request.provider,
            signing_secret=request.signing_secret,
        )
        return WebhookSubscribeResponse(
            subscribed=True,
            repo=request.repo,
            callback_url=request.callback_url,
            provider=request.provider,
            message=(
                "Subscription registered. You will receive POST"
                " notifications when scan scores change."
            ),
        )
    except Exception as e:
        logger.exception("Webhook subscribe error: %s", request.repo)
        return WebhookSubscribeResponse(
            subscribed=False,
            repo=request.repo,
            callback_url=request.callback_url,
            provider=request.provider,
            message=f"Error: {e}",
        )


class WebhookRescanRequest(BaseModel):
    """Request from external provider to trigger a rescan."""
    repo: str  # owner/repo format
    reason: str  # why the rescan is needed
    provider: str  # who is requesting (e.g. "moltbridge")
    severity: str = "medium"  # low/medium/high


class WebhookRescanResponse(BaseModel):
    """Response after processing a rescan webhook."""
    accepted: bool
    repo: str
    message: str
    scan_queued: bool = False


@router.post(
    "/webhook/rescan",
    response_model=WebhookRescanResponse,
)
async def webhook_rescan(
    request: WebhookRescanRequest,
) -> WebhookRescanResponse:
    """Receive a rescan request from an external provider.

    When MoltBridge detects a behavioral anomaly or another provider
    detects a trust signal change, they POST here to trigger a fresh
    security scan. The compound signal (behavioral anomaly + code
    analysis) is more informative than either alone.

    Example::

        POST /api/v1/gateway/webhook/rescan
        {"repo": "owner/repo", "reason": "behavioral_anomaly", "provider": "moltbridge"}
    """
    if "/" not in request.repo:
        return WebhookRescanResponse(
            accepted=False,
            repo=request.repo,
            message="repo must be in owner/repo format",
        )

    owner, repo = request.repo.split("/", 1)

    # Queue the rescan (force=True bypasses cache)
    try:
        import asyncio

        from src.config import settings
        from src.scanner.scan import scan_repo

        token = settings.github_token or settings.github_outreach_token

        async def _rescan() -> None:
            try:
                await asyncio.wait_for(
                    scan_repo(
                        full_name=request.repo,
                        stars=0,
                        description="",
                        framework="",
                        token=token,
                    ),
                    timeout=120.0,  # Hard timeout to prevent runaway scans
                )
                logger.info(
                    "Webhook rescan completed: %s (provider=%s, reason=%s)",
                    request.repo, request.provider, request.reason,
                )
            except Exception:
                logger.warning("Webhook rescan failed: %s", request.repo)

        asyncio.create_task(_rescan())

        return WebhookRescanResponse(
            accepted=True,
            repo=request.repo,
            message=f"Rescan queued (provider={request.provider}, reason={request.reason})",
            scan_queued=True,
        )
    except Exception as e:
        logger.exception("Webhook rescan error: %s", request.repo)
        return WebhookRescanResponse(
            accepted=False,
            repo=request.repo,
            message=f"Error: {e}",
        )
