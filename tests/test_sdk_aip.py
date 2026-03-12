"""Tests for SDK AIP, marketplace, and WebSocket enhancements."""
from __future__ import annotations

import asyncio

pytest_plugins: list[str] = []
agentgraph = __import__("pytest").importorskip("agentgraph")

# ---- Model tests ----


def test_delegation_model():
    """Delegation model with defaults."""
    from agentgraph.models import Delegation

    d = Delegation(
        id="abc",
        delegator_entity_id="d1",
        delegate_entity_id="d2",
        task_description="test task",
        correlation_id="corr123",
    )
    assert d.status == "pending"
    assert d.correlation_id == "corr123"
    assert d.constraints == {}
    assert d.result is None
    assert d.timeout_at is None
    assert d.created_at is None


def test_delegation_model_full():
    """Delegation model with all fields populated."""
    from agentgraph.models import Delegation

    d = Delegation(
        id="abc",
        delegator_entity_id="d1",
        delegate_entity_id="d2",
        task_description="test task",
        correlation_id="corr123",
        status="completed",
        result={"summary": "done"},
        constraints={"max_cost": 100},
        timeout_at="2026-03-01T00:00:00Z",
        created_at="2026-02-22T10:00:00Z",
    )
    assert d.status == "completed"
    assert d.result == {"summary": "done"}
    assert d.constraints == {"max_cost": 100}


def test_capability_model():
    """Capability model with defaults."""
    from agentgraph.models import Capability

    c = Capability(id="c1", entity_id="e1", capability_name="search")
    assert c.version == "1.0.0"
    assert c.description == ""
    assert c.input_schema == {}
    assert c.output_schema == {}
    assert c.is_active is True


def test_capability_model_full():
    """Capability model with all fields."""
    from agentgraph.models import Capability

    c = Capability(
        id="c1",
        entity_id="e1",
        capability_name="data-analysis",
        version="2.0.0",
        description="Analyze data",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        is_active=False,
    )
    assert c.version == "2.0.0"
    assert c.is_active is False
    assert c.description == "Analyze data"


def test_dispute_model():
    """Dispute model with defaults."""
    from agentgraph.models import Dispute

    d = Dispute(id="d1", transaction_id="t1", opened_by="e1", reason="quality")
    assert d.status == "open"
    assert d.resolution is None
    assert d.created_at is None


def test_transaction_model():
    """Transaction model with defaults."""
    from agentgraph.models import Transaction

    t = Transaction(
        id="t1",
        buyer_entity_id="b1",
        seller_entity_id="s1",
        status="escrow",
        listing_title="Test",
        listing_category="service",
    )
    assert t.amount_cents == 0
    assert t.listing_id is None
    assert t.notes is None


def test_transaction_model_full():
    """Transaction model with all fields."""
    from agentgraph.models import Transaction

    t = Transaction(
        id="t1",
        listing_id="l1",
        buyer_entity_id="b1",
        seller_entity_id="s1",
        amount_cents=4999,
        status="completed",
        listing_title="Premium Tool",
        listing_category="tool",
        notes="For Q4 project",
        created_at="2026-02-22T10:00:00Z",
    )
    assert t.amount_cents == 4999
    assert t.listing_id == "l1"
    assert t.notes == "For Q4 project"


def test_insights_model():
    """InsightsData generic container."""
    from agentgraph.models import InsightsData

    i = InsightsData(data={"total": 100})
    assert i.data["total"] == 100


def test_insights_model_default():
    """InsightsData default empty dict."""
    from agentgraph.models import InsightsData

    i = InsightsData()
    assert i.data == {}


# ---- Exception tests ----


def test_dispute_error():
    """DisputeError with status code."""
    from agentgraph.exceptions import DisputeError

    e = DisputeError("test", status_code=400)
    assert e.status_code == 400
    assert str(e) == "test"


def test_protocol_error():
    """ProtocolError basic."""
    from agentgraph.exceptions import ProtocolError

    e = ProtocolError("invalid message")
    assert str(e) == "invalid message"
    assert e.status_code is None


def test_escrow_error():
    """EscrowError with status code."""
    from agentgraph.exceptions import EscrowError

    e = EscrowError("payment failed", status_code=402)
    assert e.status_code == 402


def test_new_exceptions_inherit_from_base():
    """All new exceptions inherit from AgentGraphError."""
    from agentgraph.exceptions import (
        AgentGraphError,
        DisputeError,
        EscrowError,
        ProtocolError,
    )

    assert issubclass(DisputeError, AgentGraphError)
    assert issubclass(ProtocolError, AgentGraphError)
    assert issubclass(EscrowError, AgentGraphError)


# ---- Client mixin integration tests ----


def test_client_has_aip_methods():
    """Verify AgentGraphClient has AIP mixin methods."""
    from agentgraph.client import AgentGraphClient

    client = AgentGraphClient("http://test")
    assert hasattr(client, "aip_discover")
    assert hasattr(client, "aip_delegate")
    assert hasattr(client, "aip_get_delegation")
    assert hasattr(client, "aip_list_delegations")
    assert hasattr(client, "aip_update_delegation")
    assert hasattr(client, "aip_register_capability")
    assert hasattr(client, "aip_get_capabilities")
    assert hasattr(client, "aip_schema")
    assert hasattr(client, "aip_negotiate")


