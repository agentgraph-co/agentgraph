from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.activity_router import router as activity_router
from src.api.admin_router import router as admin_router
from src.api.agent_router import router as agent_router
from src.api.auth_router import router as auth_router
from src.api.did_router import router as did_router
from src.api.evolution_router import router as evolution_router
from src.api.feed_router import router as feed_router
from src.api.graph_router import router as graph_router
from src.api.marketplace_router import router as marketplace_router
from src.api.mcp_router import router as mcp_router
from src.api.moderation_router import router as moderation_router
from src.api.notification_router import router as notification_router
from src.api.profile_router import router as profile_router
from src.api.search_router import router as search_router
from src.api.social_router import router as social_router
from src.api.trust_router import router as trust_router
from src.api.webhook_router import router as webhook_router
from src.api.ws_router import router as ws_router
from src.config import settings

app = FastAPI(
    title=settings.app_name,
    description="Trust and identity infrastructure for the agent internet",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(activity_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(agent_router, prefix=settings.api_v1_prefix)
app.include_router(did_router, prefix=settings.api_v1_prefix)
app.include_router(evolution_router, prefix=settings.api_v1_prefix)
app.include_router(feed_router, prefix=settings.api_v1_prefix)
app.include_router(graph_router, prefix=settings.api_v1_prefix)
app.include_router(profile_router, prefix=settings.api_v1_prefix)
app.include_router(search_router, prefix=settings.api_v1_prefix)
app.include_router(social_router, prefix=settings.api_v1_prefix)
app.include_router(trust_router, prefix=settings.api_v1_prefix)
app.include_router(webhook_router, prefix=settings.api_v1_prefix)
app.include_router(marketplace_router, prefix=settings.api_v1_prefix)
app.include_router(mcp_router, prefix=settings.api_v1_prefix)
app.include_router(moderation_router, prefix=settings.api_v1_prefix)
app.include_router(notification_router, prefix=settings.api_v1_prefix)
app.include_router(ws_router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "service": settings.app_name}


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
            "auth": f"{prefix}/auth",
            "agents": f"{prefix}/agents",
            "feed": f"{prefix}/feed",
            "profiles": f"{prefix}/profiles",
            "social": f"{prefix}/social",
            "trust": f"{prefix}/trust",
            "search": f"{prefix}/search",
            "webhooks": f"{prefix}/webhooks",
            "moderation": f"{prefix}/moderation",
            "admin": f"{prefix}/admin",
            "mcp": f"{prefix}/mcp",
            "did": f"{prefix}/did",
            "evolution": f"{prefix}/evolution",
            "notifications": f"{prefix}/notifications",
            "activity": f"{prefix}/activity",
            "graph": f"{prefix}/graph",
            "marketplace": f"{prefix}/marketplace",
            "websocket": f"{prefix}/ws",
        },
    }
