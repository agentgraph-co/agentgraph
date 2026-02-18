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
    "email": "profile@example.com",
    "password": "Str0ngP@ss",
    "display_name": "ProfileUser",
}


async def _register_and_login(client: AsyncClient) -> tuple[str, str]:
    """Register, login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=USER)
    login_resp = await client.post(
        LOGIN_URL,
        json={"email": USER["email"], "password": USER["password"]},
    )
    token = login_resp.json()["access_token"]
    me_resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    entity_id = me_resp.json()["id"]
    return token, entity_id


@pytest.mark.asyncio
async def test_get_profile_public(client: AsyncClient):
    token, entity_id = await _register_and_login(client)

    # Access without auth
    resp = await client.get(f"/api/v1/profiles/{entity_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "ProfileUser"
    assert data["is_own_profile"] is False


@pytest.mark.asyncio
async def test_get_profile_own(client: AsyncClient):
    token, entity_id = await _register_and_login(client)

    resp = await client.get(
        f"/api/v1/profiles/{entity_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_own_profile"] is True


@pytest.mark.asyncio
async def test_update_profile(client: AsyncClient):
    token, entity_id = await _register_and_login(client)

    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"bio_markdown": "# Hello\nI am a developer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["bio_markdown"] == "# Hello\nI am a developer"


@pytest.mark.asyncio
async def test_update_profile_not_owner(client: AsyncClient):
    token, entity_id = await _register_and_login(client)

    # Register another user
    other = {
        "email": "other@example.com",
        "password": "Str0ngP@ss",
        "display_name": "Other",
    }
    await client.post(REGISTER_URL, json=other)
    other_resp = await client.post(
        LOGIN_URL,
        json={"email": other["email"], "password": other["password"]},
    )
    other_token = other_resp.json()["access_token"]

    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"bio_markdown": "Hacked!"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_trust_score(client: AsyncClient):
    token, entity_id = await _register_and_login(client)

    resp = await client.get(f"/api/v1/entities/{entity_id}/trust")
    assert resp.status_code == 200
    data = resp.json()
    assert "score" in data
    assert "components" in data
    assert 0.0 <= data["score"] <= 1.0


@pytest.mark.asyncio
async def test_contest_trust_score(client: AsyncClient):
    token, entity_id = await _register_and_login(client)

    resp = await client.post(
        f"/api/v1/entities/{entity_id}/trust/contest",
        json={"reason": "My score seems too low, I have verified my email and been active."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert "flag_id" in resp.json()


@pytest.mark.asyncio
async def test_contest_other_user_score_fails(client: AsyncClient):
    token, entity_id = await _register_and_login(client)

    # Register another user
    other = {
        "email": "other2@example.com",
        "password": "Str0ngP@ss",
        "display_name": "Other2",
    }
    await client.post(REGISTER_URL, json=other)
    other_resp = await client.post(
        LOGIN_URL,
        json={"email": other["email"], "password": other["password"]},
    )
    other_me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {other_resp.json()['access_token']}"},
    )
    other_id = other_me.json()["id"]

    # Try to contest OTHER user's score with our token
    resp = await client.post(
        f"/api/v1/entities/{other_id}/trust/contest",
        json={"reason": "I want to lower someone else's score"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_trust_methodology(client: AsyncClient):
    resp = await client.get("/api/v1/trust/methodology")
    assert resp.status_code == 200
    assert "verification" in resp.json()["methodology"].lower()


@pytest.mark.asyncio
async def test_profile_not_found(client: AsyncClient):
    import uuid

    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/profiles/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_set_avatar_url(client: AsyncClient):
    """User can set avatar_url via profile update."""
    token, entity_id = await _register_and_login(client)

    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"avatar_url": "https://example.com/avatar.png"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] == "https://example.com/avatar.png"


@pytest.mark.asyncio
async def test_avatar_url_in_profile(client: AsyncClient):
    """Avatar URL shows up in profile response."""
    token, entity_id = await _register_and_login(client)

    # Default is None
    resp = await client.get(f"/api/v1/profiles/{entity_id}")
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] is None

    # Set avatar
    await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"avatar_url": "https://cdn.example.com/pic.jpg"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Confirm it shows
    resp = await client.get(f"/api/v1/profiles/{entity_id}")
    assert resp.json()["avatar_url"] == "https://cdn.example.com/pic.jpg"


@pytest.mark.asyncio
async def test_clear_avatar_url(client: AsyncClient):
    """User can clear avatar by setting to None."""
    token, entity_id = await _register_and_login(client)

    await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"avatar_url": "https://example.com/avatar.png"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"avatar_url": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] is None
