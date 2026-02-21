"""MCP bridge helper for agent framework integration."""
from __future__ import annotations

from typing import Any

from agentgraph.client import AgentGraphClient
from agentgraph.models import Tool


class MCPBridge:
    """Helper for MCP-compatible tool discovery and execution.

    Usage:
        bridge = MCPBridge(client)
        tools = await bridge.discover()
        result = await bridge.execute("agentgraph_get_feed", limit=10)
    """

    def __init__(self, client: AgentGraphClient):
        self._client = client
        self._tools: dict[str, Tool] = {}

    async def discover(self) -> list[Tool]:
        tools = await self._client.mcp_tools()
        self._tools = {t.name: t for t in tools}
        return tools

    async def execute(self, tool_name: str, **arguments: Any) -> dict[str, Any]:
        return await self._client.mcp_execute(tool_name, **arguments)

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
