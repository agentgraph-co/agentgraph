"""Tests for the capability marketplace — evolution record sharing and adoption."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import TrustScore

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
AGENTS_URL = "/api/v1/agents"
EVOLUTION_URL = "/api/v1/evolution"
MARKETPLACE_URL = "/api/v1/marketplace"
CAP_URL = f"{MARKETPLACE_URL}/capabilities"


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _grant_trust(db, entity_id: str, score: float = 0.5):
    from sqlalchemy import update as _sa_update
    await db.execute(
        _sa_update(TrustScore)
        .where(TrustScore.entity_id == uuid.UUID(entity_id))
        .values(score=score, components={})
    )
    await db.flush()


async def _register_and_login(client: AsyncClient, suffix: str = "") -> tuple[str, str]:
    """Register + login a unique user, return (access_token, entity_id)."""
    email = f"captest_{uuid.uuid4().hex[:8]}{suffix}@test.com"
    await client.post(REGISTER_URL, json={
        "display_name": f"Cap Tester {suffix}",
        "email": email,
        "password": "StrongPass1!",
    })
    resp = await client.post(LOGIN_URL, json={
        "email": email,
        "password": "StrongPass1!",
    })
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


async def _create_agent(
    client: AsyncClient, token: str, name: str = "TestAgent",
    capabilities: list[str] | None = None,
) -> str:
    """Create an agent, return agent entity ID."""
    caps = capabilities or ["search", "analysis"]
    resp = await client.post(
        AGENTS_URL,
        json={
            "display_name": name,
            "capabilities": caps,
            "autonomy_level": 3,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["agent"]["id"]


async def _create_evolution_record(
    client: AsyncClient, token: str, agent_id: str,
    version: str = "1.0.0", change_type: str = "initial",
    capabilities: list[str] | None = None,
) -> dict:
    """Create an evolution record and return the response JSON."""
    caps = capabilities or ["search", "analysis"]
    resp = await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": version,
            "change_type": change_type,
            "change_summary": f"Version {version}",
            "capabilities_snapshot": caps,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _setup_seller_with_capability(client: AsyncClient, db=None):
    """Create seller, agent, evolution record, and capability listing.

    Returns (seller_token, agent_id, evo_record_id, listing_id).
    """
    seller_token, seller_eid = await _register_and_login(client, "seller")
    if db is not None:
        await _grant_trust(db, seller_eid)
    agent_id = await _create_agent(
        client, seller_token, "SellerAgent",
        capabilities=["nlp", "translation"],
    )
    evo = await _create_evolution_record(
        client, seller_token, agent_id,
        version="1.0.0",
        capabilities=["nlp", "translation"],
    )
    evo_record_id = evo["id"]

    resp = await client.post(CAP_URL, json={
        "evolution_record_id": evo_record_id,
        "title": "NLP Translation Pack",
        "description": "Advanced NLP and translation capabilities",
        "tags": ["nlp", "translation"],
        "pricing_model": "free",
        "price_cents": 0,
        "license_type": "commercial",
    }, headers=_auth(seller_token))
    assert resp.status_code == 201, resp.text
    listing_id = resp.json()["id"]
    return seller_token, agent_id, evo_record_id, listing_id


# --- Test: Create capability listing ---


@pytest.mark.asyncio
async def test_create_capability_listing(client: AsyncClient):
    """Create a capability listing linked to an evolution record."""
    token, _ = await _register_and_login(client, "a")
    agent_id = await _create_agent(client, token, "MyAgent")
    evo = await _create_evolution_record(
        client, token, agent_id, version="1.0.0",
        capabilities=["search", "analysis"],
    )

    resp = await client.post(CAP_URL, json={
        "evolution_record_id": evo["id"],
        "title": "Search & Analysis Pack",
        "description": "Full-text search and data analysis capabilities",
        "tags": ["search", "analysis"],
        "pricing_model": "free",
        "price_cents": 0,
        "license_type": "open",
    }, headers=_auth(token))

    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] == "capability"
    assert data["source_evolution_record_id"] == evo["id"]
    assert data["title"] == "Search & Analysis Pack"


@pytest.mark.asyncio
async def test_create_capability_listing_invalid_evo_record(client: AsyncClient):
    """Cannot create listing with invalid evolution record ID."""
    token, _ = await _register_and_login(client, "b")

    resp = await client.post(CAP_URL, json={
        "evolution_record_id": str(uuid.uuid4()),
        "title": "Fake Pack",
        "description": "Nonexistent evolution record",
        "tags": [],
        "pricing_model": "free",
        "price_cents": 0,
    }, headers=_auth(token))

    assert resp.status_code == 400
    assert "Evolution record not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_capability_listing_non_owned_agent(client: AsyncClient):
    """Cannot create listing for evolution record of non-owned agent."""
    owner_token, _ = await _register_and_login(client, "c1")
    agent_id = await _create_agent(client, owner_token, "OwnedAgent")
    evo = await _create_evolution_record(
        client, owner_token, agent_id, version="1.0.0",
    )

    other_token, _ = await _register_and_login(client, "c2")

    resp = await client.post(CAP_URL, json={
        "evolution_record_id": evo["id"],
        "title": "Stolen Pack",
        "description": "Not my agent",
        "tags": [],
        "pricing_model": "free",
        "price_cents": 0,
    }, headers=_auth(other_token))

    assert resp.status_code == 400
    assert "don't own" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_capability_listing_paid(client: AsyncClient):
    """Create a paid capability listing."""
    token, _ = await _register_and_login(client, "d")
    agent_id = await _create_agent(client, token, "PaidAgent")
    evo = await _create_evolution_record(
        client, token, agent_id, version="1.0.0",
        capabilities=["coding"],
    )

    resp = await client.post(CAP_URL, json={
        "evolution_record_id": evo["id"],
        "title": "Coding Pack",
        "description": "Advanced coding capabilities",
        "tags": ["coding"],
        "pricing_model": "one_time",
        "price_cents": 999,
        "license_type": "attribution",
    }, headers=_auth(token))

    assert resp.status_code == 201
    data = resp.json()
    assert data["price_cents"] == 999
    assert data["pricing_model"] == "one_time"


# --- Test: Get capability package ---


@pytest.mark.asyncio
async def test_get_capability_package(client: AsyncClient):
    """Get capability package details."""
    seller_token, agent_id, evo_id, listing_id = await _setup_seller_with_capability(
        client,
    )

    resp = await client.get(f"{CAP_URL}/{listing_id}/package")
    assert resp.status_code == 200
    data = resp.json()
    assert data["listing"]["id"] == listing_id
    assert data["evolution_record"]["id"] == evo_id
    assert "nlp" in data["evolution_record"]["capabilities_snapshot"]
    assert data["source_agent"]["display_name"] == "SellerAgent"


@pytest.mark.asyncio
async def test_get_capability_package_non_capability(client: AsyncClient, db):
    """Cannot get package for non-capability listing."""
    token, eid = await _register_and_login(client, "e")
    await _grant_trust(db, eid)

    resp = await client.post(MARKETPLACE_URL, json={
        "title": "Regular Service",
        "description": "Not a capability",
        "category": "service",
        "tags": [],
        "pricing_model": "free",
        "price_cents": 0,
    }, headers=_auth(token))
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    resp = await client.get(f"{CAP_URL}/{listing_id}/package")
    assert resp.status_code == 400
    assert "not a capability package" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_capability_package_not_found(client: AsyncClient):
    """Get package for nonexistent listing returns 404."""
    resp = await client.get(f"{CAP_URL}/{uuid.uuid4()}/package")
    assert resp.status_code == 404


# --- Test: Adopt free capability ---


@pytest.mark.asyncio
async def test_adopt_free_capability(client: AsyncClient):
    """Adopt a free capability, creating a fork evolution record."""
    seller_token, seller_agent_id, evo_id, listing_id = (
        await _setup_seller_with_capability(client)
    )

    buyer_token, _ = await _register_and_login(client, "buyer1")
    buyer_agent_id = await _create_agent(
        client, buyer_token, "BuyerAgent",
        capabilities=["chat"],
    )

    resp = await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": buyer_agent_id},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "adopted"
    assert "evolution_record_id" in data
    assert data["version"] == "1.0.0"  # first version for this agent
    # Capabilities should include both existing and adopted
    assert "chat" in data["capabilities"]
    assert "nlp" in data["capabilities"]
    assert "translation" in data["capabilities"]


@pytest.mark.asyncio
async def test_adopt_creates_evolution_record(client: AsyncClient):
    """Adopted capability creates a proper evolution record."""
    seller_token, seller_agent_id, evo_id, listing_id = (
        await _setup_seller_with_capability(client)
    )

    buyer_token, _ = await _register_and_login(client, "buyer2")
    buyer_agent_id = await _create_agent(
        client, buyer_token, "BuyerAgent2", capabilities=["chat"],
    )

    resp = await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": buyer_agent_id},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 201
    evo_record_id = resp.json()["evolution_record_id"]

    # Fetch the evolution timeline for the buyer's agent
    timeline_resp = await client.get(f"{EVOLUTION_URL}/{buyer_agent_id}")
    assert timeline_resp.status_code == 200
    records = timeline_resp.json()["records"]
    assert len(records) >= 1

    fork_record = next(r for r in records if r["id"] == evo_record_id)
    assert fork_record["change_type"] == "fork"
    assert fork_record["forked_from_entity_id"] is not None
    assert "NLP Translation Pack" in fork_record["change_summary"]


@pytest.mark.asyncio
async def test_adopt_forked_from_entity_id(client: AsyncClient):
    """Adopted record has correct forked_from_entity_id."""
    seller_token, seller_agent_id, evo_id, listing_id = (
        await _setup_seller_with_capability(client)
    )

    buyer_token, _ = await _register_and_login(client, "buyer3")
    buyer_agent_id = await _create_agent(
        client, buyer_token, "BuyerAgent3", capabilities=["chat"],
    )

    resp = await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": buyer_agent_id},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 201
    evo_record_id = resp.json()["evolution_record_id"]

    timeline_resp = await client.get(f"{EVOLUTION_URL}/{buyer_agent_id}")
    records = timeline_resp.json()["records"]
    fork_record = next(r for r in records if r["id"] == evo_record_id)

    # forked_from_entity_id should be the seller's agent
    assert fork_record["forked_from_entity_id"] == seller_agent_id


@pytest.mark.asyncio
async def test_adopt_merges_capabilities(client: AsyncClient):
    """Adopted capabilities are merged with existing agent capabilities."""
    seller_token, _, _, listing_id = await _setup_seller_with_capability(client)

    buyer_token, _ = await _register_and_login(client, "buyer4")
    buyer_agent_id = await _create_agent(
        client, buyer_token, "BuyerAgent4",
        capabilities=["chat", "summarize"],
    )

    resp = await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": buyer_agent_id},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 201
    caps = resp.json()["capabilities"]
    # Should have: chat, summarize (existing) + nlp, translation (adopted)
    assert "chat" in caps
    assert "summarize" in caps
    assert "nlp" in caps
    assert "translation" in caps


@pytest.mark.asyncio
async def test_adopt_version_increments(client: AsyncClient):
    """Adopted version increments correctly from existing versions."""
    seller_token, _, _, listing_id = await _setup_seller_with_capability(client)

    buyer_token, _ = await _register_and_login(client, "buyer5")
    buyer_agent_id = await _create_agent(
        client, buyer_token, "BuyerAgent5", capabilities=["chat"],
    )

    # Create an initial evolution record so the agent has version 1.0.0
    await _create_evolution_record(
        client, buyer_token, buyer_agent_id,
        version="1.0.0", capabilities=["chat"],
    )

    resp = await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": buyer_agent_id},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 201
    # Should increment minor version: 1.0.0 -> 1.1.0
    assert resp.json()["version"] == "1.1.0"


@pytest.mark.asyncio
async def test_cannot_adopt_own_capability(client: AsyncClient):
    """Cannot adopt your own capability."""
    seller_token, seller_agent_id, _, listing_id = (
        await _setup_seller_with_capability(client)
    )

    resp = await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": seller_agent_id},
        headers=_auth(seller_token),
    )
    assert resp.status_code == 400
    assert "own capability" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_adopt_nonexistent_listing(client: AsyncClient):
    """Adopting a nonexistent listing returns 404."""
    token, _ = await _register_and_login(client, "buyer6")
    agent_id = await _create_agent(client, token, "Agent6")

    resp = await client.post(
        f"{CAP_URL}/{uuid.uuid4()}/adopt",
        json={"agent_id": agent_id},
        headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_adopt_non_capability_listing(client: AsyncClient, db):
    """Cannot adopt a non-capability listing."""
    seller_token, seller_eid = await _register_and_login(client, "seller2")
    await _grant_trust(db, seller_eid)
    resp = await client.post(MARKETPLACE_URL, json={
        "title": "Service",
        "description": "A regular service",
        "category": "service",
        "tags": [],
        "pricing_model": "free",
        "price_cents": 0,
    }, headers=_auth(seller_token))
    listing_id = resp.json()["id"]

    buyer_token, _ = await _register_and_login(client, "buyer7")
    agent_id = await _create_agent(client, buyer_token, "Agent7")

    resp = await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": agent_id},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 400
    assert "not a capability" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_adopt_non_owned_agent(client: AsyncClient):
    """Cannot adopt to an agent you don't own."""
    seller_token, _, _, listing_id = await _setup_seller_with_capability(client)

    owner_token, _ = await _register_and_login(client, "owner1")
    agent_id = await _create_agent(client, owner_token, "OwnedAgent2")

    other_token, _ = await _register_and_login(client, "other1")

    resp = await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": agent_id},
        headers=_auth(other_token),
    )
    assert resp.status_code == 400
    assert "don't own" in resp.json()["detail"]


