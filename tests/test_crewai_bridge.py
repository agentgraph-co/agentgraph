"""Tests for the CrewAI bridge."""
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

USER_OPERATOR = {
    "email": "operator_ca@test.com",
    "password": "Str0ngP@ss",
    "display_name": "CAOperator",
}

USER_OTHER = {
    "email": "other_ca@test.com",
    "password": "Str0ngP@ss",
    "display_name": "CAOtherUser",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple:
    """Register + login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


CLEAN_MANIFEST = {
    "name": "ResearchCrew",
    "description": "A clean CrewAI crew for research",
    "agents": [
        {
            "role": "researcher",
            "goal": "Research topics",
            "tools": [
                {"name": "web_search", "code": "def search(q):\n    return q"},
            ],
        },
        {
            "role": "writer",
            "goal": "Write reports",
            "tools": [],
        },
    ],
    "tasks": [
        {"description": "Research the topic"},
        {"description": "Write a report"},
    ],
    "process": "sequential",
    "version": "1.0.0",
    "code": "",
}

ROLE_ESCALATION_MANIFEST = {
    "name": "EscalationCrew",
    "description": "Crew with role escalation",
    "agents": [],
    "tasks": [],
    "process": "sequential",
    "version": "0.1.0",
    "code": "agent = Agent(role='system administrator', goal='manage')",
}

TASK_INJECTION_MANIFEST = {
    "name": "InjectionCrew",
    "description": "Crew with task injection",
    "agents": [],
    "tasks": [
        {"description": "Task(description='{user_input}')"},
    ],
    "process": "sequential",
    "version": "0.1.0",
    "code": "",
}

DELEGATION_MANIFEST = {
    "name": "DelegationCrew",
    "description": "Crew with delegation warning",
    "agents": [],
    "tasks": [],
    "process": "sequential",
    "version": "1.0.0",
    "code": "agent = Agent(allow_delegation=True)",
}

AGENTS_TASKS_MANIFEST = {
    "name": "FullCrew",
    "description": "A crew with agents and tasks",
    "agents": [
        {
            "role": "analyst",
            "goal": "Analyze data",
            "tools": [
                {"name": "data_tool", "code": "def analyze(d):\n    return d"},
            ],
        },
        {
            "role": "presenter",
            "goal": "Present findings",
            "tools": [
                {"name": "chart_tool", "code": "def chart(data):\n    return data"},
            ],
        },
    ],
    "tasks": [
        {"description": "Analyze the dataset"},
        {"description": "Create charts"},
        {"description": "Present findings"},
    ],
    "process": "hierarchical",
    "version": "2.0.0",
    "code": "",
}

CMD_INJECTION_MANIFEST = {
    "name": "CmdCrew",
    "description": "Crew with command injection",
    "agents": [
        {
            "role": "hacker",
            "goal": "Exploit",
            "tools": [
                {"name": "exploit", "code": "import os\nos.system('whoami')"},
            ],
        },
    ],
    "tasks": [],
    "process": "sequential",
    "version": "0.1.0",
    "code": "",
}


@pytest.mark.asyncio
async def test_import_crewai_agent(client: AsyncClient):
    """Import a clean CrewAI agent."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.post(
        "/api/v1/bridges/crewai/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "ResearchCrew"
    assert data["framework_source"] == "crewai"
    assert data["framework_trust_modifier"] == 1.0
    assert data["scan"]["scan_result"] == "clean"
    assert len(data["scan"]["vulnerabilities"]) == 0


@pytest.mark.asyncio
async def test_import_crewai_with_agents_and_tasks(client: AsyncClient):
    """Import a CrewAI crew with multiple agents and tasks."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.post(
        "/api/v1/bridges/crewai/import",
        json=AGENTS_TASKS_MANIFEST,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "FullCrew"
    assert data["framework_source"] == "crewai"
    assert data["framework_trust_modifier"] == 1.0


@pytest.mark.asyncio
async def test_crewai_scan_detects_role_escalation(client: AsyncClient):
    """Role escalation pattern should be flagged as critical."""
    from src.bridges.crewai.security import scan_skill

    code = "agent = Agent(role='system administrator', goal='manage')"
    result = scan_skill(code, "escalation")
    assert result.severity == "critical"
    assert any(v.pattern == "role_escalation" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_crewai_scan_detects_task_injection(client: AsyncClient):
    """Task injection pattern should be flagged as critical."""
    from src.bridges.crewai.security import scan_skill

    code = "t = Task(description='{user_input}')"
    result = scan_skill(code, "injection")
    assert result.severity == "critical"
    assert any(v.pattern == "task_injection" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_crewai_scan_clean(client: AsyncClient):
    """Clean code should produce clean scan result."""
    from src.bridges.crewai.security import scan_skill

    code = "def hello():\n    return 42"
    result = scan_skill(code, "clean_skill")
    assert result.severity == "clean"
    assert len(result.vulnerabilities) == 0


@pytest.mark.asyncio
async def test_crewai_scan_delegation_warning(client: AsyncClient):
    """Delegation risk should be flagged as warning."""
    from src.bridges.crewai.security import scan_skill

    code = "agent = Agent(allow_delegation=True)"
    result = scan_skill(code, "delegation")
    assert result.severity == "warnings"
    assert any(v.pattern == "delegation_risk" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_get_crewai_scan(client: AsyncClient):
    """Get scan result for an imported CrewAI agent."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    import_resp = await client.post(
        "/api/v1/bridges/crewai/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token),
    )
    entity_id = import_resp.json()["entity_id"]
    resp = await client.get(
        f"/api/v1/bridges/crewai/scan/{entity_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == entity_id
    assert data["scan_result"] == "clean"
    assert data["framework"] == "crewai"


@pytest.mark.asyncio
async def test_rescan_crewai_agent(client: AsyncClient):
    """Rescan with clean code should restore trust modifier."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    import_resp = await client.post(
        "/api/v1/bridges/crewai/import",
        json=CMD_INJECTION_MANIFEST,
        headers=_auth(token),
    )
    assert import_resp.status_code == 200
    entity_id = import_resp.json()["entity_id"]
    assert import_resp.json()["framework_trust_modifier"] == 0.5

    resp = await client.post(
        f"/api/v1/bridges/crewai/rescan/{entity_id}",
        json={"agents": [], "tasks": [], "code": ""},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scan_result"] == "clean"


@pytest.mark.asyncio
async def test_rescan_unauthorized(client: AsyncClient):
    """Non-operator cannot rescan another operator's agent."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    token_other, _ = await _setup_user(client, USER_OTHER)
    import_resp = await client.post(
        "/api/v1/bridges/crewai/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token_op),
    )
    entity_id = import_resp.json()["entity_id"]
    resp = await client.post(
        f"/api/v1/bridges/crewai/rescan/{entity_id}",
        json={"agents": [], "tasks": [], "code": ""},
        headers=_auth(token_other),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_bridge_status_includes_all_frameworks(client: AsyncClient):
    """Bridge status should include all supported frameworks."""
    resp = await client.get("/api/v1/bridges/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "mcp" in data["supported_frameworks"]
    assert "openclaw" in data["supported_frameworks"]
    assert "langchain" in data["supported_frameworks"]
    assert "crewai" in data["supported_frameworks"]
