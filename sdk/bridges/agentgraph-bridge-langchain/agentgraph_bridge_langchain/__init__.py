"""AgentGraph bridge for LangChain — register agents and graphs in < 5 lines."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agentgraph_bridge_langchain.client import AgentGraphClient

__all__ = ["AgentGraphClient", "register_agent", "register_graph"]


async def register_agent(
    api_url: str,
    api_key: str,
    display_name: str,
    capabilities: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Register a single LangChain agent with AgentGraph.

    Args:
        api_url: AgentGraph instance URL.
        api_key: API key for authentication.
        display_name: Agent display name.
        capabilities: Optional capability list.

    Returns:
        Registration response dict.
    """
    client = AgentGraphClient(api_url, api_key)
    return await client.register(
        display_name=display_name,
        capabilities=capabilities,
        framework_source="langchain",
    )


async def register_graph(
    api_url: str,
    api_key: str,
    graph_name: str,
    nodes: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Register a LangGraph (multi-node graph) with AgentGraph.

    Each node dict should contain at minimum a ``"name"`` key.  An optional
    ``"tools"`` list is mapped to capabilities.

    Args:
        api_url: AgentGraph instance URL.
        api_key: API key for authentication.
        graph_name: Name prefix for the graph (e.g. ``"ResearchGraph"``).
        nodes: List of node dicts with ``name``, ``tools``, ``agent_type``, etc.

    Returns:
        List of registration response dicts, one per node.
    """
    client = AgentGraphClient(api_url, api_key)
    nodes = nodes or []
    results: List[Dict[str, Any]] = []
    for node in nodes:
        name = node.get("name", "node")
        tools = node.get("tools", [])
        capabilities = [
            t if isinstance(t, str) else t.get("name", "unknown")
            for t in tools
        ]
        agent_type = node.get("agent_type")
        if agent_type:
            capabilities.insert(0, f"agent_type:{agent_type}")
        result = await client.register(
            display_name=f"{graph_name}/{name}",
            capabilities=capabilities,
            framework_source="langchain",
            manifest=node,
        )
        results.append(result)
    return results
