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

USER = {
    "email": "onboard_user@test.com",
    "password": "Str0ngP@ss",
    "display_name": "OnboardUser",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
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


# --- Paths ---


@pytest.mark.asyncio
async def test_get_paths(client):
    resp = await client.get("/api/v1/onboarding/paths")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["paths"]) == 3
    keys = {p["key"] for p in data["paths"]}
    assert keys == {"human_user", "agent_developer", "enterprise"}


# --- Status ---


@pytest.mark.asyncio
async def test_status_requires_auth(client):
    resp = await client.get("/api/v1/onboarding/status")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_status_default(client):
    token, uid = await _setup_user(client, USER)
    resp = await client.get(
        "/api/v1/onboarding/status", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == uid
    assert data["path"] == "human_user"
    assert data["total_steps"] == 5
    assert data["completed_count"] >= 0
    assert isinstance(data["steps"], list)


# --- Set Path ---


@pytest.mark.asyncio
async def test_set_path(client):
    token, _ = await _setup_user(client, USER)
    resp = await client.post(
        "/api/v1/onboarding/set-path",
        json={"path": "agent_developer"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == "agent_developer"
    assert data["total_steps"] == 5


@pytest.mark.asyncio
async def test_set_invalid_path(client):
    token, _ = await _setup_user(client, USER)
    resp = await client.post(
        "/api/v1/onboarding/set-path",
        json={"path": "invalid_path"},
        headers=_auth(token),
    )
    assert resp.status_code == 400


# --- Complete Step ---


@pytest.mark.asyncio
async def test_complete_step(client):
    token, _ = await _setup_user(client, USER)
    resp = await client.post(
        "/api/v1/onboarding/complete-step",
        json={"step_key": "explore_trust"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_key"] == "explore_trust"
    assert data["completed"] is True

    # Verify it shows in status
    status_resp = await client.get(
        "/api/v1/onboarding/status", headers=_auth(token),
    )
    steps = status_resp.json()["steps"]
    trust_step = next(s for s in steps if s["key"] == "explore_trust")
    assert trust_step["completed"] is True


@pytest.mark.asyncio
async def test_complete_invalid_step(client):
    token, _ = await _setup_user(client, USER)
    resp = await client.post(
        "/api/v1/onboarding/complete-step",
        json={"step_key": "nonexistent_step"},
        headers=_auth(token),
    )
    assert resp.status_code == 400


# --- Auto-detect ---


@pytest.mark.asyncio
async def test_auto_detect_first_post(client):
    token, _ = await _setup_user(client, USER)

    # Create a post
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Onboarding first post!"},
        headers=_auth(token),
    )

    resp = await client.get(
        "/api/v1/onboarding/status", headers=_auth(token),
    )
    data = resp.json()
    post_step = next(s for s in data["steps"] if s["key"] == "first_post")
    assert post_step["completed"] is True


@pytest.mark.asyncio
async def test_auto_detect_first_follow(client):
    token_a, _ = await _setup_user(client, USER)

    # Register user B to follow
    user_b = {
        "email": "onboard_b@test.com",
        "password": "Str0ngP@ss",
        "display_name": "OnboardB",
    }
    _, b_id = await _setup_user(client, user_b)

    # Follow user B
    await client.post(
        f"/api/v1/social/follow/{b_id}",
        headers=_auth(token_a),
    )

    resp = await client.get(
        "/api/v1/onboarding/status", headers=_auth(token_a),
    )
    data = resp.json()
    follow_step = next(s for s in data["steps"] if s["key"] == "first_follow")
    assert follow_step["completed"] is True


# --- Reset ---


@pytest.mark.asyncio
async def test_reset_onboarding(client):
    token, _ = await _setup_user(client, USER)

    # Set a path and complete a step
    await client.post(
        "/api/v1/onboarding/set-path",
        json={"path": "enterprise"},
        headers=_auth(token),
    )
    await client.post(
        "/api/v1/onboarding/complete-step",
        json={"step_key": "verify_email"},
        headers=_auth(token),
    )

    # Reset
    resp = await client.post(
        "/api/v1/onboarding/reset",
        headers=_auth(token),
    )
    assert resp.status_code == 200

    # Verify path reverted to default
    status_resp = await client.get(
        "/api/v1/onboarding/status", headers=_auth(token),
    )
    data = status_resp.json()
    assert data["path"] == "human_user"


# --- Idempotent complete ---


@pytest.mark.asyncio
async def test_complete_step_idempotent(client):
    token, _ = await _setup_user(client, USER)

    # Complete same step twice
    resp1 = await client.post(
        "/api/v1/onboarding/complete-step",
        json={"step_key": "verify_email"},
        headers=_auth(token),
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        "/api/v1/onboarding/complete-step",
        json={"step_key": "verify_email"},
        headers=_auth(token),
    )
    assert resp2.status_code == 200
