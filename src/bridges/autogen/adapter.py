"""AutoGen adapter — translates AutoGen configs into AgentGraph capabilities."""
from __future__ import annotations


def translate_autogen_manifest(manifest: dict) -> dict:
    """Translate an AutoGen agent config into AgentGraph capabilities.

    Args:
        manifest: AutoGen manifest dict with keys like
            name, description, agents, oai_config, code_execution_config, version.

    Returns:
        Normalized dict with name, description, capabilities, version,
        and framework_metadata.
    """
    agents = manifest.get("agents", [])
    capabilities: list = []

    for agent in agents:
        agent_type = agent.get("type", agent.get("agent_type", "unknown"))
        capabilities.append(f"autogen_agent:{agent_type}")
        # Extract function names from agent configs
        for func in agent.get("functions", []):
            if isinstance(func, str):
                capabilities.append(func)
            elif isinstance(func, dict):
                capabilities.append(func.get("name", "unknown"))

    oai_config = manifest.get("oai_config", {})
    code_exec = manifest.get("code_execution_config", {})

    return {
        "name": manifest.get("name", "AutoGen Agent"),
        "description": manifest.get("description", ""),
        "capabilities": capabilities,
        "version": manifest.get("version", "1.0.0"),
        "framework_metadata": {
            "agent_count": len(agents),
            "has_oai_config": bool(oai_config),
            "code_execution_enabled": bool(code_exec),
            "model": oai_config.get("model", "unknown"),
        },
    }
