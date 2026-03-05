"""AgentGraph bridge for AutoGen — register agents and groups in < 5 lines."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agentgraph_bridge_autogen.client import AgentGraphClient

__all__ = ["AgentGraphClient", "register_agent", "register_group"]


async def register_agent(
    api_url: str,
    api_key: str,
    display_name: str,
    capabilities: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Register a single AutoGen agent with AgentGraph.

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
        framework_source="autogen",
    )


async def register_group(
    api_url: str,
    api_key: str,
    group_name: str,
    agents: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Register an AutoGen group chat (multiple agents) with AgentGraph.

    Each agent dict should contain at minimum a ``"name"`` or ``"type"`` key.
    Functions listed under ``"functions"`` are mapped to capabilities.

    Args:
        api_url: AgentGraph instance URL.
        api_key: API key for authentication.
        group_name: Name prefix for the group (e.g. ``"CodeReviewGroup"``).
        agents: List of agent dicts with ``name``/``type``, ``functions``, etc.

    Returns:
        List of registration response dicts, one per agent.
    """
    client = AgentGraphClient(api_url, api_key)
    agents = agents or []
    results: List[Dict[str, Any]] = []
    for agent in agents:
        agent_type = agent.get("type", agent.get("agent_type", "assistant"))
        name = agent.get("name", agent_type)
        functions = agent.get("functions", [])
        capabilities = [
            f if isinstance(f, str) else f.get("name", "unknown")
            for f in functions
        ]
        capabilities.insert(0, f"autogen_agent:{agent_type}")
        result = await client.register(
            display_name=f"{group_name}/{name}",
            capabilities=capabilities,
            framework_source="autogen",
            manifest=agent,
        )
        results.append(result)
    return results