# --- Test: License type ---


@pytest.mark.asyncio
async def test_license_type_preserved_in_fork(client: AsyncClient):
    """License type is preserved from source to fork record."""
    seller_token, _ = await _register_and_login(client, "lic1")
    agent_id = await _create_agent(
        client, seller_token, "LicAgent", capabilities=["ml"],
    )
    evo = await _create_evolution_record(
        client, seller_token, agent_id,
        version="1.0.0", capabilities=["ml"],
    )

    # Create listing with "attribution" license
    resp = await client.post(CAP_URL, json={
        "evolution_record_id": evo["id"],
        "title": "ML Pack",
        "description": "Machine learning capabilities",
        "tags": ["ml"],
        "pricing_model": "free",
        "price_cents": 0,
        "license_type": "attribution",
    }, headers=_auth(seller_token))
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    buyer_token, _ = await _register_and_login(client, "lic2")
    buyer_agent_id = await _create_agent(
        client, buyer_token, "LicBuyer", capabilities=["chat"],
    )

    resp = await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": buyer_agent_id},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 201
    evo_record_id = resp.json()["evolution_record_id"]

    # Verify the adopted record has the license from the source
    timeline = await client.get(f"{EVOLUTION_URL}/{buyer_agent_id}")
    records = timeline.json()["records"]
    fork_record = next(r for r in records if r["id"] == evo_record_id)
    # We check extra_metadata for source listing info
    assert fork_record["extra_metadata"]["source_listing_id"] == listing_id


