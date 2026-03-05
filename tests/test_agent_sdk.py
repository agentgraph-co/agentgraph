"""Tests for the AgentGraph Agent SDK functionality.

Since the SDK is a standalone package and cannot be imported directly,
these tests exercise the same API endpoints the SDK wraps, using our
standard test infrastructure (ASGI transport, db fixture, etc.).
"""
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
AGENT_REGISTER_URL = "/api/v1/agents/register"
FEED_POSTS_URL = "/api/v1/feed/posts"
SEARCH_URL = "/api/v1/search"
TRUST_URL = "/api/v1/entities"
PROFILES_URL = "/api/v1/profiles"
EVOLUTION_URL = "/api/v1/evolution"
MARKETPLACE_URL = "/api/v1/marketplace"
ATTESTATION_URL = "/api/v1/attestations"

USER = {
    "email": "sdk_test_user@example.com",
    "password": "Str0ngP@ss!",
    "display_name": "SDKTestUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register a user, login, and return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL,
        json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


# ------------------------------------------------------------------
# SDK-equivalent: authenticate (login)
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sdk_authenticate(client):
    """SDK authenticate() calls POST /auth/login and returns a token."""
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL,
        json={"email": USER["email"], "password": USER["password"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


# ------------------------------------------------------------------
# SDK-equivalent: register_agent
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sdk_register_agent(client, db):
    """SDK register_agent() calls POST /agents/register and gets API key."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "SDKAgent"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent"]["display_name"] == "SDKAgent"
    assert data["agent"]["type"] == "agent"
    assert "api_key" in data
    assert len(data["api_key"]) > 0

    # Verify the API key works for authentication
    api_key = data["api_key"]
    me_resp = await client.get(
        "/api/v1/auth/me",
        headers={"X-API-Key": api_key},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["display_name"] == "SDKAgent"


# ------------------------------------------------------------------
# SDK-equivalent: get_trust_score
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sdk_get_trust_score(client, db):
    """SDK get_trust_score() calls GET /trust/entities/{id}/trust."""
    token, uid = await _setup_user(client, USER)
    resp = await client.get(
        f"{TRUST_URL}/{uid}/trust",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "entity_id" in data
    assert "score" in data
    assert "components" in data
    assert "computed_at" in data


# ------------------------------------------------------------------
# SDK-equivalent: create_post
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sdk_create_post(client, db):
    """SDK create_post() calls POST /feed/posts."""
    token, uid = await _setup_user(client, USER)
    resp = await client.post(
        FEED_POSTS_URL,
        json={"content": "Hello from the SDK test!"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "Hello from the SDK test!"
    assert "id" in data
    assert data["author"]["display_name"] == USER["display_name"]


# ------------------------------------------------------------------
# SDK-equivalent: get_feed
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sdk_get_feed(client, db):
    """SDK get_feed() calls GET /feed/posts with pagination."""
    token, uid = await _setup_user(client, USER)

    # Create a post first
    await client.post(
        FEED_POSTS_URL,
        json={"content": "Feed test post"},
        headers=_auth(token),
    )

    resp = await client.get(
        FEED_POSTS_URL,
        params={"limit": 20},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "posts" in data
    assert len(data["posts"]) >= 1


# ------------------------------------------------------------------
# SDK-equivalent: search_entities
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sdk_search_entities(client, db):
    """SDK search_entities() calls GET /search with query parameter."""
    token, uid = await _setup_user(client, USER)
    resp = await client.get(
        SEARCH_URL,
        params={"q": "SDKTestUser", "limit": 20},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "entities" in data
    assert "posts" in data
    assert "entity_count" in data
    assert "post_count" in data


# ------------------------------------------------------------------
# SDK-equivalent: get_profile
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sdk_get_profile(client, db):
    """SDK get_profile() calls GET /profiles/{entity_id}."""
    token, uid = await _setup_user(client, USER)
    resp = await client.get(
        f"{PROFILES_URL}/{uid}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == USER["display_name"]
    assert "trust_score" in data
    assert "did_web" in data
    assert "type" in data


# ------------------------------------------------------------------
# SDK-equivalent: get_entity (same as profile)
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sdk_get_entity(client, db):
    """SDK get_entity() calls GET /profiles/{entity_id} (same endpoint)."""
    token, uid = await _setup_user(client, USER)
    resp = await client.get(
        f"{PROFILES_URL}/{uid}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == uid
    assert data["display_name"] == USER["display_name"]


# ------------------------------------------------------------------
# SDK-equivalent: create_attestation
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sdk_create_attestation(client, db):
    """SDK create_attestation() calls POST /attestations."""
    token, uid = await _setup_user(client, USER)

    # Create a second user to attest
    other_user = {
        "email": "sdk_attest_target@example.com",
        "password": "Str0ngP@ss!",
        "display_name": "AttestTarget",
    }
    _, other_uid = await _setup_user(client, other_user)

    resp = await client.post(
        ATTESTATION_URL,
        json={
            "subject_entity_id": other_uid,
            "attestation_type": "community_endorsed",
            "evidence": "Verified competence via SDK test",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["attestation_type"] == "community_endorsed"
    assert data["subject_entity_id"] == other_uid
    assert data["evidence"] == "Verified competence via SDK test"


# ------------------------------------------------------------------
# SDK-equivalent: get_evolution_history
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sdk_get_evolution_history(client, db):
    """SDK get_evolution_history() calls GET /evolution/{entity_id}."""
    # Register an agent (evolution endpoints are for agents)
    reg_resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "EvoAgent"},
    )
    assert reg_resp.status_code == 201
    api_key = reg_resp.json()["api_key"]
    agent_id = reg_resp.json()["agent"]["id"]

    resp = await client.get(
        f"{EVOLUTION_URL}/{agent_id}",
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "records" in data


# ------------------------------------------------------------------
# SDK-equivalent: list_marketplace
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sdk_list_marketplace(client, db):
    """SDK list_marketplace() calls GET /marketplace."""
    token, uid = await _setup_user(client, USER)
    resp = await client.get(
        MARKETPLACE_URL,
        params={"limit": 20},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "listings" in data


# ------------------------------------------------------------------
# SDK-equivalent: full workflow (register agent -> post -> search)
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sdk_full_workflow(client, db):
    """End-to-end SDK workflow: register, post, and search."""
    # 1. Register a human user and authenticate
    token, uid = await _setup_user(client, USER)

    # 2. Create a post
    post_resp = await client.post(
        FEED_POSTS_URL,
        json={"content": "SDK workflow integration test"},
        headers=_auth(token),
    )
    assert post_resp.status_code == 201
    post_id = post_resp.json()["id"]

    # 3. Get the feed and verify the post is there
    feed_resp = await client.get(
        FEED_POSTS_URL,
        params={"limit": 20},
        headers=_auth(token),
    )
    assert feed_resp.status_code == 200
    post_ids = [p["id"] for p in feed_resp.json()["posts"]]
    assert post_id in post_ids

    # 4. Get trust score
    trust_resp = await client.get(
        f"{TRUST_URL}/{uid}/trust",
        headers=_auth(token),
    )
    assert trust_resp.status_code == 200
    assert trust_resp.json()["score"] >= 0

    # 5. Get profile
    profile_resp = await client.get(
        f"{PROFILES_URL}/{uid}",
        headers=_auth(token),
    )
    assert profile_resp.status_code == 200
    assert profile_resp.json()["display_name"] == USER["display_name"]

    # 6. Register an agent
    agent_resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "WorkflowBot"},
    )
    assert agent_resp.status_code == 201
    agent_api_key = agent_resp.json()["api_key"]

    # 7. Agent can authenticate and get its own profile
    me_resp = await client.get(
        "/api/v1/auth/me",
        headers={"X-API-Key": agent_api_key},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["display_name"] == "WorkflowBot"
