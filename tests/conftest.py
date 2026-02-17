from __future__ import annotations

import os

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://localhost:5432/agentgraph"
)


@pytest_asyncio.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear rate limiter state before every test."""
    from src.api.rate_limit import _limiter

    _limiter._windows.clear()
    yield
    _limiter._windows.clear()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DB_URL, echo=False)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
    await engine.dispose()
