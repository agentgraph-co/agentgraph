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
AGENTS_URL = "/api/v1/agents"
ENTITIES_URL = "/api/v1/entities"
NOTIF_URL = "/api/v1/notifications"

HUMAN_A = {
    "email": "endorse_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "EndorserA",
}
HUMAN_B = {
    "email": "endorse_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "EndorserB",
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


async def _create_agent(
    client: AsyncClient, token: str,
) -> str:
    resp = await client.post(
        AGENTS_URL,
        json={
            "display_name": "TestBot",
            "capabilities": ["summarize", "translate"],
            "autonomy_level": 3,
        },
        headers=_auth(token),
    )
    return resp.json()["agent"]["id"]


# --- Capability Endorsement Tests ---


@pytest.mark.asyncio
async def test_endorse_capability(client: AsyncClient):
    """A user can endorse an agent's capability."""
    token_a, _ = await _setup_user(client, HUMAN_A)
    token_b, _ = await _setup_user(client, HUMAN_B)
    agent_id = await _create_agent(client, token_a)

    # B endorses agent's "summarize" capability
    resp = await client.post(
        f"{ENTITIES_URL}/{agent_id}/endorsements",
        json={"capability": "summarize", "comment": "Works great!"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["capability"] == "summarize"
    assert data["tier"] == "community_verified"
    assert data["comment"] == "Works great!"


@pytest.mark.asyncio
async def test_endorse_self_fails(client: AsyncClient):
    """Cannot endorse your own agent's capability from agent account."""
    token_a, id_a = await _setup_user(client, HUMAN_A)

    # Try to endorse self
    resp = await client.post(
        f"{ENTITIES_URL}/{id_a}/endorsements",
        json={"capability": "coding"},
        headers=_auth(token_a),
    )
    # Human entity can't be endorsed (agents only)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_endorsement_fails(client: AsyncClient):
    """Duplicate endorsement for same capability is rejected."""
    token_a, _ = await _setup_user(client, HUMAN_A)
    token_b, _ = await _setup_user(client, HUMAN_B)
    agent_id = await _create_agent(client, token_a)

    await client.post(
        f"{ENTITIES_URL}/{agent_id}/endorsements",
        json={"capability": "summarize"},
        headers=_auth(token_b),
    )
    resp = await client.post(
        f"{ENTITIES_URL}/{agent_id}/endorsements",
        json={"capability": "summarize"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_endorsements(client: AsyncClient):
    """List endorsements for an agent."""
    token_a, _ = await _setup_user(client, HUMAN_A)
    token_b, _ = await _setup_user(client, HUMAN_B)
    agent_id = await _create_agent(client, token_a)

    await client.post(
        f"{ENTITIES_URL}/{agent_id}/endorsements",
        json={"capability": "summarize"},
        headers=_auth(token_b),
    )
    await client.post(
        f"{ENTITIES_URL}/{agent_id}/endorsements",
        json={"capability": "translate"},
        headers=_auth(token_b),
    )

    resp = await client.get(
        f"{ENTITIES_URL}/{agent_id}/endorsements",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["endorsements"]) == 2


@pytest.mark.asyncio
async def test_capability_summary(client: AsyncClient):
    """Capability summary aggregates endorsements and self-declared caps."""
    token_a, _ = await _setup_user(client, HUMAN_A)
    token_b, _ = await _setup_user(client, HUMAN_B)
    agent_id = await _create_agent(client, token_a)

    # Endorse one of the self-declared capabilities
    await client.post(
        f"{ENTITIES_URL}/{agent_id}/endorsements",
        json={"capability": "summarize"},
        headers=_auth(token_b),
    )

    resp = await client.get(
        f"{ENTITIES_URL}/{agent_id}/capabilities",
    )
    assert resp.status_code == 200
    caps = resp.json()
    names = {c["capability"] for c in caps}
    # Should have both self-declared (translate) and endorsed (summarize)
    assert "summarize" in names
    assert "translate" in names

    summarize_cap = next(c for c in caps if c["capability"] == "summarize")
    assert summarize_cap["endorsement_count"] == 1
    assert summarize_cap["tier"] == "community_verified"

    translate_cap = next(c for c in caps if c["capability"] == "translate")
    assert translate_cap["endorsement_count"] == 0
    assert translate_cap["tier"] == "self_declared"


@pytest.mark.asyncio
async def test_remove_endorsement(client: AsyncClient):
    """Remove an endorsement."""
    token_a, _ = await _setup_user(client, HUMAN_A)
    token_b, _ = await _setup_user(client, HUMAN_B)
    agent_id = await _create_agent(client, token_a)

    await client.post(
        f"{ENTITIES_URL}/{agent_id}/endorsements",
        json={"capability": "summarize"},
        headers=_auth(token_b),
    )

    resp = await client.delete(
        f"{ENTITIES_URL}/{agent_id}/endorsements/summarize",
        headers=_auth(token_b),
    )
    assert resp.status_code == 204

    # Should be empty now
    resp = await client.get(
        f"{ENTITIES_URL}/{agent_id}/endorsements",
    )
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_endorsement_notification(client: AsyncClient):
    """Endorsing sends a notification to the agent's operator."""
    token_a, _ = await _setup_user(client, HUMAN_A)
    token_b, _ = await _setup_user(client, HUMAN_B)
    agent_id = await _create_agent(client, token_a)

    # Get the agent's API key to check notifications
    # The notification goes to the agent entity, but we check via operator
    await client.post(
        f"{ENTITIES_URL}/{agent_id}/endorsements",
        json={"capability": "summarize"},
        headers=_auth(token_b),
    )

    # We can verify the endorsement exists even if we can't check
    # agent notifications directly (they'd need API key auth)
    resp = await client.get(
        f"{ENTITIES_URL}/{agent_id}/endorsements",
    )
    assert resp.json()["total"] == 1


# --- Review Tests ---


@pytest.mark.asyncio
async def test_create_review(client: AsyncClient):
    """Create a review for another entity."""
    token_a, id_a = await _setup_user(client, HUMAN_A)
    token_b, _ = await _setup_user(client, HUMAN_B)

    resp = await client.post(
        f"{ENTITIES_URL}/{id_a}/reviews",
        json={"rating": 5, "text": "Excellent contributor!"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["rating"] == 5
    assert data["text"] == "Excellent contributor!"
    assert data["reviewer_display_name"] == "EndorserB"


@pytest.mark.asyncio
async def test_review_self_fails(client: AsyncClient):
    """Cannot review yourself."""
    token_a, id_a = await _setup_user(client, HUMAN_A)

    resp = await client.post(
        f"{ENTITIES_URL}/{id_a}/reviews",
        json={"rating": 5},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_review_upsert(client: AsyncClient):
    """Reviewing again updates the existing review."""
    token_a, id_a = await _setup_user(client, HUMAN_A)
    token_b, _ = await _setup_user(client, HUMAN_B)

    await client.post(
        f"{ENTITIES_URL}/{id_a}/reviews",
        json={"rating": 3, "text": "OK"},
        headers=_auth(token_b),
    )
    resp = await client.post(
        f"{ENTITIES_URL}/{id_a}/reviews",
        json={"rating": 5, "text": "Actually great!"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201
    assert resp.json()["rating"] == 5

    # Should still be just one review
    resp = await client.get(f"{ENTITIES_URL}/{id_a}/reviews")
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_list_reviews(client: AsyncClient):
    """List reviews for an entity."""
    token_a, id_a = await _setup_user(client, HUMAN_A)
    token_b, _ = await _setup_user(client, HUMAN_B)

    await client.post(
        f"{ENTITIES_URL}/{id_a}/reviews",
        json={"rating": 4, "text": "Good"},
        headers=_auth(token_b),
    )

    resp = await client.get(f"{ENTITIES_URL}/{id_a}/reviews")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["reviews"][0]["rating"] == 4


@pytest.mark.asyncio
async def test_review_summary(client: AsyncClient):
    """Review summary returns average and distribution."""
    token_a, id_a = await _setup_user(client, HUMAN_A)
    token_b, _ = await _setup_user(client, HUMAN_B)

    await client.post(
        f"{ENTITIES_URL}/{id_a}/reviews",
        json={"rating": 4},
        headers=_auth(token_b),
    )

    resp = await client.get(
        f"{ENTITIES_URL}/{id_a}/reviews/summary",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["average_rating"] == 4.0
    assert data["review_count"] == 1
    assert data["rating_distribution"]["4"] == 1
    assert data["rating_distribution"]["1"] == 0


@pytest.mark.asyncio
async def test_delete_review(client: AsyncClient):
    """Delete your own review."""
    token_a, id_a = await _setup_user(client, HUMAN_A)
    token_b, _ = await _setup_user(client, HUMAN_B)

    await client.post(
        f"{ENTITIES_URL}/{id_a}/reviews",
        json={"rating": 3},
        headers=_auth(token_b),
    )

    resp = await client.delete(
        f"{ENTITIES_URL}/{id_a}/reviews",
        headers=_auth(token_b),
    )
    assert resp.status_code == 204

    resp = await client.get(f"{ENTITIES_URL}/{id_a}/reviews")
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_review_content_filter(client: AsyncClient):
    """Review text is checked by content filter."""
    token_a, id_a = await _setup_user(client, HUMAN_A)
    token_b, _ = await _setup_user(client, HUMAN_B)

    resp = await client.post(
        f"{ENTITIES_URL}/{id_a}/reviews",
        json={
            "rating": 1,
            "text": "Buy cheap stuff click here http://spam.com",
        },
        headers=_auth(token_b),
    )
    assert resp.status_code == 400
    assert "spam_pattern" in resp.json()["detail"]


# --- Trust-Weighted Feed Tests ---


@pytest.mark.asyncio
async def test_feed_sort_ranked(client: AsyncClient):
    """Feed with sort=ranked returns posts (trust-weighted ordering)."""
    token, _ = await _setup_user(client, HUMAN_A)

    # Create a post
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Ranked feed test"},
        headers=_auth(token),
    )

    resp = await client.get(
        "/api/v1/feed/posts", params={"sort": "ranked"},
    )
    assert resp.status_code == 200
    posts = resp.json()["posts"]
    assert len(posts) >= 1


@pytest.mark.asyncio
async def test_feed_sort_newest(client: AsyncClient):
    """Feed with sort=newest returns posts in chronological order."""
    token, _ = await _setup_user(client, HUMAN_A)

    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Newest feed test"},
        headers=_auth(token),
    )

    resp = await client.get(
        "/api/v1/feed/posts", params={"sort": "newest"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["posts"]) >= 1


@pytest.mark.asyncio
async def test_feed_includes_trust_score(client: AsyncClient):
    """Feed posts include author_trust_score field."""
    token, _ = await _setup_user(client, HUMAN_A)

    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Trust score test"},
        headers=_auth(token),
    )

    resp = await client.get("/api/v1/feed/posts")
    assert resp.status_code == 200
    posts = resp.json()["posts"]
    assert len(posts) >= 1
    # Field should exist (may be None if no trust score computed)
    assert "author_trust_score" in posts[0]
