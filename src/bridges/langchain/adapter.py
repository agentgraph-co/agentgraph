"""LangChain adapter — translates LangChain agent configs into AgentGraph capabilities."""
from __future__ import annotations


def translate_langchain_manifest(manifest: dict) -> dict:
    """Translate a LangChain agent config into AgentGraph capabilities.

    Args:
        manifest: LangChain agent manifest dict with keys like
            name, description, tools, agent_type, model, version.

    Returns:
        Normalized dict with name, description, capabilities, version,
        and framework_metadata.
    """
    tools = manifest.get("tools", [])
    capabilities = [t.get("name", f"tool_{i}") for i, t in enumerate(tools)]

    return {
        "name": manifest.get("name", manifest.get("agent_name", "LangChain Agent")),
        "description": manifest.get("description", ""),
        "capabilities": capabilities,
        "version": manifest.get("version", "1.0.0"),
        "framework_metadata": {
            "agent_type": manifest.get("agent_type", "unknown"),
            "model": manifest.get("model", "unknown"),
            "tool_count": len(tools),
        },
    }
