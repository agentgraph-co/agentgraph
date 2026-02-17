from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models import Entity, EntityType

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(entity_id: uuid.UUID, entity_type: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": str(entity_id),
        "type": entity_type,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "kind": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(entity_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        "sub": str(entity_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "kind": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def generate_did_web(entity_id: uuid.UUID) -> str:
    return f"did:web:agentgraph.io:users:{entity_id}"


async def register_human(
    db: AsyncSession,
    email: str,
    password: str,
    display_name: str,
) -> Entity:
    entity_id = uuid.uuid4()
    entity = Entity(
        id=entity_id,
        type=EntityType.HUMAN,
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
        did_web=generate_did_web(entity_id),
    )
    db.add(entity)
    await db.flush()
    return entity


async def get_entity_by_email(db: AsyncSession, email: str) -> Entity | None:
    result = await db.execute(select(Entity).where(Entity.email == email))
    return result.scalar_one_or_none()


async def get_entity_by_id(db: AsyncSession, entity_id: uuid.UUID) -> Entity | None:
    return await db.get(Entity, entity_id)


async def authenticate_human(
    db: AsyncSession, email: str, password: str
) -> Entity | None:
    entity = await get_entity_by_email(db, email)
    if entity is None:
        # Prevent timing attacks — hash anyway
        pwd_context.dummy_verify()
        return None
    if not verify_password(password, entity.password_hash):
        return None
    if not entity.is_active:
        return None
    return entity
