"""Pydantic AI adapter — translates Pydantic AI agent configs into AgentGraph capabilities."""
from __future__ import annotations


def translate_pydantic_ai_manifest(manifest: dict) -> dict:
    """Translate a Pydantic AI agent config into AgentGraph capabilities.

    Args:
        manifest: Pydantic AI manifest dict with keys like
            name, description, tools, result_type, model, deps_type, version.

    Returns:
        Normalized dict with name, description, capabilities, version,
        and framework_metadata.
    """
    tools = manifest.get("tools", [])
    result_type = manifest.get("result_type", None)
    deps_type = manifest.get("deps_type", None)
    capabilities: list = []

    # Map Pydantic AI core capabilities
    if result_type:
        capabilities.append("structured_output")
        capabilities.append("result_validation")
    if tools:
        capabilities.append("tool_use")
    if deps_type:
        capabilities.append("type_safe_agents")

    # Extract individual tool names
    for tool in tools:
        if isinstance(tool, str):
            capabilities.append(tool)
        elif isinstance(tool, dict):
            capabilities.append(tool.get("name", "unknown"))

    return {
        "name": manifest.get("name", manifest.get("agent_name", "Pydantic AI Agent")),
        "description": manifest.get("description", ""),
        "capabilities": capabilities,
        "version": manifest.get("version", "1.0.0"),
        "framework_metadata": {
            "model": manifest.get("model", "unknown"),
            "result_type": result_type,
            "deps_type": deps_type,
            "tool_count": len(tools),
            "has_system_prompt": bool(manifest.get("system_prompt")),
            "retries": manifest.get("retries", 1),
        },
    }
