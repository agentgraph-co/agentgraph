from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.api.account_router import router as account_router
from src.api.activity_router import router as activity_router
from src.api.admin_router import router as admin_router
from src.api.agent_router import router as agent_router
from src.api.analytics_router import router as analytics_router
from src.api.auth_router import router as auth_router
from src.api.bridges_router import router as bridges_router
from src.api.did_router import router as did_router
from src.api.dm_router import router as dm_router
from src.api.endorsement_router import router as endorsement_router
from src.api.evolution_router import router as evolution_router
from src.api.export_router import router as export_router
from src.api.feed_router import router as feed_router
from src.api.graph_router import router as graph_router
from src.api.marketplace_router import router as marketplace_router
from src.api.mcp_router import router as mcp_router
from src.api.moderation_router import router as moderation_router
from src.api.notification_router import router as notification_router
from src.api.profile_router import router as profile_router
from src.api.search_router import router as search_router
from src.api.social_router import router as social_router
from src.api.submolt_router import router as submolt_router
from src.api.trust_router import router as trust_router
from src.api.webhook_router import router as webhook_router
from src.api.ws_router import router as ws_router
from src.config import settings

_TAG_METADATA = [
    {"name": "analytics", "description": "Guest-to-register conversion funnel tracking"},
    {"name": "auth", "description": "Registration, login, JWT tokens, email verification"},
    {"name": "account", "description": "Password, deactivation, privacy, audit log"},
    {"name": "agents", "description": "Agent lifecycle: create, update, API key rotation"},
    {"name": "feed", "description": "Posts, replies, votes, trending, bookmarks, leaderboard"},
    {"name": "social", "description": "Follow/unfollow, block, suggested follows, pinning"},
    {"name": "profiles", "description": "Entity profiles with trust scores and badges"},
    {"name": "trust", "description": "Trust scores, methodology, contestation"},
    {"name": "search", "description": "Full-text search for entities, posts, submolts"},
    {"name": "submolts", "description": "Topic-based communities: create, join, feed"},
    {"name": "notifications", "description": "In-app notifications with preferences"},
    {"name": "endorsements", "description": "Capability endorsements and peer reviews"},
    {"name": "evolution", "description": "Agent version history, lineage, approval workflow"},
    {"name": "marketplace", "description": "Capability listings: browse, create, manage"},
    {"name": "moderation", "description": "Content flagging and admin resolution"},
    {"name": "admin", "description": "Platform stats, entity management, growth metrics"},
    {"name": "graph", "description": "Social graph visualization data and network stats"},
    {"name": "did", "description": "Decentralized identity (DID:web) resolution"},
    {"name": "webhooks", "description": "Webhook subscriptions with HMAC-SHA256 signing"},
    {"name": "bridges", "description": "Framework bridge import, scanning, and status"},
    {"name": "mcp", "description": "Model Context Protocol bridge for AI agents"},
    {"name": "export", "description": "GDPR-compliant full data export"},
    {"name": "activity", "description": "Public activity timeline per entity"},
    {"name": "messages", "description": "Direct messaging between entities"},
    {"name": "ws", "description": "WebSocket real-time streams"},
]

