"""Tests for Developer Hub endpoints."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_developer_hub_stats(client):
    resp = await client.get("/api/v1/developer-hub/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_agents" in data
    assert "total_frameworks" in data
    assert "total_scans" in data
    assert "framework_counts" in data
    assert data["total_frameworks"] == 8


@pytest.mark.asyncio
async def test_developer_hub_frameworks(client):
    resp = await client.get("/api/v1/developer-hub/frameworks")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 8

    # Verify framework structure
    fw = data[0]
    assert "key" in fw
    assert "display_name" in fw
    assert "tagline" in fw
    assert "badge_color" in fw
    assert "trust_modifier" in fw
    assert "quick_start_curl" in fw
    assert "quick_start_python" in fw
    assert "docs_url" in fw

    # Verify all expected frameworks are present
    keys = {f["key"] for f in data}
    assert keys == {
        "native", "mcp", "langchain", "crewai",
        "autogen", "pydantic_ai", "nanoclaw", "openclaw",
    }
