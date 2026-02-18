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
    "email": "urlval@example.com",
    "password": "Str0ngP@ss",
    "display_name": "URLValidator",
}


async def _setup(client: AsyncClient) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL, json={"email": USER["email"], "password": USER["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Avatar URL validation ---


@pytest.mark.asyncio
async def test_avatar_rejects_non_http_url(client: AsyncClient):
    """Avatar URL must start with http:// or https://."""
    token, entity_id = await _setup(client)
    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"avatar_url": "ftp://example.com/avatar.png"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_avatar_rejects_localhost(client: AsyncClient):
    """Avatar URL cannot point to localhost (SSRF prevention)."""
    token, entity_id = await _setup(client)
    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"avatar_url": "http://localhost:8080/avatar.png"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_avatar_rejects_private_ip(client: AsyncClient):
    """Avatar URL cannot point to private IP ranges."""
    token, entity_id = await _setup(client)

    for url in [
        "http://127.0.0.1/avatar.png",
        "http://10.0.0.1/avatar.png",
        "http://192.168.1.1/avatar.png",
        "http://169.254.169.254/latest/meta-data/",
    ]:
        resp = await client.patch(
            f"/api/v1/profiles/{entity_id}",
            json={"avatar_url": url},
            headers=_auth(token),
        )
        assert resp.status_code == 422, f"Expected 422 for {url}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_avatar_accepts_valid_https(client: AsyncClient):
    """Avatar URL accepts valid HTTPS URLs."""
    token, entity_id = await _setup(client)
    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"avatar_url": "https://cdn.example.com/avatar.png"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] == "https://cdn.example.com/avatar.png"


# --- Webhook URL validation ---


@pytest.mark.asyncio
async def test_webhook_rejects_localhost(client: AsyncClient):
    """Webhook callback_url cannot point to localhost."""
    token, _ = await _setup(client)
    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "http://localhost:9000/hook",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_webhook_rejects_private_ip(client: AsyncClient):
    """Webhook callback_url cannot point to private IPs."""
    token, _ = await _setup(client)

    for url in [
        "http://10.0.0.1/hook",
        "http://192.168.1.100/hook",
        "http://172.16.0.1/hook",
        "http://169.254.169.254/latest/meta-data/",
    ]:
        resp = await client.post(
            "/api/v1/webhooks",
            json={"callback_url": url, "event_types": ["entity.followed"]},
            headers=_auth(token),
        )
        assert resp.status_code == 422, f"Expected 422 for {url}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_webhook_accepts_valid_url(client: AsyncClient):
    """Webhook accepts valid external HTTPS URLs."""
    token, _ = await _setup(client)
    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://hooks.example.com/webhook",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_webhook_update_rejects_internal_url(client: AsyncClient):
    """Webhook update also validates callback_url for SSRF."""
    token, _ = await _setup(client)

    # Create a valid webhook first
    create_resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://hooks.example.com/webhook",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token),
    )
    assert create_resp.status_code == 201
    webhook_id = create_resp.json()["webhook"]["id"]

    # Try to update to internal URL
    resp = await client.patch(
        f"/api/v1/webhooks/{webhook_id}",
        json={"callback_url": "http://127.0.0.1:8080/evil"},
        headers=_auth(token),
    )
    assert resp.status_code == 422
