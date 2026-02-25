from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient):
    """All responses include standard security headers."""
    resp = await client.get("/health")
    assert resp.status_code in (200, 503)  # 503 if Redis/DB pool stale in test suite

    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-XSS-Protection"] == "1; mode=block"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" in resp.headers["Permissions-Policy"]


@pytest.mark.asyncio
async def test_security_headers_on_api(client: AsyncClient):
    """Security headers are present on API endpoints too."""
    resp = await client.get("/api/v1/ping")
    assert resp.status_code == 200

    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


@pytest.mark.asyncio
async def test_security_headers_on_error(client: AsyncClient):
    """Security headers are present even on error responses."""
    import uuid

    resp = await client.get(f"/api/v1/profiles/{uuid.uuid4()}")
    assert resp.status_code == 404

    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
