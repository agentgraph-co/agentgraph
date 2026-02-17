from __future__ import annotations

from fastapi import FastAPI

from src.config import settings

app = FastAPI(
    title=settings.app_name,
    description="Trust and identity infrastructure for the agent internet",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "service": settings.app_name}


@app.get(f"{settings.api_v1_prefix}/ping")
async def ping() -> dict:
    return {"ping": "pong"}
