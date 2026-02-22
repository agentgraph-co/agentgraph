"""Tests for bridge discovery and health endpoints."""
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
async def test_bridge_discover(client: AsyncClient):
    """Discovery endpoint returns all frameworks with capabilities."""
    resp = await client.get("/api/v1/bridges/discover")
    assert resp.status_code == 200
    data = resp.json()
    assert "frameworks" in data
    framework_names = [f["framework"] for f in data["frameworks"]]
    assert "mcp" in framework_names
    assert "openclaw" in framework_names
    assert "langchain" in framework_names
    assert "crewai" in framework_names
    assert "autogen" in framework_names
    assert "semantic_kernel" in framework_names
    # Each framework should have capabilities and import_schema
    for fw in data["frameworks"]:
        assert "capabilities" in fw
        assert isinstance(fw["capabilities"], list)
        assert len(fw["capabilities"]) > 0
        assert "import_schema" in fw
        assert "status" in fw


@pytest.mark.asyncio
async def test_bridge_health(client: AsyncClient):
    """Health endpoint returns status for all bridge modules."""
    resp = await client.get("/api/v1/bridges/health")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    framework_names = [h["framework"] for h in data]
    assert "mcp" in framework_names
    assert "openclaw" in framework_names
    assert "langchain" in framework_names
    assert "crewai" in framework_names
    assert "autogen" in framework_names
    assert "semantic_kernel" in framework_names
    # Each should have status, module_loaded, version
    for h in data:
        assert "status" in h
        assert h["status"] in ("healthy", "unhealthy")
        assert "module_loaded" in h
        assert isinstance(h["module_loaded"], bool)
        assert "version" in h


@pytest.mark.asyncio
async def test_bridge_status_includes_new_frameworks(client: AsyncClient):
    """Bridge status should include autogen and semantic_kernel."""
    resp = await client.get("/api/v1/bridges/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "autogen" in data["supported_frameworks"]
    assert "semantic_kernel" in data["supported_frameworks"]


@pytest.mark.asyncio
async def test_discover_import_schemas_valid(client: AsyncClient):
    """Each framework's import schema should be a valid JSON Schema object."""
    resp = await client.get("/api/v1/bridges/discover")
    assert resp.status_code == 200
    data = resp.json()
    for fw in data["frameworks"]:
        schema = fw["import_schema"]
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema


@pytest.mark.asyncio
async def test_health_all_modules_loaded(client: AsyncClient):
    """All bridge modules should be loaded (healthy) in the test environment."""
    resp = await client.get("/api/v1/bridges/health")
    assert resp.status_code == 200
    data = resp.json()
    for h in data:
        assert h["module_loaded"] is True, f"{h['framework']} module not loaded"
        assert h["status"] == "healthy", f"{h['framework']} not healthy"
