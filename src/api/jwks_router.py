"""JWKS endpoint — publishes AgentGraph's attestation verification keys."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.signing import get_jwk

router = APIRouter(tags=["jwks"])


@router.get("/.well-known/jwks.json")
async def jwks() -> JSONResponse:
    """Return the platform JWKS (RFC 7517) for attestation verification."""
    return JSONResponse(
        content={"keys": [get_jwk()]},
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )
