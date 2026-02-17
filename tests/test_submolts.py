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


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
SUBMOLTS_URL = "/api/v1/submolts"
POSTS_URL = "/api/v1/feed/posts"

USER_A = {
    "email": "submolt-a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "SubUser_A",
}
USER_B = {
    "email": "submolt-b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "SubUser_B",
}


async def _setup_user(
    client: AsyncClient, user: dict,
) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL,
        json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Create ---


@pytest.mark.asyncio
async def test_create_submolt(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        SUBMOLTS_URL,
        json={
            "name": "ai-research",
            "display_name": "AI Research",
            "description": "Discuss AI research papers",
            "tags": ["ai", "research"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "ai-research"
    assert data["display_name"] == "AI Research"
    assert data["member_count"] == 1
    assert data["is_member"] is True


@pytest.mark.asyncio
async def test_create_submolt_bad_name(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        SUBMOLTS_URL,
        json={
            "name": "A B",  # spaces not allowed
            "display_name": "Bad Name",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_submolt_duplicate(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    await client.post(
        SUBMOLTS_URL,
        json={"name": "unique-name", "display_name": "First"},
        headers=_auth(token),
    )
    resp = await client.post(
        SUBMOLTS_URL,
        json={"name": "unique-name", "display_name": "Second"},
        headers=_auth(token),
    )
    assert resp.status_code == 409


# --- Browse ---


@pytest.mark.asyncio
async def test_list_submolts(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    await client.post(
        SUBMOLTS_URL,
        json={"name": "list-test-1", "display_name": "List Test 1"},
        headers=_auth(token),
    )
    await client.post(
        SUBMOLTS_URL,
        json={"name": "list-test-2", "display_name": "List Test 2"},
        headers=_auth(token),
    )

    resp = await client.get(SUBMOLTS_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_search_submolts(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    await client.post(
        SUBMOLTS_URL,
        json={
            "name": "machine-learning",
            "display_name": "Machine Learning",
        },
        headers=_auth(token),
    )

    resp = await client.get(SUBMOLTS_URL, params={"q": "machine"})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


# --- Get ---


@pytest.mark.asyncio
async def test_get_submolt(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    await client.post(
        SUBMOLTS_URL,
        json={"name": "get-test", "display_name": "Get Test"},
        headers=_auth(token),
    )

    resp = await client.get(
        f"{SUBMOLTS_URL}/get-test", headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_member"] is True


@pytest.mark.asyncio
async def test_get_submolt_not_found(client: AsyncClient):
    resp = await client.get(f"{SUBMOLTS_URL}/nonexistent")
    assert resp.status_code == 404


# --- Join / Leave ---


@pytest.mark.asyncio
async def test_join_and_leave_submolt(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # A creates submolt
    await client.post(
        SUBMOLTS_URL,
        json={"name": "join-test", "display_name": "Join Test"},
        headers=_auth(token_a),
    )

    # B joins
    resp = await client.post(
        f"{SUBMOLTS_URL}/join-test/join", headers=_auth(token_b),
    )
    assert resp.status_code == 200

    # Check member count
    resp = await client.get(f"{SUBMOLTS_URL}/join-test")
    assert resp.json()["member_count"] == 2

    # B leaves
    resp = await client.post(
        f"{SUBMOLTS_URL}/join-test/leave", headers=_auth(token_b),
    )
    assert resp.status_code == 200

    # Count back to 1
    resp = await client.get(f"{SUBMOLTS_URL}/join-test")
    assert resp.json()["member_count"] == 1


@pytest.mark.asyncio
async def test_join_duplicate(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    await client.post(
        SUBMOLTS_URL,
        json={"name": "dup-join", "display_name": "Dup Join"},
        headers=_auth(token),
    )

    # Already a member (auto-joined on create)
    resp = await client.post(
        f"{SUBMOLTS_URL}/dup-join/join", headers=_auth(token),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_owner_cannot_leave(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    await client.post(
        SUBMOLTS_URL,
        json={"name": "owner-leave", "display_name": "Owner Leave"},
        headers=_auth(token),
    )

    resp = await client.post(
        f"{SUBMOLTS_URL}/owner-leave/leave", headers=_auth(token),
    )
    assert resp.status_code == 400


# --- Update ---


@pytest.mark.asyncio
async def test_update_submolt(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    await client.post(
        SUBMOLTS_URL,
        json={"name": "update-test", "display_name": "Before"},
        headers=_auth(token),
    )

    resp = await client.patch(
        f"{SUBMOLTS_URL}/update-test",
        json={"display_name": "After"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "After"


@pytest.mark.asyncio
async def test_update_submolt_non_owner(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    await client.post(
        SUBMOLTS_URL,
        json={"name": "no-update", "display_name": "No Update"},
        headers=_auth(token_a),
    )

    resp = await client.patch(
        f"{SUBMOLTS_URL}/no-update",
        json={"display_name": "Hacked"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 403


# --- Members ---


@pytest.mark.asyncio
async def test_list_members(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    await client.post(
        SUBMOLTS_URL,
        json={"name": "members-test", "display_name": "Members Test"},
        headers=_auth(token_a),
    )
    await client.post(
        f"{SUBMOLTS_URL}/members-test/join", headers=_auth(token_b),
    )

    resp = await client.get(f"{SUBMOLTS_URL}/members-test/members")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["members"]) == 2
    roles = {m["role"] for m in data["members"]}
    assert "owner" in roles
    assert "member" in roles


# --- Submolt Feed ---


@pytest.mark.asyncio
async def test_submolt_feed(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    # Create submolt
    resp = await client.post(
        SUBMOLTS_URL,
        json={"name": "feed-test", "display_name": "Feed Test"},
        headers=_auth(token),
    )
    submolt_id = resp.json()["id"]

    # Post to submolt
    resp = await client.post(
        POSTS_URL,
        json={
            "content": "Post in submolt",
            "submolt_id": submolt_id,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["submolt_id"] == submolt_id

    # Get submolt feed
    resp = await client.get(
        f"{SUBMOLTS_URL}/feed-test/feed", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["posts"]) == 1
    assert data["posts"][0]["content"] == "Post in submolt"
    assert data["submolt"]["is_member"] is True


@pytest.mark.asyncio
async def test_post_to_invalid_submolt(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        POSTS_URL,
        json={
            "content": "Bad submolt",
            "submolt_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 404
