"""Anthropic client retries transient network faults (the ConnectTimeout Sentry case)."""
import httpx
import pytest

from src.marketing.config import marketing_settings
from src.marketing.llm import anthropic_client


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Async-context httpx.AsyncClient stand-in with a scripted post() sequence."""

    def __init__(self, behaviors):
        self._behaviors = list(behaviors)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        b = self._behaviors[self.calls]
        self.calls += 1
        if isinstance(b, Exception):
            raise b
        return b


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setattr(marketing_settings, "anthropic_api_key", "sk-test", raising=False)


def _install(monkeypatch, behaviors):
    holder = {}

    def _factory(*a, **k):
        holder["client"] = _FakeClient(behaviors)
        return holder["client"]

    monkeypatch.setattr(anthropic_client.asyncio, "sleep", lambda *_a, **_k: _noop())
    monkeypatch.setattr(anthropic_client.httpx, "AsyncClient", _factory)
    return holder


async def _noop():
    return None


_OK = _FakeResp({
    "content": [{"type": "text", "text": "hello"}],
    "usage": {"input_tokens": 3, "output_tokens": 1},
})


@pytest.mark.asyncio
async def test_retries_transient_connect_timeout_then_succeeds(monkeypatch):
    holder = _install(monkeypatch, [httpx.ConnectTimeout("boom"), _OK])
    res = await anthropic_client.generate("hi")
    assert res.error is None
    assert res.text == "hello"
    assert holder["client"].calls == 2  # first failed, retry succeeded


@pytest.mark.asyncio
async def test_exhausts_and_returns_network_error(monkeypatch):
    holder = _install(monkeypatch, [httpx.ConnectTimeout("x")] * 3)
    res = await anthropic_client.generate("hi")
    assert res.error == "network: ConnectTimeout"
    assert res.text == ""
    assert holder["client"].calls == 3


@pytest.mark.asyncio
async def test_success_first_try_no_retry(monkeypatch):
    holder = _install(monkeypatch, [_OK])
    res = await anthropic_client.generate("hi")
    assert res.error is None and holder["client"].calls == 1
