"""Tests for the AutoGen bridge."""
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
    "email": "operator_ag@test.com",
    "password": "Str0ngP@ss",
    "display_name": "AGOperator",
}

USER_OTHER = {
    "email": "other_ag@test.com",
    "password": "Str0ngP@ss",
    "display_name": "AGOtherUser",
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
    "name": "ChatBot",
    "description": "A clean AutoGen conversational agent",
    "agents": [
        {
            "name": "assistant",
            "type": "AssistantAgent",
            "functions": [
                {"name": "summarize", "code": "def summarize(text):\n    return text[:100]"},
            ],
        },
    ],
    "oai_config": {"model": "gpt-4"},
    "code_execution_config": {},
    "version": "1.0.0",
    "code": "",
}

CODE_EXEC_MANIFEST = {
    "name": "CodeExecBot",
    "description": "Agent with code execution enabled",
    "agents": [],
    "oai_config": {},
    "code_execution_config": {},
    "version": "0.1.0",
    "code": "agent = AssistantAgent(code_execution_config={'work_dir': '/tmp'})",
}

SHELL_ACCESS_MANIFEST = {
    "name": "ShellBot",
    "description": "Agent with shell access",
    "agents": [],
    "oai_config": {},
    "code_execution_config": {},
    "version": "0.1.0",
    "code": "agent = AssistantAgent(code_execution_config={}, use_docker=False)",
}

USER_PROXY_MANIFEST = {
    "name": "ProxyBot",
    "description": "Agent with UserProxyAgent",
    "agents": [],
    "oai_config": {},
    "code_execution_config": {},
    "version": "1.0.0",
    "code": "proxy = UserProxyAgent(name='proxy')",
}

CMD_INJECTION_MANIFEST = {
    "name": "CmdBot",
    "description": "Agent with command injection",
    "agents": [
        {
            "name": "hacker",
            "type": "AssistantAgent",
            "functions": [
                {"name": "exploit", "code": "import os\nos.system('whoami')"},
            ],
        },
    ],
    "oai_config": {},
    "code_execution_config": {},
    "version": "0.1.0",
    "code": "",
}

MULTI_AGENT_MANIFEST = {
    "name": "TeamBot",
    "description": "Multi-agent AutoGen setup",
    "agents": [
        {
            "name": "coder",
            "type": "AssistantAgent",
            "functions": [
                {"name": "write_code", "code": "def write(spec):\n    return spec"},
            ],
        },
        {
            "name": "reviewer",
            "type": "AssistantAgent",
            "functions": [
                {"name": "review_code", "code": "def review(code):\n    return 'ok'"},
            ],
        },
    ],
    "oai_config": {"model": "gpt-4"},
    "code_execution_config": {},
    "version": "2.0.0",
    "code": "",
}


@pytest.mark.asyncio
async def test_import_autogen_agent(client: AsyncClient):
    """Import a clean AutoGen agent."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.post(
        "/api/v1/bridges/autogen/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "ChatBot"
    assert data["framework_source"] == "autogen"
    assert data["framework_trust_modifier"] == 1.0
    assert data["scan"]["scan_result"] == "clean"
    assert len(data["scan"]["vulnerabilities"]) == 0


@pytest.mark.asyncio
async def test_import_autogen_with_multiple_agents(client: AsyncClient):
    """Import an AutoGen agent with multiple sub-agents."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.post(
        "/api/v1/bridges/autogen/import",
        json=MULTI_AGENT_MANIFEST,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "TeamBot"
    assert data["framework_source"] == "autogen"
    assert data["framework_trust_modifier"] == 1.0


@pytest.mark.asyncio
async def test_autogen_scan_detects_code_execution(client: AsyncClient):
    """Code execution config should be flagged as critical."""
    from src.bridges.autogen.security import scan_skill

    code = "agent = AssistantAgent(code_execution_config={'work_dir': '/tmp'})"
    result = scan_skill(code, "code_exec")
    assert result.severity == "critical"
    assert any(v.pattern == "code_execution_enabled" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_autogen_scan_detects_shell_access(client: AsyncClient):
    """Shell access (use_docker=False) should be flagged as critical."""
    from src.bridges.autogen.security import scan_skill

    code = "agent = AssistantAgent(code_execution_config={}, use_docker=False)"
    result = scan_skill(code, "shell_bot")
    assert result.severity == "critical"
    assert any(v.pattern == "shell_command_access" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_autogen_scan_detects_user_proxy(client: AsyncClient):
    """UserProxyAgent should be flagged as warning."""
    from src.bridges.autogen.security import scan_skill

    code = "proxy = UserProxyAgent(name='proxy')"
    result = scan_skill(code, "proxy")
    assert result.severity == "warnings"
    assert any(v.pattern == "unrestricted_agent" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_autogen_scan_clean(client: AsyncClient):
    """Clean code should produce clean scan result."""
    from src.bridges.autogen.security import scan_skill

    code = "def hello():\n    return 42"
    result = scan_skill(code, "clean_skill")
    assert result.severity == "clean"
    assert len(result.vulnerabilities) == 0


@pytest.mark.asyncio
async def test_get_autogen_scan(client: AsyncClient):
    """Get scan result for an imported AutoGen agent."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    import_resp = await client.post(
        "/api/v1/bridges/autogen/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token),
    )
    entity_id = import_resp.json()["entity_id"]
    resp = await client.get(
        f"/api/v1/bridges/autogen/scan/{entity_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == entity_id
    assert data["scan_result"] == "clean"
    assert data["framework"] == "autogen"


@pytest.mark.asyncio
async def test_rescan_autogen_agent(client: AsyncClient):
    """Rescan with clean code should restore trust modifier."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    import_resp = await client.post(
        "/api/v1/bridges/autogen/import",
        json=CMD_INJECTION_MANIFEST,
        headers=_auth(token),
    )
    assert import_resp.status_code == 200
    entity_id = import_resp.json()["entity_id"]
    assert import_resp.json()["framework_trust_modifier"] == 0.5

    resp = await client.post(
        f"/api/v1/bridges/autogen/rescan/{entity_id}",
        json={"agents": [], "code_execution_config": {}, "code": ""},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scan_result"] == "clean"


@pytest.mark.asyncio
async def test_rescan_autogen_unauthorized(client: AsyncClient):
    """Non-operator cannot rescan another operator's agent."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    token_other, _ = await _setup_user(client, USER_OTHER)
    import_resp = await client.post(
        "/api/v1/bridges/autogen/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token_op),
    )
    entity_id = import_resp.json()["entity_id"]
    resp = await client.post(
        f"/api/v1/bridges/autogen/rescan/{entity_id}",
        json={"agents": [], "code_execution_config": {}, "code": ""},
        headers=_auth(token_other),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_autogen_scan_command_injection(client: AsyncClient):
    """Base command injection patterns should still be detected."""
    from src.bridges.autogen.security import scan_skill

    code = "import os\nos.system('rm -rf /')"
    result = scan_skill(code, "cmd_skill")
    assert result.severity == "critical"
    assert any(v.pattern == "command_injection_os_system" for v in result.vulnerabilities)
