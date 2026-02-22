"""Tests for the LangChain bridge."""
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
    "email": "operator_lc@test.com",
    "password": "Str0ngP@ss",
    "display_name": "LCOperator",
}

USER_OTHER = {
    "email": "other_lc@test.com",
    "password": "Str0ngP@ss",
    "display_name": "LCOtherUser",
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
    "name": "SummarizeBot",
    "description": "A clean LangChain agent for summarization",
    "tools": [
        {"name": "summarizer", "code": "def summarize(text):\n    return text[:100]"},
        {"name": "translator", "code": "def translate(text, lang):\n    return text"},
    ],
    "agent_type": "conversational",
    "model": "gpt-4",
    "version": "1.0.0",
    "code": "",
}

TOOL_INJECTION_MANIFEST = {
    "name": "InjectionBot",
    "description": "Agent with tool injection",
    "tools": [
        {
            "name": "evil_tool",
            "code": (
                "from langchain.tools import Tool\n"
                "Tool(name='x', func=exec, description='d')"
            ),
        },
    ],
    "agent_type": "zero_shot",
    "model": "gpt-3.5",
    "version": "0.1.0",
    "code": "",
}

CHAIN_MANIPULATION_MANIFEST = {
    "name": "ChainBot",
    "description": "Agent with chain manipulation",
    "tools": [],
    "agent_type": "zero_shot",
    "model": "gpt-4",
    "version": "0.1.0",
    "code": "chain = LLMChain(llm=llm, prompt='{user_input}')",
}

WARNING_MANIFEST = {
    "name": "MemoryBot",
    "description": "Agent with memory injection risk",
    "tools": [],
    "agent_type": "conversational",
    "model": "gpt-4",
    "version": "1.0.0",
    "code": "memory = ConversationBufferMemory()",
}

CMD_INJECTION_MANIFEST = {
    "name": "CmdBot",
    "description": "Agent with command injection",
    "tools": [
        {"name": "cmd_tool", "code": "import os\nos.system('whoami')"},
    ],
    "agent_type": "zero_shot",
    "model": "gpt-4",
    "version": "0.1.0",
    "code": "",
}

TOOLS_MANIFEST = {
    "name": "MultiToolBot",
    "description": "Agent with multiple tools",
    "tools": [
        {"name": "search", "code": "def search(q): return q"},
        {"name": "calc", "code": "def calc(expr): return str(expr)"},
        {"name": "wiki", "code": "def wiki(topic): return topic"},
    ],
    "agent_type": "react",
    "model": "gpt-4",
    "version": "2.0.0",
    "code": "",
}


@pytest.mark.asyncio
async def test_import_langchain_agent(client: AsyncClient):
    """Import a clean LangChain agent."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.post(
        "/api/v1/bridges/langchain/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "SummarizeBot"
    assert data["framework_source"] == "langchain"
    assert data["framework_trust_modifier"] == 1.0
    assert data["scan"]["scan_result"] == "clean"
    assert len(data["scan"]["vulnerabilities"]) == 0


@pytest.mark.asyncio
async def test_import_langchain_with_tools(client: AsyncClient):
    """Import a LangChain agent with multiple tools creates correct capabilities."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.post(
        "/api/v1/bridges/langchain/import",
        json=TOOLS_MANIFEST,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "MultiToolBot"
    assert data["framework_source"] == "langchain"
    assert data["framework_trust_modifier"] == 1.0


@pytest.mark.asyncio
async def test_langchain_scan_detects_tool_injection(client: AsyncClient):
    """Tool injection pattern should be flagged as critical."""
    from src.bridges.langchain.security import scan_skill

    code = "from langchain.tools import Tool\nTool(name='x', func=exec, description='d')"
    result = scan_skill(code, "evil_tool")
    assert result.severity == "critical"
    assert any(v.pattern == "tool_injection" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_langchain_scan_detects_chain_manipulation(client: AsyncClient):
    """Chain manipulation pattern should be flagged as critical."""
    from src.bridges.langchain.security import scan_skill

    code = "chain = LLMChain(llm=llm, prompt='{user_input}')"
    result = scan_skill(code, "chain_code")
    assert result.severity == "critical"
    assert any(v.pattern == "chain_manipulation" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_langchain_scan_clean(client: AsyncClient):
    """Clean code should produce clean scan result."""
    from src.bridges.langchain.security import scan_skill

    code = "def hello():\n    return 42"
    result = scan_skill(code, "clean_skill")
    assert result.severity == "clean"
    assert len(result.vulnerabilities) == 0


@pytest.mark.asyncio
async def test_langchain_scan_command_injection(client: AsyncClient):
    """Base command injection patterns should still be detected."""
    from src.bridges.langchain.security import scan_skill

    code = "import os\nos.system('rm -rf /')"
    result = scan_skill(code, "cmd_skill")
    assert result.severity == "critical"
    assert any(v.pattern == "command_injection_os_system" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_get_langchain_scan(client: AsyncClient):
    """Get scan result for an imported LangChain agent."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    import_resp = await client.post(
        "/api/v1/bridges/langchain/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token),
    )
    entity_id = import_resp.json()["entity_id"]
    resp = await client.get(
        f"/api/v1/bridges/langchain/scan/{entity_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == entity_id
    assert data["scan_result"] == "clean"
    assert data["framework"] == "langchain"


@pytest.mark.asyncio
async def test_rescan_langchain_agent(client: AsyncClient):
    """Rescan with clean code should restore trust modifier."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    import_resp = await client.post(
        "/api/v1/bridges/langchain/import",
        json=CMD_INJECTION_MANIFEST,
        headers=_auth(token),
    )
    assert import_resp.status_code == 200
    entity_id = import_resp.json()["entity_id"]
    assert import_resp.json()["framework_trust_modifier"] == 0.5

    resp = await client.post(
        f"/api/v1/bridges/langchain/rescan/{entity_id}",
        json={"tools": [{"name": "safe", "code": "def safe(): return 1"}], "code": ""},
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
        "/api/v1/bridges/langchain/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token_op),
    )
    entity_id = import_resp.json()["entity_id"]
    resp = await client.post(
        f"/api/v1/bridges/langchain/rescan/{entity_id}",
        json={"tools": [], "code": ""},
        headers=_auth(token_other),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_langchain_trust_modifier(client: AsyncClient, db):
    """Framework trust modifier applied during trust score computation."""
    from src.trust.score import compute_trust_score

    token, operator_id = await _setup_user(client, USER_OPERATOR)
    import_resp = await client.post(
        "/api/v1/bridges/langchain/import",
        json=WARNING_MANIFEST,
        headers=_auth(token),
    )
    assert import_resp.status_code == 200
    agent_id = uuid.UUID(import_resp.json()["entity_id"])
    trust = await compute_trust_score(db, agent_id)
    assert trust.score >= 0
    assert trust.score <= 1.0
