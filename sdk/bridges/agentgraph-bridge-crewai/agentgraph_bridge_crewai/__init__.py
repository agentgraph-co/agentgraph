"""AgentGraph bridge for CrewAI — register crews and agents in < 5 lines."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agentgraph_bridge_crewai.client import AgentGraphClient

__all__ = ["AgentGraphClient", "register_crew", "register_agent"]


async def register_agent(
    api_url: str,
    api_key: str,
    display_name: str,
    capabilities: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Register a single CrewAI agent with AgentGraph.

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
        framework_source="crewai",
    )


async def register_crew(
    api_url: str,
    api_key: str,
    crew_name: str,
    agents: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Register an entire CrewAI crew (multiple agents) with AgentGraph.

    Each agent dict should contain at minimum a ``"role"`` key.  The role
    is used as the display name, and any ``"tools"`` list is mapped to
    capabilities.

    Args:
        api_url: AgentGraph instance URL.
        api_key: API key for authentication.
        crew_name: Name prefix for the crew (e.g. ``"ResearchCrew"``).
        agents: List of agent dicts with ``role``, ``tools``, etc.

    Returns:
        List of registration response dicts, one per agent.
    """
    client = AgentGraphClient(api_url, api_key)
    agents = agents or []
    results: List[Dict[str, Any]] = []
    for agent in agents:
        role = agent.get("role", "agent")
        tools = agent.get("tools", [])
        capabilities = [
            t if isinstance(t, str) else t.get("name", "unknown")
            for t in tools
        ]
        capabilities.insert(0, f"crew_role:{role}")
        result = await client.register(
            display_name=f"{crew_name}/{role}",
            capabilities=capabilities,
            framework_source="crewai",
            manifest=agent,
        )
        results.append(result)
    return results
