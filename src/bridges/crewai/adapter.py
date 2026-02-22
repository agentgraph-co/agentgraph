"""CrewAI adapter — translates CrewAI configs into AgentGraph capabilities."""
from __future__ import annotations


def translate_crewai_manifest(manifest: dict) -> dict:
    """Translate a CrewAI config into AgentGraph capabilities.

    Args:
        manifest: CrewAI manifest dict with keys like
            name, description, agents, tasks, process, version.

    Returns:
        Normalized dict with name, description, capabilities, version,
        and framework_metadata.
    """
    agents = manifest.get("agents", [])
    tasks = manifest.get("tasks", [])
    capabilities: list = []

    for agent in agents:
        role = agent.get("role", "unknown")
        capabilities.append(f"crew_role:{role}")
        for tool in agent.get("tools", []):
            if isinstance(tool, str):
                capabilities.append(tool)
            elif isinstance(tool, dict):
                capabilities.append(tool.get("name", "unknown"))

    return {
        "name": manifest.get("name", manifest.get("crew_name", "CrewAI Agent")),
        "description": manifest.get("description", ""),
        "capabilities": capabilities,
        "version": manifest.get("version", "1.0.0"),
        "framework_metadata": {
            "agent_count": len(agents),
            "task_count": len(tasks),
            "process_type": manifest.get("process", "sequential"),
        },
    }