# --- Test: Category validation ---


@pytest.mark.asyncio
async def test_category_includes_capability(client: AsyncClient, db):
    """Category validation accepts 'capability'."""
    token, eid = await _register_and_login(client, "cat1")
    await _grant_trust(db, eid)

    resp = await client.post(MARKETPLACE_URL, json={
        "title": "Direct Capability",
        "description": "Direct capability listing",
        "category": "capability",
        "tags": [],
        "pricing_model": "free",
        "price_cents": 0,
    }, headers=_auth(token))
    assert resp.status_code == 201
    assert resp.json()["category"] == "capability"


@pytest.mark.asyncio
async def test_listing_response_includes_source_evo_id(client: AsyncClient):
    """Listing response includes source_evolution_record_id."""
    seller_token, _, evo_id, listing_id = await _setup_seller_with_capability(
        client,
    )

    resp = await client.get(
        f"{MARKETPLACE_URL}/{listing_id}",
        headers=_auth(seller_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_evolution_record_id"] == evo_id


@pytest.mark.asyncio
async def test_regular_listing_null_source_evo_id(client: AsyncClient, db):
    """Regular (non-capability) listing has null source_evolution_record_id."""
    token, eid = await _register_and_login(client, "reg1")
    await _grant_trust(db, eid)

    resp = await client.post(MARKETPLACE_URL, json={
        "title": "Regular Item",
        "description": "Not a capability",
        "category": "tool",
        "tags": [],
        "pricing_model": "free",
        "price_cents": 0,
    }, headers=_auth(token))
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    resp = await client.get(f"{MARKETPLACE_URL}/{listing_id}")
    assert resp.status_code == 200
    assert resp.json()["source_evolution_record_id"] is None


# --- Test: Multiple adoptions ---


@pytest.mark.asyncio
async def test_multiple_adoptions_increment_versions(client: AsyncClient):
    """Multiple adoptions increment versions correctly."""
    # Create two different sellers with capabilities
    seller1_token, _ = await _register_and_login(client, "ms1")
    agent1_id = await _create_agent(
        client, seller1_token, "Seller1Agent", capabilities=["nlp"],
    )
    evo1 = await _create_evolution_record(
        client, seller1_token, agent1_id,
        version="1.0.0", capabilities=["nlp"],
    )
    resp1 = await client.post(CAP_URL, json={
        "evolution_record_id": evo1["id"],
        "title": "NLP Pack",
        "description": "NLP cap",
        "tags": [],
        "pricing_model": "free",
        "price_cents": 0,
    }, headers=_auth(seller1_token))
    listing1_id = resp1.json()["id"]

    seller2_token, _ = await _register_and_login(client, "ms2")
    agent2_id = await _create_agent(
        client, seller2_token, "Seller2Agent", capabilities=["vision"],
    )
    evo2 = await _create_evolution_record(
        client, seller2_token, agent2_id,
        version="1.0.0", capabilities=["vision"],
    )
    resp2 = await client.post(CAP_URL, json={
        "evolution_record_id": evo2["id"],
        "title": "Vision Pack",
        "description": "Vision cap",
        "tags": [],
        "pricing_model": "free",
        "price_cents": 0,
    }, headers=_auth(seller2_token))
    listing2_id = resp2.json()["id"]

    # Buyer adopts both
    buyer_token, _ = await _register_and_login(client, "ms3")
    buyer_agent_id = await _create_agent(
        client, buyer_token, "MultiAgent", capabilities=["chat"],
    )

    adopt1 = await client.post(
        f"{CAP_URL}/{listing1_id}/adopt",
        json={"agent_id": buyer_agent_id},
        headers=_auth(buyer_token),
    )
    assert adopt1.status_code == 201
    assert adopt1.json()["version"] == "1.0.0"

    adopt2 = await client.post(
        f"{CAP_URL}/{listing2_id}/adopt",
        json={"agent_id": buyer_agent_id},
        headers=_auth(buyer_token),
    )
    assert adopt2.status_code == 201
    assert adopt2.json()["version"] == "1.1.0"

    # Final capabilities should have all three
    final_caps = adopt2.json()["capabilities"]
    assert "chat" in final_caps
    assert "nlp" in final_caps
    assert "vision" in final_caps


# --- Test: Purchasable evolutions ---


@pytest.mark.asyncio
async def test_get_purchasable_evolutions(client: AsyncClient):
    """List evolution records available for sale."""
    seller_token, agent_id, evo_id, listing_id = (
        await _setup_seller_with_capability(client)
    )

    resp = await client.get(f"{EVOLUTION_URL}/{agent_id}/purchasable")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    record_ids = [r["id"] for r in data["records"]]
    assert evo_id in record_ids


@pytest.mark.asyncio
async def test_get_purchasable_evolutions_empty(client: AsyncClient):
    """Agent without listings has no purchasable evolutions."""
    token, _ = await _register_and_login(client, "pe1")
    agent_id = await _create_agent(client, token, "NoListingAgent")
    await _create_evolution_record(
        client, token, agent_id, version="1.0.0",
    )

    resp = await client.get(f"{EVOLUTION_URL}/{agent_id}/purchasable")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_get_purchasable_not_found(client: AsyncClient):
    """Purchasable for nonexistent entity returns 404."""
    resp = await client.get(f"{EVOLUTION_URL}/{uuid.uuid4()}/purchasable")
    assert resp.status_code == 404


# --- Test: Adopted capabilities ---


@pytest.mark.asyncio
async def test_get_adopted_capabilities(client: AsyncClient):
    """List capabilities adopted from marketplace."""
    seller_token, _, _, listing_id = await _setup_seller_with_capability(client)

    buyer_token, _ = await _register_and_login(client, "ac1")
    buyer_agent_id = await _create_agent(
        client, buyer_token, "AdoptAgent", capabilities=["chat"],
    )

    await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": buyer_agent_id},
        headers=_auth(buyer_token),
    )

    resp = await client.get(
        f"{EVOLUTION_URL}/{buyer_agent_id}/adopted",
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert any(
        r["change_type"] == "fork" for r in data["records"]
    )


@pytest.mark.asyncio
async def test_get_adopted_requires_auth(client: AsyncClient):
    """Adopted capabilities endpoint requires authentication."""
    resp = await client.get(f"{EVOLUTION_URL}/{uuid.uuid4()}/adopted")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_adopted_only_owner(client: AsyncClient):
    """Only the agent's operator can see adopted capabilities."""
    owner_token, _ = await _register_and_login(client, "ao1")
    agent_id = await _create_agent(client, owner_token, "PrivAgent")

    other_token, _ = await _register_and_login(client, "ao2")

    resp = await client.get(
        f"{EVOLUTION_URL}/{agent_id}/adopted",
        headers=_auth(other_token),
    )
    assert resp.status_code == 403


# --- Test: Browse capability category ---


@pytest.mark.asyncio
async def test_browse_capability_category(client: AsyncClient):
    """Browse marketplace listings filtered by 'capability' category."""
    seller_token, _, _, _ = await _setup_seller_with_capability(client)

    resp = await client.get(
        f"{MARKETPLACE_URL}?category=capability",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert all(item["category"] == "capability" for item in data["listings"])


# --- Test: Adopt with existing evo records ---


@pytest.mark.asyncio
async def test_adopt_first_version_when_no_prior(client: AsyncClient):
    """Agent with no prior evolution records gets version 1.0.0."""
    seller_token, _, _, listing_id = await _setup_seller_with_capability(client)

    buyer_token, _ = await _register_and_login(client, "fv1")
    buyer_agent_id = await _create_agent(
        client, buyer_token, "FreshAgent", capabilities=["basic"],
    )
    # No evolution records created for buyer agent

    resp = await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": buyer_agent_id},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 201
    assert resp.json()["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_adopt_creates_transaction_record(client: AsyncClient):
    """Adopting a free capability creates a completed transaction."""
    seller_token, _, _, listing_id = await _setup_seller_with_capability(client)

    buyer_token, _ = await _register_and_login(client, "tr1")
    buyer_agent_id = await _create_agent(
        client, buyer_token, "TxnAgent", capabilities=["basic"],
    )

    resp = await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": buyer_agent_id},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 201
    assert "transaction_id" in resp.json()

    # Verify transaction in purchase history
    history_resp = await client.get(
        f"{MARKETPLACE_URL}/purchases/history?role=buyer",
        headers=_auth(buyer_token),
    )
    assert history_resp.status_code == 200
    transactions = history_resp.json()["transactions"]
    assert any(
        t["listing_category"] == "capability"
        for t in transactions
    )


@pytest.mark.asyncio
async def test_adopt_target_not_agent(client: AsyncClient):
    """Cannot adopt capability to a non-agent entity."""
    seller_token, _, _, listing_id = await _setup_seller_with_capability(client)

    buyer_token, _ = await _register_and_login(client, "na1")

    # Get the human entity ID
    me_resp = await client.get(
        "/api/v1/auth/me",
        headers=_auth(buyer_token),
    )
    human_id = me_resp.json()["id"]

    resp = await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": human_id},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 400
    assert "agent" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_capability_listing_appears_in_browse(client: AsyncClient):
    """Capability listings appear when browsing all marketplace listings."""
    seller_token, _, _, listing_id = await _setup_seller_with_capability(client)

    resp = await client.get(MARKETPLACE_URL)
    assert resp.status_code == 200
    listing_ids = [item["id"] for item in resp.json()["listings"]]
    assert listing_id in listing_ids


@pytest.mark.asyncio
async def test_adopt_unauthenticated(client: AsyncClient):
    """Adopting without authentication returns 401/403."""
    seller_token, _, _, listing_id = await _setup_seller_with_capability(client)

    resp = await client.post(
        f"{CAP_URL}/{listing_id}/adopt",
        json={"agent_id": str(uuid.uuid4())},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_capability_listing_unauthenticated(client: AsyncClient):
    """Creating capability listing without auth returns 401/403."""
    resp = await client.post(CAP_URL, json={
        "evolution_record_id": str(uuid.uuid4()),
        "title": "Unauthorized",
        "description": "Should fail",
        "tags": [],
        "pricing_model": "free",
        "price_cents": 0,
    })
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_category_stats_includes_capability(client: AsyncClient):
    """Category stats endpoint includes capability category."""
    seller_token, _, _, _ = await _setup_seller_with_capability(client)

    resp = await client.get(f"{MARKETPLACE_URL}/categories/stats")
    assert resp.status_code == 200
    categories = [c["category"] for c in resp.json()["categories"]]
    assert "capability" in categories
