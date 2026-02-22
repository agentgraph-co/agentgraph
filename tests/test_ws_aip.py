"""Tests for AIP and expanded WebSocket channels.

Verifies that the AIP channel is accepted, all expected channels
are present, and AIP REST endpoints work correctly alongside
the WebSocket broadcast infrastructure.
"""
from __future__ import annotations

import uuid

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


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
AIP_URL = "/api/v1/aip"


async def _setup_user(
    client: AsyncClient, email: str, name: str,
) -> tuple[str, str]:
    """Register a user and return (token, entity_id)."""
    await client.post(
        REGISTER_URL,
        json={"email": email, "password": "Str0ngP@ss!", "display_name": name},
    )
    resp = await client.post(
        LOGIN_URL, json={"email": email, "password": "Str0ngP@ss!"},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_aip_channel_in_valid_channels():
    """Test that 'aip' is a valid WS channel."""
    import inspect

    from src.api import ws_router

    source = inspect.getsource(ws_router.websocket_endpoint)
    assert '"aip"' in source or "'aip'" in source


@pytest.mark.asyncio
async def test_valid_channels_complete():
    """Verify all expected channels are in valid_channels set."""
    import inspect

    from src.api import ws_router

    source = inspect.getsource(ws_router.websocket_endpoint)
    expected_channels = [
        "feed", "notifications", "activity", "aip",
        "messages", "marketplace", "disputes",
    ]
    for ch in expected_channels:
        assert f'"{ch}"' in source or f"'{ch}'" in source, (
            f"Channel '{ch}' not found in ws_router valid_channels"
        )


@pytest.mark.asyncio
async def test_valid_channels_count():
    """Verify exactly 7 channels are in the valid_channels set."""
    import inspect
    import re

    from src.api import ws_router

    source = inspect.getsource(ws_router.websocket_endpoint)
    # Find the valid_channels = {...} set (may span multiple lines)
    match = re.search(r'valid_channels\s*=\s*\{([^}]+)\}', source, re.DOTALL)
    assert match is not None, "valid_channels set not found"
    channels_str = match.group(1)
    # Count quoted strings
    channel_names = re.findall(r'"(\w+)"', channels_str)
    assert len(channel_names) == 7, (
        f"Expected 7 channels, found {len(channel_names)}: {channel_names}"
    )


@pytest.mark.asyncio
async def test_aip_discover_endpoint(client: AsyncClient):
    """AIP discover endpoint works without WS issues."""
    token, entity_id = await _setup_user(
        client, f"aipws1-{uuid.uuid4().hex[:6]}@t.com", "AIPAgent1",
    )

    resp = await client.get(
        f"{AIP_URL}/discover",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data


@pytest.mark.asyncio
async def test_capability_register_no_ws_failure(client: AsyncClient):
    """Capability registration works without WS issues."""
    token, entity_id = await _setup_user(
        client, f"aipws2-{uuid.uuid4().hex[:6]}@t.com", "AIPAgent2",
    )

    # Register a capability for the current entity
    resp = await client.post(
        f"{AIP_URL}/capabilities",
        json={
            "capability_name": "text_summarization",
            "version": "1.0.0",
            "description": "Summarize text documents",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
            },
        },
        headers=_auth(token),
    )
    # Accept 201 (created) or 409 (duplicate) - not 500
    assert resp.status_code < 500


@pytest.mark.asyncio
async def test_aip_capabilities_list(client: AsyncClient):
    """AIP capabilities listing works without WS issues."""
    token, entity_id = await _setup_user(
        client, f"aipws3-{uuid.uuid4().hex[:6]}@t.com", "AIPAgent3",
    )

    resp = await client.get(
        f"{AIP_URL}/capabilities/{entity_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "capabilities" in data


@pytest.mark.asyncio
async def test_disputes_channel_broadcasts_on_router():
    """Verify disputes_router uses 'disputes' channel for WS broadcasts."""
    import inspect

    from src.api import disputes_router

    source = inspect.getsource(disputes_router)
    assert '"disputes"' in source, "disputes_router should broadcast on 'disputes' channel"


@pytest.mark.asyncio
async def test_marketplace_router_broadcasts_on_channel():
    """Verify marketplace_router uses 'marketplace' channel for WS broadcasts."""
    import inspect

    from src.api import marketplace_router

    source = inspect.getsource(marketplace_router)
    # Should have marketplace channel broadcasts for listing_created and purchase
    assert '"listing_created"' in source, "marketplace_router should broadcast listing_created"
    assert '"purchase"' in source, "marketplace_router should broadcast purchase event"
    assert '"transaction_cancelled"' in source, (
        "marketplace_router should broadcast transaction_cancelled"
    )


@pytest.mark.asyncio
async def test_ws_manager_send_to_entity_no_connections():
    """Verify ws manager send_to_entity handles no active connections gracefully."""
    from src.ws import manager

    # No connections should result in 0 sent but no error
    sent = await manager.send_to_entity("nonexistent-id", "marketplace", {
        "type": "test",
        "data": "test_value",
    })
    assert sent == 0


@pytest.mark.asyncio
async def test_ws_manager_broadcast_to_channel_no_connections():
    """Verify ws manager broadcast_to_channel handles no active connections gracefully."""
    from src.ws import manager

    sent = await manager.broadcast_to_channel("disputes", {
        "type": "test",
        "data": "test_value",
    })
    assert sent == 0
