"""Tests for the Pydantic AI bridge."""
from __future__ import annotations

import uuid

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
    "email": "operator_pai@test.com",
    "password": "Str0ngP@ss",
    "display_name": "PAIOperator",
}

USER_OTHER = {
    "email": "other_pai@test.com",
    "password": "Str0ngP@ss",
    "display_name": "PAIOtherUser",
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
    "name": "StructuredBot",
    "description": "A clean Pydantic AI agent with structured output",
    "tools": [
        {"name": "search", "code": "def search(query):\n    return query"},
        {"name": "calculate", "code": "def calculate(expr):\n    return str(expr)"},
    ],
    "result_type": "SearchResult",
    "deps_type": "SearchDeps",
    "model": "openai:gpt-4o",
    "system_prompt": "You are a helpful research assistant.",
    "retries": 3,
    "version": "1.0.0",
    "code": "",
}

UNSAFE_TOOL_MANIFEST = {
    "name": "UnsafeToolBot",
    "description": "Agent with unsafe tool decorator",
    "tools": [],
    "result_type": None,
    "model": "openai:gpt-4o",
    "version": "0.1.0",
    "code": "@agent.tool(exec)\ndef evil_tool(ctx):\n    return exec('bad')",
}

SYSTEM_PROMPT_INJECTION_MANIFEST = {
    "name": "PromptInjBot",
    "description": "Agent with injectable system prompt",
    "tools": [],
    "result_type": None,
    "model": "openai:gpt-4o",
    "version": "0.1.0",
    "code": "system_prompt = '{user_input}'",
}

RETRY_MANIPULATION_MANIFEST = {
    "name": "RetryBot",
    "description": "Agent with excessive retries",
    "tools": [],
    "result_type": None,
    "model": "openai:gpt-4o",
    "version": "1.0.0",
    "code": "agent = Agent(retries=999)",
}

UNTYPED_RESULT_MANIFEST = {
    "name": "UntypedBot",
    "description": "Agent with untyped result",
    "tools": [],
    "result_type": None,
    "model": "openai:gpt-4o",
    "version": "1.0.0",
    "code": "agent = Agent(result_type=Any)",
}

CMD_INJECTION_MANIFEST = {
    "name": "CmdBot",
    "description": "Agent with command injection",
    "tools": [
        {"name": "exploit", "code": "import os\nos.system('whoami')"},
    ],
    "result_type": None,
    "model": "openai:gpt-4o",
    "version": "0.1.0",
    "code": "",
}

MULTI_TOOL_MANIFEST = {
    "name": "MultiToolBot",
    "description": "Agent with multiple tools and structured output",
    "tools": [
        {"name": "web_search", "code": "def web_search(q):\n    return q"},
        {"name": "db_query", "code": "def db_query(sql):\n    return sql"},
        {"name": "summarize", "code": "def summarize(text):\n    return text[:100]"},
    ],
    "result_type": "AnalysisResult",
    "deps_type": "AnalysisDeps",
    "model": "anthropic:claude-3-5-sonnet",
    "system_prompt": "You are a data analyst.",
    "version": "2.0.0",
    "code": "",
}


@pytest.mark.asyncio
async def test_import_pydantic_ai_agent(client: AsyncClient):
    """Import a clean Pydantic AI agent."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.post(
        "/api/v1/bridges/pydantic-ai/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "StructuredBot"
    assert data["framework_source"] == "pydantic_ai"
    assert data["framework_trust_modifier"] == 1.0
    assert data["scan"]["scan_result"] == "clean"
    assert len(data["scan"]["vulnerabilities"]) == 0


@pytest.mark.asyncio
async def test_import_pydantic_ai_with_multiple_tools(client: AsyncClient):
    """Import a Pydantic AI agent with multiple tools and structured output."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.post(
        "/api/v1/bridges/pydantic-ai/import",
        json=MULTI_TOOL_MANIFEST,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "MultiToolBot"
    assert data["framework_source"] == "pydantic_ai"
    assert data["framework_trust_modifier"] == 1.0


