"""Tests for the AgentGraph SDK CLI commands.

These tests require the agentgraph_sdk package to be installed.
If not installed, they are automatically skipped.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Make the SDK importable from the repo checkout
_SDK_ROOT = Path(__file__).resolve().parent.parent / "sdk"
if str(_SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(_SDK_ROOT))

agentgraph_sdk = pytest.importorskip("agentgraph_sdk")

from agentgraph_sdk.cli import cli  # noqa: E402
from click.testing import CliRunner  # noqa: E402


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestWhoami:
    """Tests for the `agentgraph whoami` command."""

    def test_whoami_not_authenticated(self, runner: CliRunner) -> None:
        """whoami should fail when no credentials are stored."""
        with patch("agentgraph_sdk.cli._load_config", return_value={}):
            result = runner.invoke(cli, ["whoami"])
            assert result.exit_code != 0
            assert "Not authenticated" in result.output

    def test_whoami_success(self, runner: CliRunner) -> None:
        """whoami should display identity info."""
        me_data = {
            "id": "abc-123",
            "display_name": "TestBot",
            "type": "agent",
            "did_web": "did:web:agentgraph.co:agents:abc-123",
            "email": "test@example.com",
            "is_active": True,
            "is_admin": False,
        }

        mock_client = AsyncMock()
        mock_client.get_me = AsyncMock(return_value=me_data)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        config = {"token": "test-token", "base_url": "http://localhost:8000"}

        with patch("agentgraph_sdk.cli._load_config", return_value=config), \
             patch("agentgraph_sdk.cli._get_client", return_value=mock_client):
            result = runner.invoke(cli, ["whoami"])
            assert result.exit_code == 0
            assert "TestBot" in result.output
            assert "abc-123" in result.output
            assert "did:web:agentgraph.co" in result.output
            assert "test@example.com" in result.output


class TestStatus:
    """Tests for the `agentgraph status` command."""

    def test_status_success(self, runner: CliRunner) -> None:
        """status should display entity info and trust score."""
        me_data = {
            "id": "xyz-789",
            "display_name": "StatusBot",
            "type": "ai_agent",
            "did_web": "did:web:agentgraph.co:agents:xyz-789",
            "is_verified": True,
            "email_verified": True,
        }
        trust_data = {
            "score": 0.85,
            "components": {"identity": 0.9, "behavior": 0.8},
        }

        mock_client = AsyncMock()
        mock_client.get_me = AsyncMock(return_value=me_data)
        mock_client.get_trust_score = AsyncMock(return_value=trust_data)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("agentgraph_sdk.cli._get_client", return_value=mock_client):
            result = runner.invoke(cli, ["status"])
            assert result.exit_code == 0
            assert "StatusBot" in result.output
            assert "0.85" in result.output
            assert "identity" in result.output
            assert "Verified: True" in result.output

    def test_status_no_trust_score(self, runner: CliRunner) -> None:
        """status should handle missing trust score gracefully."""
        from agentgraph_sdk.client import AgentGraphError

        me_data = {
            "id": "xyz-789",
            "display_name": "NewBot",
            "type": "ai_agent",
            "did_web": None,
            "is_verified": False,
            "email_verified": False,
        }

        mock_client = AsyncMock()
        mock_client.get_me = AsyncMock(return_value=me_data)
        mock_client.get_trust_score = AsyncMock(
            side_effect=AgentGraphError("Not found", status_code=404)
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("agentgraph_sdk.cli._get_client", return_value=mock_client):
            result = runner.invoke(cli, ["status"])
            assert result.exit_code == 0
            assert "N/A" in result.output
            assert "NewBot" in result.output


class TestRegisterCommand:
    """Tests for the `agentgraph register` command."""

    def test_register_with_capabilities(self, runner: CliRunner) -> None:
        """register should accept --capabilities flag."""
        agent_data = {
            "agent": {"id": "new-123", "display_name": "MyAgent"},
            "api_key": "ag_key_new",
        }

        mock_client = AsyncMock()
        mock_client.register_agent = AsyncMock(return_value=agent_data)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        config = {"base_url": "http://localhost:8000"}
        saved_configs: list[dict] = []

        def mock_save(c: dict) -> None:
            saved_configs.append(c)

        with patch("agentgraph_sdk.cli._get_client", return_value=mock_client), \
             patch("agentgraph_sdk.cli._load_config", return_value=config), \
             patch("agentgraph_sdk.cli._save_config", side_effect=mock_save):
            result = runner.invoke(
                cli,
                ["register", "--name", "MyAgent", "--capabilities", "web_search,code_review"],
            )
            assert result.exit_code == 0
            assert "MyAgent" in result.output
            assert "web_search,code_review" in result.output
            assert "ag_key_new" in result.output


class TestLoginCommand:
    """Tests for the `agentgraph login` command."""

    def test_login_success(self, runner: CliRunner) -> None:
        mock_client = AsyncMock()
        mock_client.authenticate = AsyncMock(return_value="tok_abc")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        saved: list[dict] = []

        with patch("agentgraph_sdk.cli.AgentGraphClient", return_value=mock_client), \
             patch("agentgraph_sdk.cli._load_config", return_value={}), \
             patch("agentgraph_sdk.cli._save_config", side_effect=lambda c: saved.append(c)):
            result = runner.invoke(
                cli,
                ["login", "--email", "test@example.com", "--password", "pass"],
            )
            assert result.exit_code == 0
            assert "Login successful" in result.output
            assert len(saved) == 1
            assert saved[0]["token"] == "tok_abc"
