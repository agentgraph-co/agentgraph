"""Semantic Kernel adapter — translates SK configs into AgentGraph capabilities."""
from __future__ import annotations


def translate_sk_manifest(manifest: dict) -> dict:
    """Translate a Semantic Kernel plugin config into AgentGraph capabilities.

    Args:
        manifest: SK manifest dict with keys like
            name, description, plugins, planner_config, kernel_config, version.

    Returns:
        Normalized dict with name, description, capabilities, version,
        and framework_metadata.
    """
    plugins = manifest.get("plugins", [])
    capabilities: list = []

    for plugin in plugins:
        plugin_name = plugin.get("name", "unknown")
        capabilities.append(f"sk_plugin:{plugin_name}")
        for func in plugin.get("functions", []):
            if isinstance(func, str):
                capabilities.append(func)
            elif isinstance(func, dict):
                capabilities.append(func.get("name", "unknown"))

    planner_config = manifest.get("planner_config", {})
    kernel_config = manifest.get("kernel_config", {})

    return {
        "name": manifest.get("name", "Semantic Kernel Agent"),
        "description": manifest.get("description", ""),
        "capabilities": capabilities,
        "version": manifest.get("version", "1.0.0"),
        "framework_metadata": {
            "plugin_count": len(plugins),
            "has_planner": bool(planner_config),
            "planner_type": planner_config.get("type", "none"),
            "kernel_services": list(kernel_config.get("services", {}).keys())
            if isinstance(kernel_config.get("services"), dict)
            else [],
        },
    }
