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
PRIVACY_URL = "/api/v1/account/privacy"
SEARCH_URL = "/api/v1/search"

USER = {
    "email": "privacy@test.com",
    "password": "Str0ngP@ss",
    "display_name": "PrivacyUser",
}
USER_B = {
    "email": "privacy-b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "PublicUser",
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


@pytest.mark.asyncio
async def test_default_privacy_tier(client: AsyncClient):
    token, _ = await _setup_user(client, USER)

    resp = await client.get(PRIVACY_URL, headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "public"
    assert "public" in data["options"]
    assert "verified" in data["options"]
    assert "private" in data["options"]


@pytest.mark.asyncio
async def test_set_privacy_tier(client: AsyncClient):
    token, _ = await _setup_user(client, USER)

    resp = await client.put(
        PRIVACY_URL,
        json={"tier": "private"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["tier"] == "private"

    # Verify it persists
    resp = await client.get(PRIVACY_URL, headers=_auth(token))
    assert resp.json()["tier"] == "private"


@pytest.mark.asyncio
async def test_set_privacy_tier_invalid(client: AsyncClient):
    token, _ = await _setup_user(client, USER)

    resp = await client.put(
        PRIVACY_URL,
        json={"tier": "invisible"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_privacy_tier_hides_from_search(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER)
    await _setup_user(client, USER_B)

    # Both visible by default
    resp = await client.get(SEARCH_URL, params={"q": "User"})
    assert resp.json()["entity_count"] >= 2

    # A goes private
    await client.put(
        PRIVACY_URL,
        json={"tier": "private"},
        headers=_auth(token_a),
    )

    # Search should only find B (public)
    resp = await client.get(SEARCH_URL, params={"q": "PrivacyUser"})
    assert resp.json()["entity_count"] == 0


@pytest.mark.asyncio
async def test_privacy_change_audit_logged(client: AsyncClient):
    token, _ = await _setup_user(client, USER)

    await client.put(
        PRIVACY_URL,
        json={"tier": "verified"},
        headers=_auth(token),
    )

    resp = await client.get(
        "/api/v1/account/audit-log", headers=_auth(token),
    )
    actions = [e["action"] for e in resp.json()["entries"]]
    assert "account.privacy_change" in actions
