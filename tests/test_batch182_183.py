"""Tests for Tasks #182-183: is_active fixes in trust and search routers."""
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
ME_URL = "/api/v1/auth/me"


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_trust_score_404_for_deactivated_entity(client, db):
    """GET /entities/{id}/trust should return 404 for deactivated entity."""
    token_a, entity_a = await _setup_user(client, {
        "email": "batch182trust@test.com",
        "password": "Str0ngP@ss",
        "display_name": "Batch182Trust",
    })
    token_b, entity_b = await _setup_user(client, {
        "email": "batch182other@test.com",
        "password": "Str0ngP@ss",
        "display_name": "Batch182Other",
    })

    # Trust score is accessible before deactivation
    resp = await client.get(
        f"/api/v1/entities/{entity_a}/trust", headers=_auth(token_b),
    )
    assert resp.status_code == 200

    # Deactivate entity A
    resp = await client.post(
        "/api/v1/account/deactivate", headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Trust score should return 404
    resp = await client.get(
        f"/api/v1/entities/{entity_a}/trust", headers=_auth(token_b),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_excludes_posts_by_deactivated_author(client, db):
    """Search should not return posts by deactivated authors."""
    token_a, entity_a = await _setup_user(client, {
        "email": "batch182search@test.com",
        "password": "Str0ngP@ss",
        "display_name": "Batch182Search",
    })
    token_b, entity_b = await _setup_user(client, {
        "email": "batch182searcher@test.com",
        "password": "Str0ngP@ss",
        "display_name": "Batch182Searcher",
    })

    # Create a post with a unique keyword
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Unique xylophone182 content for search test"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    # Search finds the post before deactivation
    resp = await client.get(
        "/api/v1/search?q=xylophone182", headers=_auth(token_b),
    )
    assert resp.status_code == 200
    assert resp.json()["post_count"] >= 1

    # Deactivate the author
    resp = await client.post(
        "/api/v1/account/deactivate", headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Search should no longer find the post
    resp = await client.get(
        "/api/v1/search?q=xylophone182", headers=_auth(token_b),
    )
    assert resp.status_code == 200
    assert resp.json()["post_count"] == 0
