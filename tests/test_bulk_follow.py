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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(
    client: AsyncClient, email: str, name: str,
) -> tuple[str, str]:
    await client.post(
        REGISTER_URL,
        json={"email": email, "password": "Str0ngP@ss", "display_name": name},
    )
    resp = await client.post(
        LOGIN_URL, json={"email": email, "password": "Str0ngP@ss"},
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


@pytest.mark.asyncio
async def test_bulk_follow_multiple(client: AsyncClient, db):
    """Bulk follow creates relationships for valid targets."""
    token_a, _ = await _setup_user(client, "bf_a@test.com", "BulkA")
    _, id_b = await _setup_user(client, "bf_b@test.com", "BulkB")
    _, id_c = await _setup_user(client, "bf_c@test.com", "BulkC")

    resp = await client.post(
        "/api/v1/social/bulk-follow",
        json={"entity_ids": [id_b, id_c]},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["followed"] == 2
    assert len(data["results"]) == 2
    assert all(r["status"] == "followed" for r in data["results"])


@pytest.mark.asyncio
async def test_bulk_follow_skips_self(client: AsyncClient, db):
    """Bulk follow skips self in the list."""
    token_a, id_a = await _setup_user(client, "bfs_a@test.com", "BfSelfA")
    _, id_b = await _setup_user(client, "bfs_b@test.com", "BfSelfB")

    resp = await client.post(
        "/api/v1/social/bulk-follow",
        json={"entity_ids": [id_a, id_b]},
        headers=_auth(token_a),
    )
    data = resp.json()
    assert data["followed"] == 1
    statuses = {r["id"]: r["status"] for r in data["results"]}
    assert statuses[id_a] == "skipped"
    assert statuses[id_b] == "followed"


@pytest.mark.asyncio
async def test_bulk_follow_already_following(client: AsyncClient, db):
    """Bulk follow reports already-following status."""
    token_a, _ = await _setup_user(client, "bfaf_a@test.com", "BfAfA")
    _, id_b = await _setup_user(client, "bfaf_b@test.com", "BfAfB")

    # Follow first
    await client.post(
        f"/api/v1/social/follow/{id_b}", headers=_auth(token_a),
    )

    # Bulk follow includes the already-followed target
    resp = await client.post(
        "/api/v1/social/bulk-follow",
        json={"entity_ids": [id_b]},
        headers=_auth(token_a),
    )
    data = resp.json()
    assert data["followed"] == 0
    assert data["results"][0]["status"] == "already_following"


@pytest.mark.asyncio
async def test_bulk_follow_blocked(client: AsyncClient, db):
    """Bulk follow reports blocked status when target blocks the user."""
    token_a, id_a = await _setup_user(client, "bfbl_a@test.com", "BfBlA")
    token_b, id_b = await _setup_user(client, "bfbl_b@test.com", "BfBlB")

    # B blocks A
    await client.post(
        f"/api/v1/social/block/{id_a}", headers=_auth(token_b),
    )

    resp = await client.post(
        "/api/v1/social/bulk-follow",
        json={"entity_ids": [id_b]},
        headers=_auth(token_a),
    )
    data = resp.json()
    assert data["followed"] == 0
    assert data["results"][0]["status"] == "blocked"


@pytest.mark.asyncio
async def test_bulk_follow_not_found(client: AsyncClient, db):
    """Bulk follow reports not_found for nonexistent entities."""
    token_a, _ = await _setup_user(client, "bfnf_a@test.com", "BfNfA")

    resp = await client.post(
        "/api/v1/social/bulk-follow",
        json={"entity_ids": [str(uuid.uuid4())]},
        headers=_auth(token_a),
    )
    data = resp.json()
    assert data["followed"] == 0
    assert data["results"][0]["status"] == "not_found"


@pytest.mark.asyncio
async def test_bulk_unfollow(client: AsyncClient, db):
    """Bulk unfollow removes follow relationships."""
    token_a, _ = await _setup_user(client, "bfu_a@test.com", "BfuA")
    _, id_b = await _setup_user(client, "bfu_b@test.com", "BfuB")
    _, id_c = await _setup_user(client, "bfu_c@test.com", "BfuC")

    # Follow both
    await client.post(
        f"/api/v1/social/follow/{id_b}", headers=_auth(token_a),
    )
    await client.post(
        f"/api/v1/social/follow/{id_c}", headers=_auth(token_a),
    )

    # Bulk unfollow
    resp = await client.post(
        "/api/v1/social/bulk-unfollow",
        json={"entity_ids": [id_b, id_c]},
        headers=_auth(token_a),
    )
    data = resp.json()
    assert data["unfollowed"] == 2
    assert all(r["status"] == "unfollowed" for r in data["results"])


@pytest.mark.asyncio
async def test_bulk_unfollow_not_following(client: AsyncClient, db):
    """Bulk unfollow reports not_following for entities not being followed."""
    token_a, _ = await _setup_user(client, "bfunf_a@test.com", "BfuNfA")
    _, id_b = await _setup_user(client, "bfunf_b@test.com", "BfuNfB")

    resp = await client.post(
        "/api/v1/social/bulk-unfollow",
        json={"entity_ids": [id_b]},
        headers=_auth(token_a),
    )
    data = resp.json()
    assert data["unfollowed"] == 0
    assert data["results"][0]["status"] == "not_following"
