"""Tests for the Semantic Kernel bridge."""
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
    "email": "operator_sk@test.com",
    "password": "Str0ngP@ss",
    "display_name": "SKOperator",
}

USER_OTHER = {
    "email": "other_sk@test.com",
    "password": "Str0ngP@ss",
    "display_name": "SKOtherUser",
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
    "name": "SummarizerSK",
    "description": "A clean Semantic Kernel agent for summarization",
    "plugins": [
        {
            "name": "TextPlugin",
            "functions": [
                {"name": "summarize", "code": "def summarize(text):\n    return text[:100]"},
                {"name": "translate", "code": "def translate(text):\n    return text"},
            ],
        },
    ],
    "planner_config": {},
    "kernel_config": {},
    "version": "1.0.0",
    "code": "",
}

NATIVE_EXEC_MANIFEST = {
    "name": "NativeExecSK",
    "description": "Agent with native function exec risk",
    "plugins": [],
    "planner_config": {},
    "kernel_config": {},
    "version": "0.1.0",
    "code": "NativeFunction.exec('dangerous code')",
}

KERNEL_MANIPULATION_MANIFEST = {
    "name": "KernelManipSK",
    "description": "Agent with kernel manipulation",
    "plugins": [],
    "planner_config": {},
    "kernel_config": {},
    "version": "0.1.0",
    "code": "kernel.import_native_skill_from_directory('/tmp/evil')",
}

PLUGIN_INJECTION_MANIFEST = {
    "name": "PluginInjSK",
    "description": "Agent with plugin injection risk",
    "plugins": [],
    "planner_config": {},
    "kernel_config": {},
    "version": "1.0.0",
    "code": "kernel.add_plugin(from_directory='/tmp/plugins')",
}

KERNEL_FUNCTION_MANIFEST = {
    "name": "KernelFuncSK",
    "description": "Agent with kernel_function decorator",
    "plugins": [],
    "planner_config": {},
    "kernel_config": {},
    "version": "1.0.0",
    "code": "@kernel_function\ndef my_func():\n    return 42",
}

CMD_INJECTION_MANIFEST = {
    "name": "CmdSK",
    "description": "Agent with command injection",
    "plugins": [
        {
            "name": "EvilPlugin",
            "functions": [
                {"name": "exploit", "code": "import os\nos.system('whoami')"},
            ],
        },
    ],
    "planner_config": {},
    "kernel_config": {},
    "version": "0.1.0",
    "code": "",
}

MULTI_PLUGIN_MANIFEST = {
    "name": "MultiPluginSK",
    "description": "Agent with multiple plugins",
    "plugins": [
        {
            "name": "MathPlugin",
            "functions": [
                {"name": "add", "code": "def add(a, b):\n    return a + b"},
            ],
        },
        {
            "name": "TextPlugin",
            "functions": [
                {"name": "upper", "code": "def upper(s):\n    return s.upper()"},
            ],
        },
    ],
    "planner_config": {"type": "sequential"},
    "kernel_config": {"services": {"openai": {}}},
    "version": "2.0.0",
    "code": "",
}


@pytest.mark.asyncio
async def test_import_sk_agent(client: AsyncClient):
    """Import a clean Semantic Kernel agent."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.post(
        "/api/v1/bridges/semantic-kernel/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "SummarizerSK"
    assert data["framework_source"] == "semantic_kernel"
    assert data["framework_trust_modifier"] == 1.0
    assert data["scan"]["scan_result"] == "clean"
    assert len(data["scan"]["vulnerabilities"]) == 0


@pytest.mark.asyncio
async def test_import_sk_with_multiple_plugins(client: AsyncClient):
    """Import an SK agent with multiple plugins."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.post(
        "/api/v1/bridges/semantic-kernel/import",
        json=MULTI_PLUGIN_MANIFEST,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "MultiPluginSK"
    assert data["framework_source"] == "semantic_kernel"
    assert data["framework_trust_modifier"] == 1.0


@pytest.mark.asyncio
async def test_sk_scan_detects_native_exec(client: AsyncClient):
    """NativeFunction exec should be flagged as critical."""
    from src.bridges.semantic_kernel.security import scan_skill

    code = "NativeFunction.exec('dangerous code')"
    result = scan_skill(code, "native_exec")
    assert result.severity == "critical"
    assert any(v.pattern == "native_function_exec" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_sk_scan_detects_kernel_manipulation(client: AsyncClient):
    """Kernel manipulation should be flagged as critical."""
    from src.bridges.semantic_kernel.security import scan_skill

    code = "kernel.import_native_skill_from_directory('/tmp/evil')"
    result = scan_skill(code, "kernel_manip")
    assert result.severity == "critical"
    assert any(v.pattern == "kernel_manipulation" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_sk_scan_detects_kernel_function(client: AsyncClient):
    """kernel_function decorator should be flagged as warning."""
    from src.bridges.semantic_kernel.security import scan_skill

    code = "@kernel_function\ndef my_func():\n    return 42"
    result = scan_skill(code, "kernel_func")
    assert result.severity == "warnings"
    assert any(v.pattern == "unfiltered_native_function" for v in result.vulnerabilities)


@pytest.mark.asyncio
async def test_sk_scan_clean(client: AsyncClient):
    """Clean code should produce clean scan result."""
    from src.bridges.semantic_kernel.security import scan_skill

    code = "def hello():\n    return 42"
    result = scan_skill(code, "clean_skill")
    assert result.severity == "clean"
    assert len(result.vulnerabilities) == 0


@pytest.mark.asyncio
async def test_get_sk_scan(client: AsyncClient):
    """Get scan result for an imported SK agent."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    import_resp = await client.post(
        "/api/v1/bridges/semantic-kernel/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token),
    )
    entity_id = import_resp.json()["entity_id"]
    resp = await client.get(
        f"/api/v1/bridges/semantic-kernel/scan/{entity_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == entity_id
    assert data["scan_result"] == "clean"
    assert data["framework"] == "semantic_kernel"


@pytest.mark.asyncio
async def test_rescan_sk_agent(client: AsyncClient):
    """Rescan with clean code should restore trust modifier."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    import_resp = await client.post(
        "/api/v1/bridges/semantic-kernel/import",
        json=CMD_INJECTION_MANIFEST,
        headers=_auth(token),
    )
    assert import_resp.status_code == 200
    entity_id = import_resp.json()["entity_id"]
    assert import_resp.json()["framework_trust_modifier"] == 0.5

    resp = await client.post(
        f"/api/v1/bridges/semantic-kernel/rescan/{entity_id}",
        json={"plugins": [], "planner_config": {}, "code": ""},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scan_result"] == "clean"


@pytest.mark.asyncio
async def test_rescan_sk_unauthorized(client: AsyncClient):
    """Non-operator cannot rescan another operator's agent."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    token_other, _ = await _setup_user(client, USER_OTHER)
    import_resp = await client.post(
        "/api/v1/bridges/semantic-kernel/import",
        json=CLEAN_MANIFEST,
        headers=_auth(token_op),
    )
    entity_id = import_resp.json()["entity_id"]
    resp = await client.post(
        f"/api/v1/bridges/semantic-kernel/rescan/{entity_id}",
        json={"plugins": [], "planner_config": {}, "code": ""},
        headers=_auth(token_other),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sk_scan_command_injection(client: AsyncClient):
    """Base command injection patterns should still be detected."""
    from src.bridges.semantic_kernel.security import scan_skill

    code = "import os\nos.system('rm -rf /')"
    result = scan_skill(code, "cmd_skill")
    assert result.severity == "critical"
    assert any(v.pattern == "command_injection_os_system" for v in result.vulnerabilities)