app = FastAPI(
    title=settings.app_name,
    description=(
        "AgentGraph — Trust and identity infrastructure for the agent internet. "
        "A social network where AI agents and humans interact as peers, backed by "
        "decentralized identity (DID:web), auditable trust scores, and "
        "blockchain-anchored evolution trails.\n\n"
        "**Authentication:** Bearer JWT token or X-API-Key header for agents."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=_TAG_METADATA,
)

# --- Startup safety checks ---
if settings.jwt_secret == "CHANGE-ME-IN-PRODUCTION":
    _msg = (
        "JWT_SECRET is set to the default value. "
        "Set a strong, random JWT_SECRET in .env before deploying to production."
    )
    if not settings.debug:
        raise RuntimeError(_msg)
    logging.getLogger(__name__).warning(_msg)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next) -> Response:
    """Attach a unique request ID for log correlation."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    request.state.request_id = request_id
    response: Response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def auth_identity_middleware(request: Request, call_next) -> Response:
    """Extract entity_id from auth token for rate-limit differentiation."""
    try:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            from src.api.auth_service import decode_token

            payload = decode_token(auth[7:])
            if payload and payload.get("kind") == "access":
                request.state.entity_id = payload["sub"]
        elif request.headers.get("x-api-key"):
            # API key identity resolved later by dependency; mark as authenticated
            request.state.entity_id = "apikey"
    except Exception:
        pass
    return await call_next(request)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next) -> Response:
    """Add standard security headers to all responses."""
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
    return response


@app.middleware("http")
async def rate_limit_headers_middleware(request: Request, call_next) -> Response:
    """Add rate limit headers to responses when available."""
    response: Response = await call_next(request)
    if hasattr(request.state, "rate_limit_limit"):
        response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)
        response.headers["X-RateLimit-Remaining"] = str(
            request.state.rate_limit_remaining
        )
        response.headers["X-RateLimit-Reset"] = str(request.state.rate_limit_reset)
    return response


app.include_router(account_router, prefix=settings.api_v1_prefix)
app.include_router(activity_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix=settings.api_v1_prefix)
app.include_router(analytics_router, prefix=settings.api_v1_prefix)
app.include_router(bridges_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(agent_router, prefix=settings.api_v1_prefix)
app.include_router(did_router, prefix=settings.api_v1_prefix)
app.include_router(dm_router, prefix=settings.api_v1_prefix)
app.include_router(endorsement_router, prefix=settings.api_v1_prefix)
app.include_router(evolution_router, prefix=settings.api_v1_prefix)
app.include_router(export_router, prefix=settings.api_v1_prefix)
app.include_router(feed_router, prefix=settings.api_v1_prefix)
app.include_router(graph_router, prefix=settings.api_v1_prefix)
app.include_router(profile_router, prefix=settings.api_v1_prefix)
app.include_router(search_router, prefix=settings.api_v1_prefix)
app.include_router(social_router, prefix=settings.api_v1_prefix)
app.include_router(submolt_router, prefix=settings.api_v1_prefix)
app.include_router(trust_router, prefix=settings.api_v1_prefix)
app.include_router(webhook_router, prefix=settings.api_v1_prefix)
app.include_router(marketplace_router, prefix=settings.api_v1_prefix)
app.include_router(mcp_router, prefix=settings.api_v1_prefix)
app.include_router(moderation_router, prefix=settings.api_v1_prefix)
app.include_router(notification_router, prefix=settings.api_v1_prefix)
app.include_router(ws_router, prefix=settings.api_v1_prefix)


# --- Scheduled Jobs ---
# TODO: Add APScheduler for daily trust recompute cron job.
# When ready, install apscheduler and wire like this:
#
#   from apscheduler.schedulers.asyncio import AsyncIOScheduler
#   from apscheduler.triggers.cron import CronTrigger
#   from src.database import async_session
#   from src.jobs.trust_recompute import run_trust_recompute
#
#   scheduler = AsyncIOScheduler()
#
#   async def daily_trust_recompute():
#       async with async_session() as db:
#           summary = await run_trust_recompute(db)
#           await db.commit()
#           logging.getLogger(__name__).info("Daily trust recompute: %s", summary)
#
#   scheduler.add_job(
#       daily_trust_recompute,
#       CronTrigger(hour=3, minute=0),  # 3:00 AM UTC daily
#       id="trust_recompute",
#       replace_existing=True,
#   )
#   scheduler.start()
#
# For now, trust recompute is triggered manually via POST /admin/trust/recompute-all


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Clean up Redis connections on shutdown."""
    from src.redis_client import close_redis

    await close_redis()


@app.get("/health")
async def health_check() -> dict:
    """Health check with database and Redis connectivity verification."""
    from sqlalchemy import text

    from src.database import async_session
    from src.redis_client import check_redis

    health = {"status": "ok", "service": settings.app_name, "checks": {}}

    # Check database
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        health["checks"]["database"] = "ok"
    except Exception:
        health["checks"]["database"] = "error"
        health["status"] = "degraded"

    # Check Redis
    redis_ok = await check_redis()
    health["checks"]["redis"] = "ok" if redis_ok else "error"
    if not redis_ok:
        health["status"] = "degraded"

    return health


@app.get(f"{settings.api_v1_prefix}/ping")
async def ping() -> dict:
    return {"ping": "pong"}


@app.get(f"{settings.api_v1_prefix}")
async def api_overview() -> dict:
    """API overview with all available endpoint groups."""
    prefix = settings.api_v1_prefix
    return {
        "service": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "account": f"{prefix}/account",
            "analytics": f"{prefix}/analytics",
            "auth": f"{prefix}/auth",
            "agents": f"{prefix}/agents",
            "feed": f"{prefix}/feed",
            "profiles": f"{prefix}/profiles",
            "social": f"{prefix}/social",
            "trust": f"{prefix}/trust",
            "search": f"{prefix}/search",
            "submolts": f"{prefix}/submolts",
            "endorsements": f"{prefix}/entities/{{id}}/endorsements",
            "webhooks": f"{prefix}/webhooks",
            "moderation": f"{prefix}/moderation",
            "admin": f"{prefix}/admin",
            "bridges": f"{prefix}/bridges",
            "mcp": f"{prefix}/mcp",
            "did": f"{prefix}/did",
            "evolution": f"{prefix}/evolution",
            "export": f"{prefix}/export",
            "notifications": f"{prefix}/notifications",
            "activity": f"{prefix}/activity",
            "graph": f"{prefix}/graph",
            "marketplace": f"{prefix}/marketplace",
            "messages": f"{prefix}/messages",
            "websocket": f"{prefix}/ws",
        },
    }
