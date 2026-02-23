from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_service import decode_token, get_entity_by_id
from src.database import get_db
from src.models import Entity

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_entity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Entity:
    """Authenticate via Bearer JWT or X-API-Key header."""
    # Try API key first
    if x_api_key is not None:
        from src.api.agent_service import authenticate_by_api_key

        entity = await authenticate_by_api_key(db, x_api_key)
        if entity is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )
        return entity

    # Fall back to Bearer JWT
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("kind") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check token blacklist (for logout)
    jti = payload.get("jti")
    if jti:
        from src.api.auth_service import is_token_blacklisted

        if await is_token_blacklisted(db, jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

    try:
        entity_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    entity = await get_entity_by_id(db, entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Auto-reactivate if suspension has expired
    if not entity.is_active and entity.suspended_until is not None:
        from datetime import datetime, timezone

        if datetime.now(timezone.utc) >= entity.suspended_until:
            entity.is_active = True
            entity.suspended_until = None
            await db.flush()

    if not entity.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return entity


def require_scope(scope: str):
    """Dependency that checks API key scopes.

    If the request was authenticated via API key, verifies the key
    has the required scope. JWT-authenticated requests pass through.
    """

    async def _check_scope(
        x_api_key: str | None = Header(None),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        if x_api_key is None:
            return  # JWT auth — scopes not applicable
        import hashlib

        from sqlalchemy import select as sa_select

        from src.models import APIKey

        key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
        api_key = await db.scalar(
            sa_select(APIKey).where(
                APIKey.key_hash == key_hash, APIKey.is_active.is_(True),
            )
        )
        if api_key is None:
            return  # Will be rejected by get_current_entity
        if api_key.scopes and scope not in api_key.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key missing required scope: {scope}",
            )

    return Depends(_check_scope)


async def get_optional_entity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Entity | None:
    if credentials is None and x_api_key is None:
        return None
    try:
        return await get_current_entity(credentials, x_api_key, db)
    except HTTPException:
        return None
