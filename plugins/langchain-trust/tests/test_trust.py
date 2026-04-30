"""Unit tests for agentgraph_langchain trust module."""
from __future__ import annotations

import httpx
import pytest
import respx
from agentgraph_langchain.trust import (
    AgentGraphTrustCallback,
    get_trust_badge_url,
    run_security_scan,
    verify_trust,
)

BASE = "https://agentgraph.co/api/v1"


class TestVerifyTrust:
    @pytest.mark.asyncio
    @respx.mock
    async def test_trust_above_threshold(self) -> None:
        respx.get(f"{BASE}/trust/entity-123").mock(
            return_value=httpx.Response(200, json={"score": 0.85})
        )
        result = await verify_trust("entity-123", min_score=0.5)
        assert result is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_trust_below_threshold(self) -> None:
        respx.get(f"{BASE}/trust/entity-456").mock(
            return_value=httpx.Response(200, json={"score": 0.3})
        )
        result = await verify_trust("entity-456", min_score=0.5)
        assert result is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_trust_exact_threshold(self) -> None:
        respx.get(f"{BASE}/trust/entity-789").mock(
            return_value=httpx.Response(200, json={"score": 0.5})
        )
        result = await verify_trust("entity-789", min_score=0.5)
        assert result is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_trust_api_error(self) -> None:
        respx.get(f"{BASE}/trust/bad-id").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await verify_trust("bad-id")

    @pytest.mark.asyncio
    @respx.mock
    async def test_custom_base_url(self) -> None:
        custom = "https://custom.example.com/api/v1"
        respx.get(f"{custom}/trust/ent-1").mock(
            return_value=httpx.Response(200, json={"score": 0.9})
        )
        result = await verify_trust("ent-1", base_url=custom)
        assert result is True


class TestGetTrustBadgeUrl:
    def test_default_style(self) -> None:
        url = get_trust_badge_url("entity-123")
        assert url == f"{BASE}/trust/entity-123/badge?style=compact"

    def test_custom_style(self) -> None:
        url = get_trust_badge_url("entity-123", style="full")
        assert url == f"{BASE}/trust/entity-123/badge?style=full"

    def test_custom_base_url(self) -> None:
        url = get_trust_badge_url("e1", base_url="https://example.com/api/v1")
        assert url == "https://example.com/api/v1/trust/e1/badge?style=compact"


class TestRunSecurityScan:
    @pytest.mark.asyncio
    @respx.mock
    async def test_scan_success(self) -> None:
        scan_result = {
            "repo": "owner/repo",
            "vulnerabilities": 3,
            "critical": 0,
            "high": 1,
            "medium": 2,
        }
        respx.post(f"{BASE}/security/scan").mock(
            return_value=httpx.Response(200, json=scan_result)
        )
        result = await run_security_scan("owner/repo")
        assert result["vulnerabilities"] == 3
        assert result["high"] == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_scan_with_token(self) -> None:
        respx.post(f"{BASE}/security/scan").mock(
            return_value=httpx.Response(200, json={"vulnerabilities": 0})
        )
        result = await run_security_scan("owner/private-repo", token="ghp_xxx")
        assert result["vulnerabilities"] == 0


class TestAgentGraphTrustCallback:
    def test_on_chain_start_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.INFO):
            cb = AgentGraphTrustCallback(
                did="did:agentgraph:abc",
                api_key="test-key",
            )
            cb.on_chain_start(
                serialized={"name": "TestChain"},
                inputs={"query": "hello"},
            )
        assert "did:agentgraph:abc" in caplog.text
        assert "TestChain" in caplog.text

    def test_on_chain_end_no_report(self) -> None:
        cb = AgentGraphTrustCallback(
            did="did:agentgraph:abc",
            api_key="test-key",
            report_results=False,
        )
        # Should not raise even without network
        cb.on_chain_end(outputs={"result": "done"})

    def test_on_chain_error_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            cb = AgentGraphTrustCallback(
                did="did:agentgraph:def",
                api_key="test-key",
            )
            cb.on_chain_error(error=ValueError("test error"))
        assert "did:agentgraph:def" in caplog.text
        assert "test error" in caplog.text
