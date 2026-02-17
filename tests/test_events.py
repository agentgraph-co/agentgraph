from __future__ import annotations

import pytest

from src.events import clear_handlers, emit, register_handler


@pytest.fixture(autouse=True)
def _clean_handlers():
    clear_handlers()
    yield
    clear_handlers()


@pytest.mark.asyncio
async def test_emit_calls_handler():
    received = []

    async def handler(event_type, payload):
        received.append((event_type, payload))

    register_handler("test.event", handler)
    await emit("test.event", {"key": "value"})

    assert len(received) == 1
    assert received[0] == ("test.event", {"key": "value"})


@pytest.mark.asyncio
async def test_emit_multiple_handlers():
    count = {"a": 0, "b": 0}

    async def handler_a(event_type, payload):
        count["a"] += 1

    async def handler_b(event_type, payload):
        count["b"] += 1

    register_handler("multi", handler_a)
    register_handler("multi", handler_b)
    await emit("multi", {})

    assert count["a"] == 1
    assert count["b"] == 1


@pytest.mark.asyncio
async def test_emit_no_handlers():
    # Should not raise
    await emit("unregistered.event", {"data": 123})


@pytest.mark.asyncio
async def test_handler_error_doesnt_crash():
    results = []

    async def bad_handler(event_type, payload):
        raise ValueError("Oops")

    async def good_handler(event_type, payload):
        results.append("ok")

    register_handler("fail", bad_handler)
    register_handler("fail", good_handler)
    await emit("fail", {})

    # Good handler should still run despite bad handler failing
    assert results == ["ok"]


@pytest.mark.asyncio
async def test_different_event_types_isolated():
    a_calls = []
    b_calls = []

    async def handler_a(event_type, payload):
        a_calls.append(1)

    async def handler_b(event_type, payload):
        b_calls.append(1)

    register_handler("type_a", handler_a)
    register_handler("type_b", handler_b)

    await emit("type_a", {})

    assert len(a_calls) == 1
    assert len(b_calls) == 0
