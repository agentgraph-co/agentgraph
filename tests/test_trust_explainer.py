from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.main import app
from src.models import Entity, EntityType

# --- Fixtures ---

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
METHODOLOGY_URL = "/api/v1/trust-explainer/methodology"
FAQ_URL = "/api/v1/trust-explainer/faq"


def _breakdown_url(entity_id: str) -> str:
    return f"/api/v1/trust-explainer/breakdown/{entity_id}"


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


USER_DATA = {
    "email": "explainer_user@test.com",
    "password": "Str0ngP@ss1!",
    "display_name": "ExplainerUser",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register + login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Methodology endpoint (public) ---


@pytest.mark.asyncio
async def test_methodology_returns_200(client: AsyncClient):
    resp = await client.get(METHODOLOGY_URL)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_methodology_has_formula(client: AsyncClient):
    resp = await client.get(METHODOLOGY_URL)
    data = resp.json()
    assert "formula" in data
    assert "verification" in data["formula"]
    assert "activity" in data["formula"]


@pytest.mark.asyncio
async def test_methodology_has_five_components(client: AsyncClient):
    resp = await client.get(METHODOLOGY_URL)
    data = resp.json()
    component_names = [c["name"] for c in data["components"]]
    assert "verification" in component_names
    assert "age" in component_names
    assert "activity" in component_names
    assert "reputation" in component_names
    assert "community" in component_names
    assert len(data["components"]) == 5


@pytest.mark.asyncio
async def test_methodology_weights_sum_to_one(client: AsyncClient):
    resp = await client.get(METHODOLOGY_URL)
    data = resp.json()
    total = sum(c["weight"] for c in data["components"])
    assert abs(total - 1.0) < 0.01


@pytest.mark.asyncio
async def test_methodology_has_score_ranges(client: AsyncClient):
    resp = await client.get(METHODOLOGY_URL)
    data = resp.json()
    assert len(data["score_ranges"]) == 4
    labels = [r["range_label"] for r in data["score_ranges"]]
    assert "Low" in labels
    assert "Moderate" in labels
    assert "High" in labels
    assert "Exceptional" in labels


@pytest.mark.asyncio
async def test_methodology_has_dual_scores(client: AsyncClient):
    resp = await client.get(METHODOLOGY_URL)
    data = resp.json()
    assert "dual_scores" in data
    assert "trust_score" in data["dual_scores"]
    assert "community_score" in data["dual_scores"]


@pytest.mark.asyncio
async def test_methodology_has_improvement_tips(client: AsyncClient):
    resp = await client.get(METHODOLOGY_URL)
    data = resp.json()
    assert "improvement_tips" in data
    assert len(data["improvement_tips"]) > 0


@pytest.mark.asyncio
async def test_methodology_component_has_how_to_improve(client: AsyncClient):
    resp = await client.get(METHODOLOGY_URL)
    data = resp.json()
    for component in data["components"]:
        assert "how_to_improve" in component
        assert len(component["how_to_improve"]) > 0


# --- FAQ endpoint (public) ---


@pytest.mark.asyncio
async def test_faq_returns_200(client: AsyncClient):
    resp = await client.get(FAQ_URL)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_faq_has_items(client: AsyncClient):
    resp = await client.get(FAQ_URL)
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) >= 5


@pytest.mark.asyncio
async def test_faq_items_have_question_and_answer(client: AsyncClient):
    resp = await client.get(FAQ_URL)
    data = resp.json()
    for item in data["items"]:
        assert "question" in item
        assert "answer" in item
        assert len(item["question"]) > 0
        assert len(item["answer"]) > 0


@pytest.mark.asyncio
async def test_faq_covers_contestation(client: AsyncClient):
    resp = await client.get(FAQ_URL)
    data = resp.json()
    questions = [item["question"].lower() for item in data["items"]]
    assert any("contest" in q for q in questions)


# --- Breakdown endpoint (authenticated) ---


