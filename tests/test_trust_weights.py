from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.trust.personalized import compute_personalized_score


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
ACCOUNT_URL = "/api/v1/account"

USER = {
    "email": "trustweight@test.com",
    "password": "Str0ngP@ss",
    "display_name": "TrustWeightUser",
}


async def _setup_user(
    client: AsyncClient, user: dict | None = None,
) -> str:
    """Register + login, return JWT token."""
    u = user or USER
    await client.post(REGISTER_URL, json=u)
    resp = await client.post(
        LOGIN_URL, json={"email": u["email"], "password": u["password"]},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- API endpoint tests ---


@pytest.mark.asyncio
async def test_get_default_trust_weights(client: AsyncClient):
    """GET /account/trust-weights returns defaults when no custom weights."""
    token = await _setup_user(client)

    resp = await client.get(
        f"{ACCOUNT_URL}/trust-weights", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_custom"] is False
    assert data["verification"] == 0.35
    assert data["age"] == 0.10
    assert data["activity"] == 0.20
    assert data["reputation"] == 0.15
    assert data["community"] == 0.20


@pytest.mark.asyncio
async def test_put_custom_trust_weights(client: AsyncClient):
    """PUT /account/trust-weights saves custom weights."""
    token = await _setup_user(client)

    custom = {
        "verification": 0.20,
        "age": 0.20,
        "activity": 0.20,
        "reputation": 0.20,
        "community": 0.20,
    }

    resp = await client.put(
        f"{ACCOUNT_URL}/trust-weights",
        json=custom,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_custom"] is True
    assert data["verification"] == 0.20
    assert data["age"] == 0.20

    # Verify it persists on GET
    resp = await client.get(
        f"{ACCOUNT_URL}/trust-weights", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_custom"] is True
    assert data["verification"] == 0.20


@pytest.mark.asyncio
async def test_put_rejects_bad_sum(client: AsyncClient):
    """PUT rejects weights that don't sum to ~1.0."""
    token = await _setup_user(client)

    bad_weights = {
        "verification": 0.50,
        "age": 0.50,
        "activity": 0.50,
        "reputation": 0.50,
        "community": 0.50,
    }

    resp = await client.put(
        f"{ACCOUNT_URL}/trust-weights",
        json=bad_weights,
        headers=_auth(token),
    )
    assert resp.status_code == 422
    assert "sum" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_put_accepts_close_to_one(client: AsyncClient):
    """PUT accepts weights that sum close to 1.0 (within 0.05 tolerance)."""
    token = await _setup_user(client)

    # Sum = 1.03 (within tolerance)
    weights = {
        "verification": 0.34,
        "age": 0.11,
        "activity": 0.20,
        "reputation": 0.18,
        "community": 0.20,
    }

    resp = await client.put(
        f"{ACCOUNT_URL}/trust-weights",
        json=weights,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_custom"] is True


@pytest.mark.asyncio
async def test_delete_resets_to_defaults(client: AsyncClient):
    """DELETE /account/trust-weights resets to default weights."""
    token = await _setup_user(client)

    # Set custom weights first
    custom = {
        "verification": 0.20,
        "age": 0.20,
        "activity": 0.20,
        "reputation": 0.20,
        "community": 0.20,
    }
    await client.put(
        f"{ACCOUNT_URL}/trust-weights",
        json=custom,
        headers=_auth(token),
    )

    # Reset
    resp = await client.delete(
        f"{ACCOUNT_URL}/trust-weights", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_custom"] is False
    assert data["verification"] == 0.35
    assert data["age"] == 0.10

    # Confirm GET returns defaults
    resp = await client.get(
        f"{ACCOUNT_URL}/trust-weights", headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_custom"] is False


@pytest.mark.asyncio
async def test_put_rejects_out_of_range(client: AsyncClient):
    """PUT rejects individual weights outside 0.0-1.0 range."""
    token = await _setup_user(client)

    bad = {
        "verification": 1.5,
        "age": 0.10,
        "activity": 0.20,
        "reputation": 0.15,
        "community": 0.20,
    }

    resp = await client.put(
        f"{ACCOUNT_URL}/trust-weights",
        json=bad,
        headers=_auth(token),
    )
    assert resp.status_code == 422


# --- Unit tests for compute_personalized_score ---


def test_compute_personalized_score_defaults():
    """compute_personalized_score uses default weights when none provided."""
    components = {
        "verification": 1.0,
        "age": 1.0,
        "activity": 1.0,
        "reputation": 1.0,
        "community": 1.0,
    }
    score = compute_personalized_score(components)
    assert abs(score - 1.0) < 0.001


def test_compute_personalized_score_custom():
    """compute_personalized_score respects custom weights."""
    components = {
        "verification": 1.0,
        "age": 0.0,
        "activity": 0.0,
        "reputation": 0.0,
        "community": 0.0,
    }
    custom = {
        "verification": 0.50,
        "age": 0.10,
        "activity": 0.10,
        "reputation": 0.10,
        "community": 0.20,
    }
    score = compute_personalized_score(components, custom)
    assert abs(score - 0.50) < 0.001


def test_compute_personalized_score_zero_components():
    """compute_personalized_score returns 0 for all-zero components."""
    components = {
        "verification": 0.0,
        "age": 0.0,
        "activity": 0.0,
        "reputation": 0.0,
        "community": 0.0,
    }
    score = compute_personalized_score(components)
    assert score == 0.0


def test_compute_personalized_score_clamped():
    """compute_personalized_score clamps result to 0.0-1.0."""
    components = {
        "verification": 2.0,
        "age": 2.0,
        "activity": 2.0,
        "reputation": 2.0,
        "community": 2.0,
    }
    score = compute_personalized_score(components)
    assert score == 1.0


def test_compute_personalized_score_partial_components():
    """compute_personalized_score handles missing component keys gracefully."""
    components = {"verification": 0.8}  # only one component provided
    score = compute_personalized_score(components)
    expected = 0.35 * 0.8  # only verification contributes
    assert abs(score - expected) < 0.001
