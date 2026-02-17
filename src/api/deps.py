from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_service import decode_token, get_entity_by_id
from src.database import get_db
from src.models import Entity

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_entity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Entity:
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

    try:
        entity_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    entity = await get_entity_by_id(db, entity_id)
    if entity is None or not entity.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return entity


async def get_optional_entity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Entity | None:
    if credentials is None:
        return None
    try:
        return await get_current_entity(credentials, db)
    except HTTPException:
        return None
