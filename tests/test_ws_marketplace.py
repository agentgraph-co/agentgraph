"""Tests for marketplace WebSocket channel expansion.

Verifies that the marketplace channel is accepted by the WebSocket
endpoint and that marketplace REST endpoints work correctly with
best-effort WS broadcasting (no active WS connections needed).
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
MARKET_URL = "/api/v1/marketplace"

LISTING = {
    "title": "WS Test Listing Service",
    "description": "A service created to test marketplace WS broadcasts",
    "category": "service",
    "tags": ["ws", "test"],
    "pricing_model": "free",
    "price_cents": 0,
}


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


async def _grant_trust(db, entity_id: str, score: float = 0.5):
    import uuid as _uuid
    from src.models import TrustScore
    ts = TrustScore(id=_uuid.uuid4(), entity_id=entity_id, score=score, components={})
    db.add(ts)
    await db.flush()


@pytest.mark.asyncio
async def test_marketplace_channel_in_valid_channels():
    """Verify 'marketplace' is in the ws_router valid_channels set."""
    import inspect

    from src.api import ws_router

    source = inspect.getsource(ws_router.websocket_endpoint)
    assert '"marketplace"' in source or "'marketplace'" in source


@pytest.mark.asyncio
async def test_disputes_channel_in_valid_channels():
    """Verify 'disputes' is in the ws_router valid_channels set."""
    import inspect

    from src.api import ws_router

    source = inspect.getsource(ws_router.websocket_endpoint)
    assert '"disputes"' in source or "'disputes'" in source


@pytest.mark.asyncio
async def test_messages_channel_in_valid_channels():
    """Verify 'messages' is in the ws_router valid_channels set."""
    import inspect

    from src.api import ws_router

    source = inspect.getsource(ws_router.websocket_endpoint)
    assert '"messages"' in source or "'messages'" in source


@pytest.mark.asyncio
async def test_all_expected_channels_present():
    """Verify all 7 expected channels are present in ws_router source."""
    import inspect

    from src.api import ws_router

    source = inspect.getsource(ws_router.websocket_endpoint)
    expected = ["feed", "notifications", "activity", "aip", "messages", "marketplace", "disputes"]
    for channel in expected:
        assert f'"{channel}"' in source or f"'{channel}'" in source, (
            f"Channel '{channel}' not found in ws_router"
        )


@pytest.mark.asyncio
async def test_listing_create_broadcasts(client: AsyncClient, db):
    """Verify listing creation doesn't fail with marketplace WS broadcast."""
    token, entity_id = await _setup_user(client, f"wsm1-{uuid.uuid4().hex[:6]}@t.com", "WSMSeller1")
    await _grant_trust(db, entity_id)

    resp = await client.post(MARKET_URL, json=LISTING, headers=_auth(token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == LISTING["title"]
    assert data["category"] == "service"


@pytest.mark.asyncio
async def test_purchase_broadcasts_marketplace_event(client: AsyncClient, db):
    """Verify purchase doesn't fail with marketplace WS broadcast."""
    seller_token, seller_id = await _setup_user(
        client, f"wsm2-{uuid.uuid4().hex[:6]}@t.com", "WSMSeller2",
    )
    buyer_token, buyer_id = await _setup_user(
        client, f"wsm3-{uuid.uuid4().hex[:6]}@t.com", "WSMBuyer1",
    )
    await _grant_trust(db, seller_id)

    # Create listing
    resp = await client.post(MARKET_URL, json=LISTING, headers=_auth(seller_token))
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    # Purchase (free)
    resp = await client.post(
        f"{MARKET_URL}/{listing_id}/purchase",
        json={"notes": "WS broadcast test purchase"},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_cancel_transaction_broadcasts(client: AsyncClient, db):
    """Verify cancel doesn't fail with marketplace WS broadcast."""
    seller_token, seller_id = await _setup_user(
        client, f"wsm4-{uuid.uuid4().hex[:6]}@t.com", "WSMSeller3",
    )
    buyer_token, _ = await _setup_user(
        client, f"wsm5-{uuid.uuid4().hex[:6]}@t.com", "WSMBuyer2",
    )
    await _grant_trust(db, seller_id)

    # Create a paid listing
    paid_listing = {**LISTING, "pricing_model": "one_time", "price_cents": 1000}
    resp = await client.post(MARKET_URL, json=paid_listing, headers=_auth(seller_token))
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    # Purchase (will be pending since Stripe is not configured)
    resp = await client.post(
        f"{MARKET_URL}/{listing_id}/purchase",
        json={"notes": "cancel test"},
        headers=_auth(buyer_token),
    )
    # 503 if stripe not configured, 201 if it is
    if resp.status_code == 201:
        txn_id = resp.json()["id"]

        # Cancel the pending transaction
        resp = await client.patch(
            f"{MARKET_URL}/purchases/{txn_id}/cancel",
            headers=_auth(buyer_token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
    else:
        # Stripe not configured - that's fine, confirms Stripe gate works
        assert resp.status_code == 503


@pytest.mark.asyncio
async def test_browse_after_ws_listing_create(client: AsyncClient, db):
    """Verify browsing works after listing created with WS broadcast."""
    token, entity_id = await _setup_user(
        client, f"wsm6-{uuid.uuid4().hex[:6]}@t.com", "WSMBrowse",
    )
    await _grant_trust(db, entity_id)

    # Create a listing (triggers WS broadcast)
    resp = await client.post(MARKET_URL, json=LISTING, headers=_auth(token))
    assert resp.status_code == 201

    # Browse should include it
    resp = await client.get(MARKET_URL)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_listing_update_does_not_break(client: AsyncClient, db):
    """Verify listing update works (no WS broadcast needed, but no regression)."""
    token, entity_id = await _setup_user(
        client, f"wsm7-{uuid.uuid4().hex[:6]}@t.com", "WSMUpdate",
    )
    await _grant_trust(db, entity_id)

    resp = await client.post(MARKET_URL, json=LISTING, headers=_auth(token))
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    resp = await client.patch(
        f"{MARKET_URL}/{listing_id}",
        json={"title": "Updated WS Test"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated WS Test"


@pytest.mark.asyncio
async def test_my_listings_works_after_ws_broadcast(client: AsyncClient, db):
    """Verify my-listings endpoint works after WS-broadcast listing creation."""
    token, entity_id = await _setup_user(
        client, f"wsm8-{uuid.uuid4().hex[:6]}@t.com", "WSMMyList",
    )
    await _grant_trust(db, entity_id)

    await client.post(MARKET_URL, json=LISTING, headers=_auth(token))

    resp = await client.get(
        f"{MARKET_URL}/my-listings", headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
