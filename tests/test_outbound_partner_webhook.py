"""Tests for outbound scan-change webhooks — HMAC partner-signature contract.

Covers:
- Event type canonicalization ("scan-change")
- HMAC-SHA256 signature header when signing_secret is registered
- No HMAC header when signing_secret is absent (JWS-only path)
- Timestamp header within the ±5 min window
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.trust import outbound_webhooks


@pytest.mark.asyncio
async def test_hmac_signature_present_when_secret_registered():
    """If a subscription has a signing_secret, the outbound POST includes
    X-Partner-Signature computed with HMAC-SHA256 over the raw body."""
    secret = "test-shared-secret-abc123"
    captured: dict = {}

    class _FakeResp:
        status_code = 200

    async def _fake_post(self, url, *, content, headers):  # noqa: ARG001
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        return _FakeResp()

    sub = [{
        "repo": "owner/repo",
        "callback_url": "https://partner.example.com/hook",
        "provider": "moltbridge",
        "signing_secret": secret,
    }]
    with patch.object(
        outbound_webhooks, "_get_subscriptions", AsyncMock(return_value=sub),
    ), patch("httpx.AsyncClient.post", _fake_post):
        await outbound_webhooks.notify_scan_change(
            "owner/repo", new_score=82, old_score=71,
        )

    assert captured["url"] == "https://partner.example.com/hook"
    assert captured["headers"]["X-AgentGraph-Event"] == "scan-change"

    sig_header = captured["headers"]["X-Partner-Signature"]
    assert sig_header.startswith("sha256=")
    expected = hmac.new(
        secret.encode("utf-8"),
        captured["content"],
        hashlib.sha256,
    ).hexdigest()
    assert sig_header == f"sha256={expected}"

    # Timestamp within ±5 min
    ts = datetime.fromisoformat(captured["headers"]["X-Partner-Timestamp"])
    now = datetime.now(timezone.utc)
    assert abs((now - ts).total_seconds()) < 300


@pytest.mark.asyncio
async def test_no_hmac_headers_when_secret_absent():
    """Subscriptions without a signing_secret get JWS-only — no partner headers."""
    captured: dict = {}

    class _FakeResp:
        status_code = 200

    async def _fake_post(self, url, *, content, headers):  # noqa: ARG001
        captured["headers"] = headers
        return _FakeResp()

    sub = [{
        "repo": "owner/repo",
        "callback_url": "https://partner.example.com/hook",
        "provider": "someprovider",
        # no signing_secret
    }]
    with patch.object(
        outbound_webhooks, "_get_subscriptions", AsyncMock(return_value=sub),
    ), patch("httpx.AsyncClient.post", _fake_post):
        await outbound_webhooks.notify_scan_change(
            "owner/repo", new_score=50, old_score=None,
        )

    assert "X-Partner-Signature" not in captured["headers"]
    assert "X-Partner-Timestamp" not in captured["headers"]
    assert captured["headers"]["X-AgentGraph-Event"] == "scan-change"


@pytest.mark.asyncio
async def test_event_type_canonicalized():
    """Body carries 'scan-change' as the top-level type, with legacy alias
    preserved inside the signed JWS payload."""
    captured: dict = {}

    class _FakeResp:
        status_code = 200

    async def _fake_post(self, url, *, content, headers):  # noqa: ARG001
        captured["content"] = content
        return _FakeResp()

    sub = [{
        "repo": "owner/repo",
        "callback_url": "https://partner.example.com/hook",
        "provider": "moltbridge",
    }]
    with patch.object(
        outbound_webhooks, "_get_subscriptions", AsyncMock(return_value=sub),
    ), patch("httpx.AsyncClient.post", _fake_post):
        await outbound_webhooks.notify_scan_change(
            "owner/repo", new_score=90, old_score=85,
        )

    import json as _json

    body = _json.loads(captured["content"])
    assert body["type"] == "scan-change"
    assert body["repo"] == "owner/repo"
    assert body["new_score"] == 90
    assert "jws" in body
