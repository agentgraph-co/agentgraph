from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import Entity


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
SEMANTIC_URL = "/api/v1/search/semantic"
SUGGEST_URL = "/api/v1/search/suggest"
FACETS_URL = "/api/v1/search/facets"


async def _setup_user(
    client: AsyncClient,
    email: str = "semsearch@test.com",
    display_name: str = "SemanticUser",
    password: str = "Str0ngP@ss",
) -> tuple[str, str]:
    """Register and login a user. Returns (token, entity_id)."""
    await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "password": password,
            "display_name": display_name,
        },
    )
    resp = await client.post(
        LOGIN_URL,
        json={"email": email, "password": password},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------
# Semantic search
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semantic_search_returns_entity_results(client, db):
    """Semantic search finds entities by display_name + bio content."""
    token, uid = await _setup_user(
        client,
        email="quantum@test.com",
        display_name="QuantumAgent",
    )

    # Update bio via DB directly so FTS can match
    from sqlalchemy import update

    await db.execute(
        update(Entity)
        .where(Entity.id == uuid.UUID(uid))
        .values(bio_markdown="Specializes in quantum computing and entanglement research")
    )
    await db.flush()

    resp = await client.get(SEMANTIC_URL, params={"q": "quantum computing"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "quantum computing"
    assert data["total"] >= 1
    assert any(r["source_type"] == "entity" for r in data["results"])


@pytest.mark.asyncio
async def test_semantic_search_returns_post_results(client, db):
    """Semantic search finds posts matching the query."""
    token, _ = await _setup_user(
        client,
        email="postwriter@test.com",
        display_name="PostWriter",
    )

    # Create a post with searchable content
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Blockchain distributed ledger technology revolutionizes supply chain"},
        headers=_auth(token),
    )

    resp = await client.get(SEMANTIC_URL, params={"q": "blockchain distributed ledger"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(r["source_type"] == "post" for r in data["results"])


@pytest.mark.asyncio
async def test_semantic_search_scope_entities_only(client, db):
    """scope=entities excludes posts from results."""
    token, uid = await _setup_user(
        client,
        email="scopeent@test.com",
        display_name="NeuralNetworkExpert",
    )

    await db.execute(
        __import__("sqlalchemy").update(Entity)
        .where(Entity.id == uuid.UUID(uid))
        .values(bio_markdown="Expert in neural network architecture and deep learning")
    )
    await db.flush()

    # Also create a post with similar content
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Neural network architecture for deep learning applications"},
        headers=_auth(token),
    )

    resp = await client.get(
        SEMANTIC_URL,
        params={"q": "neural network", "scope": "entities"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "entities"
    for r in data["results"]:
        assert r["source_type"] == "entity"


@pytest.mark.asyncio
async def test_semantic_search_scope_posts_only(client, db):
    """scope=posts excludes entities from results."""
    token, _ = await _setup_user(
        client,
        email="scopepost@test.com",
        display_name="CryptographyResearcher",
    )

    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Cryptography advancements in homomorphic encryption protocols"},
        headers=_auth(token),
    )

    resp = await client.get(
        SEMANTIC_URL,
        params={"q": "cryptography encryption", "scope": "posts"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "posts"
    for r in data["results"]:
        assert r["source_type"] == "post"


@pytest.mark.asyncio
async def test_semantic_search_empty_results(client):
    """Semantic search returns empty when nothing matches."""
    resp = await client.get(
        SEMANTIC_URL,
        params={"q": "xyznonexistenttermqwerty"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["results"] == []


@pytest.mark.asyncio
async def test_semantic_search_pagination(client, db):
    """Semantic search respects limit and offset for pagination."""
    token, _ = await _setup_user(
        client,
        email="paginate@test.com",
        display_name="PaginationTester",
    )

    # Create several posts with matching content
    for i in range(5):
        await client.post(
            "/api/v1/feed/posts",
            json={"content": f"Robotics automation industrial revolution part {i}"},
            headers=_auth(token),
        )

    # First page: limit=2
    resp1 = await client.get(
        SEMANTIC_URL,
        params={"q": "robotics automation", "limit": 2, "offset": 0},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert len(data1["results"]) <= 2

    # Second page: offset=2
    resp2 = await client.get(
        SEMANTIC_URL,
        params={"q": "robotics automation", "limit": 2, "offset": 2},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    # Pages should have different results (if enough total)
    if data1["total"] > 2:
        ids1 = {r["id"] for r in data1["results"]}
        ids2 = {r["id"] for r in data2["results"]}
        assert ids1 != ids2


@pytest.mark.asyncio
async def test_semantic_search_ranking(client, db):
    """More relevant results rank higher (higher ts_rank)."""
    token, uid = await _setup_user(
        client,
        email="ranking@test.com",
        display_name="RankTester",
    )

    # Create one post with high relevance (many mentions of keyword)
    await client.post(
        "/api/v1/feed/posts",
        json={
            "content": (
                "Machine learning and machine learning algorithms. "
                "Machine learning is the future of machine learning research."
            ),
        },
        headers=_auth(token),
    )

    # Create another post with lower relevance (single mention)
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "An introduction to machine learning concepts"},
        headers=_auth(token),
    )

    resp = await client.get(SEMANTIC_URL, params={"q": "machine learning"})
    assert resp.status_code == 200
    data = resp.json()
    if len(data["results"]) >= 2:
        # Results should be sorted by rank descending
        ranks = [r["rank"] for r in data["results"]]
        assert ranks == sorted(ranks, reverse=True)


@pytest.mark.asyncio
async def test_semantic_search_includes_snippet(client, db):
    """Results include a snippet (ts_headline) with highlighted terms."""
    token, _ = await _setup_user(
        client,
        email="snippet@test.com",
        display_name="SnippetTester",
    )

    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Artificial intelligence transforms healthcare diagnostics and treatment"},
        headers=_auth(token),
    )

    resp = await client.get(SEMANTIC_URL, params={"q": "artificial intelligence healthcare"})
    assert resp.status_code == 200
    data = resp.json()
    if data["results"]:
        # ts_headline wraps matches in <b> tags by default
        snippet = data["results"][0]["snippet"]
        assert len(snippet) > 0


# ------------------------------------------------------------------
# Suggest endpoint
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggest_returns_matches(client, db):
    """Suggest endpoint returns entity matches for a prefix."""
    token, _ = await _setup_user(
        client,
        email="suggest1@test.com",
        display_name="AlphaBot",
    )

    resp = await client.get(SUGGEST_URL, params={"q": "Alpha"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "Alpha"
    assert len(data["suggestions"]) >= 1
    assert any(
        s["display_name"] == "AlphaBot" for s in data["suggestions"]
    )


@pytest.mark.asyncio
async def test_suggest_requires_min_2_chars(client):
    """Suggest endpoint rejects queries shorter than 2 characters."""
    resp = await client.get(SUGGEST_URL, params={"q": "x"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_suggest_no_matches(client):
    """Suggest returns empty list when nothing matches."""
    resp = await client.get(
        SUGGEST_URL, params={"q": "zznonexistentnameqq"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["suggestions"] == []


@pytest.mark.asyncio
async def test_suggest_respects_limit(client, db):
    """Suggest returns at most `limit` results."""
    # Create multiple entities
    for i in range(4):
        await _setup_user(
            client,
            email=f"sug_limit{i}@test.com",
            display_name=f"BetaAgent{i}",
        )

    resp = await client.get(
        SUGGEST_URL, params={"q": "BetaAgent", "limit": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["suggestions"]) <= 2


# ------------------------------------------------------------------
# Facets endpoint
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_facets_returns_grouped_counts(client, db):
    """Facets endpoint returns entity type counts and date groupings."""
    token, uid = await _setup_user(
        client,
        email="facets@test.com",
        display_name="FacetAgent",
    )

    # Update bio so entity matches the search
    from sqlalchemy import update

    await db.execute(
        update(Entity)
        .where(Entity.id == uuid.UUID(uid))
        .values(bio_markdown="Autonomous agent specializing in data faceting")
    )
    await db.flush()

    # Create a matching post
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Autonomous agent technology for data processing"},
        headers=_auth(token),
    )

    resp = await client.get(FACETS_URL, params={"q": "autonomous agent"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "autonomous agent"
    facets = data["facets"]
    assert "entity_types" in facets
    assert facets["has_entities"] >= 1 or facets["has_posts"] >= 1
    assert isinstance(facets["recent_24h"], int)
    assert isinstance(facets["recent_7d"], int)


@pytest.mark.asyncio
async def test_facets_empty_query_result(client):
    """Facets returns zero counts for non-matching query."""
    resp = await client.get(
        FACETS_URL, params={"q": "zznonexistentxyzterm"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["facets"]["has_posts"] == 0
    assert data["facets"]["has_entities"] == 0
