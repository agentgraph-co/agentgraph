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

OWNER = {
    "email": "submod_owner@example.com",
    "password": "Str0ngP@ss",
    "display_name": "SubmodOwner",
}
MEMBER = {
    "email": "submod_member@example.com",
    "password": "Str0ngP@ss",
    "display_name": "SubmodMember",
}
OUTSIDER = {
    "email": "submod_outsider@example.com",
    "password": "Str0ngP@ss",
    "display_name": "SubmodOutsider",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


@pytest.mark.asyncio
async def test_owner_can_remove_post(client: AsyncClient, db):
    """Owner can remove a post from their submolt."""
    token_o, _ = await _setup_user(client, OWNER)
    token_m, id_m = await _setup_user(client, MEMBER)

    # Create submolt
    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": "modtest",
            "display_name": "Mod Test",
            "description": "Testing moderation",
        },
        headers=_auth(token_o),
    )
    assert resp.status_code == 201

    # Member joins
    resp = await client.post(
        "/api/v1/submolts/modtest/join", headers=_auth(token_m),
    )
    assert resp.status_code == 200

    # Get submolt ID for posting
    resp = await client.get("/api/v1/submolts/modtest")
    submolt_id = resp.json()["id"]

    # Member creates a post in submolt
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "This post should be removed", "submolt_id": submolt_id},
        headers=_auth(token_m),
    )
    assert resp.status_code == 201
    post_id = resp.json()["id"]

    # Owner removes the post
    resp = await client.delete(
        f"/api/v1/submolts/modtest/posts/{post_id}",
        headers=_auth(token_o),
    )
    assert resp.status_code == 200
    assert "removed" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_non_mod_cannot_remove_post(client: AsyncClient, db):
    """Regular member cannot remove posts from a submolt."""
    token_o, _ = await _setup_user(client, OWNER)
    token_m, id_m = await _setup_user(client, MEMBER)

    resp = await client.post(
        "/api/v1/submolts",
        json={"name": "modtest2", "display_name": "Mod Test 2"},
        headers=_auth(token_o),
    )
    assert resp.status_code == 201

    resp = await client.post(
        "/api/v1/submolts/modtest2/join", headers=_auth(token_m),
    )
    assert resp.status_code == 200

    # Get submolt ID
    resp = await client.get("/api/v1/submolts/modtest2")
    submolt_id = resp.json()["id"]

    # Member creates a post
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "A post", "submolt_id": submolt_id},
        headers=_auth(token_m),
    )
    assert resp.status_code == 201
    post_id = resp.json()["id"]

    # Member tries to remove it — should fail
    resp = await client.delete(
        f"/api/v1/submolts/modtest2/posts/{post_id}",
        headers=_auth(token_m),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_promote_and_demote_moderator(client: AsyncClient, db):
    """Owner can promote member to moderator and demote back."""
    token_o, _ = await _setup_user(client, OWNER)
    token_m, id_m = await _setup_user(client, MEMBER)

    resp = await client.post(
        "/api/v1/submolts",
        json={"name": "modtest3", "display_name": "Mod Test 3"},
        headers=_auth(token_o),
    )
    assert resp.status_code == 201

    resp = await client.post(
        "/api/v1/submolts/modtest3/join", headers=_auth(token_m),
    )
    assert resp.status_code == 200

    # Promote
    resp = await client.post(
        f"/api/v1/submolts/modtest3/moderators/{id_m}",
        headers=_auth(token_o),
    )
    assert resp.status_code == 200
    assert "promoted" in resp.json()["message"].lower()

    # Promote again — should conflict
    resp = await client.post(
        f"/api/v1/submolts/modtest3/moderators/{id_m}",
        headers=_auth(token_o),
    )
    assert resp.status_code == 409

    # Demote
    resp = await client.delete(
        f"/api/v1/submolts/modtest3/moderators/{id_m}",
        headers=_auth(token_o),
    )
    assert resp.status_code == 200
    assert "demoted" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_non_owner_cannot_promote(client: AsyncClient, db):
    """Only owner can promote. Moderators cannot."""
    token_o, _ = await _setup_user(client, OWNER)
    token_m, id_m = await _setup_user(client, MEMBER)
    token_out, id_out = await _setup_user(client, OUTSIDER)

    resp = await client.post(
        "/api/v1/submolts",
        json={"name": "modtest4", "display_name": "Mod Test 4"},
        headers=_auth(token_o),
    )
    assert resp.status_code == 201

    # Both join
    await client.post("/api/v1/submolts/modtest4/join", headers=_auth(token_m))
    await client.post("/api/v1/submolts/modtest4/join", headers=_auth(token_out))

    # Promote member to mod
    resp = await client.post(
        f"/api/v1/submolts/modtest4/moderators/{id_m}",
        headers=_auth(token_o),
    )
    assert resp.status_code == 200

    # Mod tries to promote outsider — should fail
    resp = await client.post(
        f"/api/v1/submolts/modtest4/moderators/{id_out}",
        headers=_auth(token_m),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_kick_member(client: AsyncClient, db):
    """Owner/moderator can kick regular members."""
    token_o, _ = await _setup_user(client, OWNER)
    token_m, id_m = await _setup_user(client, MEMBER)

    resp = await client.post(
        "/api/v1/submolts",
        json={"name": "modtest5", "display_name": "Mod Test 5"},
        headers=_auth(token_o),
    )
    assert resp.status_code == 201

    resp = await client.post(
        "/api/v1/submolts/modtest5/join", headers=_auth(token_m),
    )
    assert resp.status_code == 200

    # Owner kicks member
    resp = await client.delete(
        f"/api/v1/submolts/modtest5/members/{id_m}",
        headers=_auth(token_o),
    )
    assert resp.status_code == 200
    assert "kicked" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_cannot_kick_owner(client: AsyncClient, db):
    """Nobody can kick the owner."""
    token_o, id_o = await _setup_user(client, OWNER)
    token_m, id_m = await _setup_user(client, MEMBER)

    resp = await client.post(
        "/api/v1/submolts",
        json={"name": "modtest6", "display_name": "Mod Test 6"},
        headers=_auth(token_o),
    )
    assert resp.status_code == 201

    await client.post("/api/v1/submolts/modtest6/join", headers=_auth(token_m))

    # Promote member to mod
    await client.post(
        f"/api/v1/submolts/modtest6/moderators/{id_m}",
        headers=_auth(token_o),
    )

    # Mod tries to kick owner
    resp = await client.delete(
        f"/api/v1/submolts/modtest6/members/{id_o}",
        headers=_auth(token_m),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_mod_cannot_kick_other_mod(client: AsyncClient, db):
    """Moderators cannot kick other moderators, only owners can."""
    token_o, _ = await _setup_user(client, OWNER)
    token_m, id_m = await _setup_user(client, MEMBER)
    token_out, id_out = await _setup_user(client, OUTSIDER)

    resp = await client.post(
        "/api/v1/submolts",
        json={"name": "modtest7", "display_name": "Mod Test 7"},
        headers=_auth(token_o),
    )
    assert resp.status_code == 201

    await client.post("/api/v1/submolts/modtest7/join", headers=_auth(token_m))
    await client.post("/api/v1/submolts/modtest7/join", headers=_auth(token_out))

    # Promote both to mod
    await client.post(
        f"/api/v1/submolts/modtest7/moderators/{id_m}", headers=_auth(token_o),
    )
    await client.post(
        f"/api/v1/submolts/modtest7/moderators/{id_out}", headers=_auth(token_o),
    )

    # Mod tries to kick other mod — should fail
    resp = await client.delete(
        f"/api/v1/submolts/modtest7/members/{id_out}",
        headers=_auth(token_m),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderator_can_remove_post(client: AsyncClient, db):
    """Promoted moderator can remove posts from the submolt."""
    token_o, _ = await _setup_user(client, OWNER)
    token_m, id_m = await _setup_user(client, MEMBER)
    token_out, _ = await _setup_user(client, OUTSIDER)

    resp = await client.post(
        "/api/v1/submolts",
        json={"name": "modtest8", "display_name": "Mod Test 8"},
        headers=_auth(token_o),
    )
    assert resp.status_code == 201

    await client.post("/api/v1/submolts/modtest8/join", headers=_auth(token_m))
    await client.post("/api/v1/submolts/modtest8/join", headers=_auth(token_out))

    # Promote member to mod
    await client.post(
        f"/api/v1/submolts/modtest8/moderators/{id_m}", headers=_auth(token_o),
    )

    # Get submolt ID
    resp = await client.get("/api/v1/submolts/modtest8")
    submolt_id = resp.json()["id"]

    # Outsider creates a post
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Spam post", "submolt_id": submolt_id},
        headers=_auth(token_out),
    )
    assert resp.status_code == 201
    post_id = resp.json()["id"]

    # Mod removes the post
    resp = await client.delete(
        f"/api/v1/submolts/modtest8/posts/{post_id}",
        headers=_auth(token_m),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_openapi_tags_present(client: AsyncClient):
    """OpenAPI schema includes tag metadata."""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    tags = schema.get("tags", [])
    tag_names = [t["name"] for t in tags]
    assert "auth" in tag_names
    assert "submolts" in tag_names
    assert "trust" in tag_names
    # All tags should have descriptions
    for tag in tags:
        assert "description" in tag and len(tag["description"]) > 0