@pytest.mark.asyncio
async def test_breakdown_requires_auth(client: AsyncClient):
    fake_id = str(uuid.uuid4())
    resp = await client.get(_breakdown_url(fake_id))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_breakdown_returns_404_for_missing_entity(
    client: AsyncClient, db: AsyncSession,
):
    token, _ = await _setup_user(client, USER_DATA)
    fake_id = str(uuid.uuid4())
    resp = await client.get(
        _breakdown_url(fake_id), headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_breakdown_returns_own_score(
    client: AsyncClient, db: AsyncSession,
):
    token, entity_id = await _setup_user(
        client,
        {
            "email": "breakdown_own@test.com",
            "password": "Str0ngP@ss2!",
            "display_name": "BreakdownOwn",
        },
    )
    resp = await client.get(
        _breakdown_url(entity_id), headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == entity_id
    assert "current_score" in data
    assert "score_label" in data
    assert "components" in data
    assert "platform_average" in data
    assert "percentile_estimate" in data
    assert "account_age_days" in data
    assert "improvement_suggestions" in data


@pytest.mark.asyncio
async def test_breakdown_score_label_matches_range(
    client: AsyncClient, db: AsyncSession,
):
    token, entity_id = await _setup_user(
        client,
        {
            "email": "breakdown_label@test.com",
            "password": "Str0ngP@ss3!",
            "display_name": "BreakdownLabel",
        },
    )
    resp = await client.get(
        _breakdown_url(entity_id), headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    score = data["current_score"]
    label = data["score_label"]
    if score < 0.3:
        assert label == "Low"
    elif score < 0.6:
        assert label == "Moderate"
    elif score < 0.8:
        assert label == "High"
    else:
        assert label == "Exceptional"


@pytest.mark.asyncio
async def test_breakdown_components_have_explanations(
    client: AsyncClient, db: AsyncSession,
):
    token, entity_id = await _setup_user(
        client,
        {
            "email": "breakdown_comp@test.com",
            "password": "Str0ngP@ss4!",
            "display_name": "BreakdownComp",
        },
    )
    resp = await client.get(
        _breakdown_url(entity_id), headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    for comp in data["components"]:
        assert "name" in comp
        assert "raw_value" in comp
        assert "weight" in comp
        assert "contribution" in comp
        assert "explanation" in comp
        assert len(comp["explanation"]) > 0


@pytest.mark.asyncio
async def test_breakdown_can_view_other_entity(
    client: AsyncClient, db: AsyncSession,
):
    """Authenticated users can view breakdown of another entity."""
    token, _ = await _setup_user(
        client,
        {
            "email": "breakdown_viewer@test.com",
            "password": "Str0ngP@ss5!",
            "display_name": "Viewer",
        },
    )
    # Create another entity in the DB
    other = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        display_name="OtherEntity",
        did_web=f"did:web:agentgraph.co:users:{uuid.uuid4()}",
    )
    db.add(other)
    await db.flush()

    resp = await client.get(
        _breakdown_url(str(other.id)), headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == str(other.id)


@pytest.mark.asyncio
async def test_breakdown_inactive_entity_returns_404(
    client: AsyncClient, db: AsyncSession,
):
    token, _ = await _setup_user(
        client,
        {
            "email": "breakdown_inactive@test.com",
            "password": "Str0ngP@ss6!",
            "display_name": "InactiveViewer",
        },
    )
    inactive = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        display_name="InactiveEntity",
        did_web=f"did:web:agentgraph.co:users:{uuid.uuid4()}",
        is_active=False,
    )
    db.add(inactive)
    await db.flush()

    resp = await client.get(
        _breakdown_url(str(inactive.id)), headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_breakdown_has_improvement_suggestions_for_new_user(
    client: AsyncClient, db: AsyncSession,
):
    """New users should get actionable improvement suggestions."""
    token, entity_id = await _setup_user(
        client,
        {
            "email": "breakdown_new@test.com",
            "password": "Str0ngP@ss7!",
            "display_name": "NewUser",
        },
    )
    resp = await client.get(
        _breakdown_url(entity_id), headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    suggestions = data["improvement_suggestions"]
    # New users should have some suggestions
    assert len(suggestions) >= 1
    for s in suggestions:
        assert "component" in s
        assert "suggestion" in s
        assert "potential_gain" in s
        assert s["potential_gain"] > 0


@pytest.mark.asyncio
async def test_breakdown_platform_average_is_number(
    client: AsyncClient, db: AsyncSession,
):
    token, entity_id = await _setup_user(
        client,
        {
            "email": "breakdown_avg@test.com",
            "password": "Str0ngP@ss8!",
            "display_name": "AvgUser",
        },
    )
    resp = await client.get(
        _breakdown_url(entity_id), headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["platform_average"], (int, float))
    assert data["platform_average"] >= 0.0