def test_client_has_marketplace_methods():
    """Verify AgentGraphClient has marketplace mixin methods."""
    from agentgraph.client import AgentGraphClient

    client = AgentGraphClient("http://test")
    assert hasattr(client, "purchase_listing")
    assert hasattr(client, "confirm_purchase")
    assert hasattr(client, "get_transaction")
    assert hasattr(client, "get_purchase_history")
    assert hasattr(client, "open_dispute")
    assert hasattr(client, "get_disputes")
    assert hasattr(client, "create_capability_listing")
    assert hasattr(client, "adopt_capability")
    assert hasattr(client, "get_insights")


def test_client_aip_methods_are_coroutines():
    """AIP methods should be coroutine functions."""
    import inspect

    from agentgraph.client import AgentGraphClient

    client = AgentGraphClient("http://test")
    assert inspect.iscoroutinefunction(client.aip_discover)
    assert inspect.iscoroutinefunction(client.aip_delegate)
    assert inspect.iscoroutinefunction(client.aip_schema)


def test_client_marketplace_methods_are_coroutines():
    """Marketplace methods should be coroutine functions."""
    import inspect

    from agentgraph.client import AgentGraphClient

    client = AgentGraphClient("http://test")
    assert inspect.iscoroutinefunction(client.purchase_listing)
    assert inspect.iscoroutinefunction(client.open_dispute)
    assert inspect.iscoroutinefunction(client.get_insights)


# ---- WebSocket client tests ----


def test_ws_client_creation():
    """WebSocket client basic construction."""
    from agentgraph.ws import AgentGraphWebSocket

    ws = AgentGraphWebSocket(
        base_url="http://localhost:8000",
        access_token="test_token",
        channels=["feed", "marketplace"],
    )
    assert "ws://localhost:8000" in ws.ws_url
    assert "token=test_token" in ws.ws_url
    assert "channels=feed,marketplace" in ws.ws_url


def test_ws_handler_registration():
    """Handler registration for channels."""
    from agentgraph.ws import AgentGraphWebSocket

    ws = AgentGraphWebSocket("http://test", "token")

    async def handler(data):
        pass

    ws.on("feed", handler)
    ws.on_any(handler)
    assert len(ws._handlers["feed"]) == 1
    assert len(ws._handlers["*"]) == 1


def test_ws_url_https_to_wss():
    """HTTPS URLs should convert to WSS."""
    from agentgraph.ws import AgentGraphWebSocket

    ws = AgentGraphWebSocket("https://api.agentgraph.co", "token")
    assert ws.ws_url.startswith("wss://")


def test_ws_url_http_to_ws():
    """HTTP URLs should convert to WS."""
    from agentgraph.ws import AgentGraphWebSocket

    ws = AgentGraphWebSocket("http://localhost:8000", "token")
    assert ws.ws_url.startswith("ws://")


def test_ws_default_channels():
    """Default channels are feed and notifications."""
    from agentgraph.ws import AgentGraphWebSocket

    ws = AgentGraphWebSocket("http://test", "token")
    assert "channels=feed,notifications" in ws.ws_url


def test_ws_dispatch_skips_pong():
    """Pong messages should not be dispatched to handlers."""
    from agentgraph.ws import AgentGraphWebSocket

    ws = AgentGraphWebSocket("http://test", "token")
    called = []

    async def handler(data):
        called.append(data)

    ws.on_any(handler)

    # _dispatch is async, run it
    asyncio.get_event_loop().run_until_complete(
        ws._dispatch({"type": "pong"})
    )
    assert len(called) == 0


def test_ws_dispatch_routes_to_channel():
    """Messages should be dispatched to the correct channel handler."""
    from agentgraph.ws import AgentGraphWebSocket

    ws = AgentGraphWebSocket("http://test", "token")
    feed_msgs = []
    all_msgs = []

    async def feed_handler(data):
        feed_msgs.append(data)

    async def any_handler(data):
        all_msgs.append(data)

    ws.on("feed", feed_handler)
    ws.on_any(any_handler)

    msg = {"channel": "feed", "type": "new_post", "content": "hello"}
    asyncio.get_event_loop().run_until_complete(ws._dispatch(msg))

    assert len(feed_msgs) == 1
    assert feed_msgs[0]["content"] == "hello"
    assert len(all_msgs) == 1


def test_ws_multiple_handlers_per_channel():
    """Multiple handlers on same channel should all be called."""
    from agentgraph.ws import AgentGraphWebSocket

    ws = AgentGraphWebSocket("http://test", "token")
    results = []

    async def handler_a(data):
        results.append("a")

    async def handler_b(data):
        results.append("b")

    ws.on("feed", handler_a)
    ws.on("feed", handler_b)

    msg = {"channel": "feed", "type": "test"}
    asyncio.get_event_loop().run_until_complete(ws._dispatch(msg))
    assert results == ["a", "b"]


# ---- Package-level exports test ----


def test_package_exports():
    """Verify new types are exported from the package."""
    import agentgraph

    assert hasattr(agentgraph, "AgentGraphWebSocket")
    assert hasattr(agentgraph, "Delegation")
    assert hasattr(agentgraph, "Capability")
    assert hasattr(agentgraph, "Dispute")
    assert hasattr(agentgraph, "Transaction")
    assert hasattr(agentgraph, "InsightsData")
    assert hasattr(agentgraph, "DisputeError")
    assert hasattr(agentgraph, "ProtocolError")
    assert hasattr(agentgraph, "EscrowError")


def test_version_updated():
    """SDK version should be 0.2.0."""
    import agentgraph

    assert agentgraph.__version__ == "0.2.0"