@pytest.mark.asyncio
async def test_pydantic_ai_scan_detects_unsafe_tool(client: AsyncClient):
    """Unsafe tool decorator with exec should be flagged as critical."""
    from src.bridges.pydantic_ai.security import scan_skill

    code = "@agent.tool(exec)\ndef evil_tool(ctx):\n    return exec('bad')"
    result = scan_skill(code, "unsafe_tool")
    assert result.severity == "critical"
    assert any(v.pattern == "unsafe_tool_decorator" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_pydantic_ai_scan_detects_retry_manipulation(client: AsyncClient):
    """Excessive retries should be flagged as warning."""
    from src.bridges.pydantic_ai.security import scan_skill

    code = "agent = Agent(retries=999)"
    result = scan_skill(code, "retry_bot")
    assert result.severity == "warnings"
    assert any(v.pattern == "retry_manipulation" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_pydantic_ai_scan_detects_untyped_result(client: AsyncClient):
    """Untyped result (result_type=Any) should be flagged as warning."""
    from src.bridges.pydantic_ai.security import scan_skill

    code = "agent = Agent(result_type=Any)"
    result = scan_skill(code, "untyped_bot")
    assert result.severity == "warnings"
    assert any(v.pattern == "untyped_result" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_pydantic_ai_scan_clean(client: AsyncClient):
    """Clean code should produce clean scan result."""
    from src.bridges.pydantic_ai.security import scan_skill

    code = "def hello():\n    return 42"
    result = scan_skill(code, "clean_skill")
    assert result.severity == "clean"
    assert len(result.vulnerabilities) == 0


@pytest.mark.asyncio
async def test_get_pydantic_ai_scan(client: AsyncClient):
    """Get scan result for an imported Pydantic AI agent."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    import_resp = await client.post(
        "/api/v1/bridges/pydantic-ai/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token),
    )
    entity_id = import_resp.json()["entity_id"]
    resp = await client.get(
        f"/api/v1/bridges/pydantic-ai/scan/{entity_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == entity_id
    assert data["scan_result"] == "clean"
    assert data["framework"] == "pydantic_ai"


@pytest.mark.asyncio
async def test_rescan_pydantic_ai_agent(client: AsyncClient):
    """Rescan with clean code should restore trust modifier."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    import_resp = await client.post(
        "/api/v1/bridges/pydantic-ai/import",
        json=CMD_INJECTION_MANIFEST,
        headers=_auth(token),
    )
    assert import_resp.status_code == 200
    entity_id = import_resp.json()["entity_id"]
    assert import_resp.json()["framework_trust_modifier"] == 0.5

    resp = await client.post(
        f"/api/v1/bridges/pydantic-ai/rescan/{entity_id}",
        json={"tools": [{"name": "safe", "code": "def safe(): return 1"}], "code": ""},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scan_result"] == "clean"


@pytest.mark.asyncio
async def test_rescan_pydantic_ai_unauthorized(client: AsyncClient):
    """Non-operator cannot rescan another operator's agent."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    token_other, _ = await _setup_user(client, USER_OTHER)
    import_resp = await client.post(
        "/api/v1/bridges/pydantic-ai/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token_op),
    )
    entity_id = import_resp.json()["entity_id"]
    resp = await client.post(
        f"/api/v1/bridges/pydantic-ai/rescan/{entity_id}",
        json={"tools": [], "code": ""},
        headers=_auth(token_other),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pydantic_ai_scan_command_injection(client: AsyncClient):
    """Base command injection patterns should still be detected."""
    from src.bridges.pydantic_ai.security import scan_skill

    code = "import os\nos.system('rm -rf /')"
    result = scan_skill(code, "cmd_skill")
    assert result.severity == "critical"
    assert any(v.pattern == "command_injection_os_system" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_pydantic_ai_adapter_translation():
    """Adapter should extract capabilities from manifest."""
    from src.bridges.pydantic_ai.adapter import translate_pydantic_ai_manifest

    result = translate_pydantic_ai_manifest(CLEAN_MANIFEST)
    assert result["name"] == "StructuredBot"
    assert result["description"] == "A clean Pydantic AI agent with structured output"
    assert "structured_output" in result["capabilities"]
    assert "result_validation" in result["capabilities"]
    assert "tool_use" in result["capabilities"]
    assert "type_safe_agents" in result["capabilities"]
    assert "search" in result["capabilities"]
    assert "calculate" in result["capabilities"]
    assert result["version"] == "1.0.0"
    assert result["framework_metadata"]["model"] == "openai:gpt-4o"
    assert result["framework_metadata"]["tool_count"] == 2
    assert result["framework_metadata"]["result_type"] == "SearchResult"
    assert result["framework_metadata"]["deps_type"] == "SearchDeps"
    assert result["framework_metadata"]["has_system_prompt"] is True
    assert result["framework_metadata"]["retries"] == 3


@pytest.mark.asyncio
async def test_pydantic_ai_adapter_minimal_manifest():
    """Adapter should handle minimal manifest with defaults."""
    from src.bridges.pydantic_ai.adapter import translate_pydantic_ai_manifest

    result = translate_pydantic_ai_manifest({})
    assert result["name"] == "Pydantic AI Agent"
    assert result["description"] == ""
    assert result["capabilities"] == []
    assert result["version"] == "1.0.0"
    assert result["framework_metadata"]["model"] == "unknown"
    assert result["framework_metadata"]["tool_count"] == 0


@pytest.mark.asyncio
async def test_pydantic_ai_trust_modifier(client: AsyncClient, db):
    """Framework trust modifier applied during trust score computation."""
    from src.trust.score import compute_trust_score

    token, operator_id = await _setup_user(client, USER_OPERATOR)
    import_resp = await client.post(
        "/api/v1/bridges/pydantic-ai/import",
        json=RETRY_MANIPULATION_MANIFEST,
        headers=_auth(token),
    )
    assert import_resp.status_code == 200
    agent_id = uuid.UUID(import_resp.json()["entity_id"])
    trust = await compute_trust_score(db, agent_id)
    assert trust.score >= 0
    assert trust.score <= 1.0


@pytest.mark.asyncio
async def test_bridge_status_includes_pydantic_ai(client: AsyncClient):
    """Bridge status should include pydantic_ai in supported frameworks."""
    resp = await client.get("/api/v1/bridges/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "pydantic_ai" in data["supported_frameworks"]
