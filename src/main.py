from __future__ import annotations

from fastapi import FastAPI

from src.api.agent_router import router as agent_router
from src.api.auth_router import router as auth_router
from src.api.profile_router import router as profile_router
from src.api.trust_router import router as trust_router
from src.config import settings

app = FastAPI(
    title=settings.app_name,
    description="Trust and identity infrastructure for the agent internet",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(agent_router, prefix=settings.api_v1_prefix)
app.include_router(profile_router, prefix=settings.api_v1_prefix)
app.include_router(trust_router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "service": settings.app_name}


@app.get(f"{settings.api_v1_prefix}/ping")
async def ping() -> dict:
    return {"ping": "pong"}
