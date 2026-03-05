"""Unified bridge health check and discovery.

Provides discovery of all supported framework bridges with their capabilities
and import schemas, plus health status checks for each bridge module.
"""
from __future__ import annotations

from typing import Any

# Framework definitions with capabilities and import schemas
_FRAMEWORK_DEFINITIONS: list[dict[str, Any]] = [
    {
        "framework": "mcp",
        "capabilities": [
            "tool_discovery",
            "tool_execution",
            "protocol_bridge",
        ],
        "import_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "tools": {"type": "array"},
            },
        },
        "module": "src.bridges",
        "version": "1.0.0",
    },
    {
        "framework": "openclaw",
        "capabilities": [
            "agent_import",
            "security_scan",
            "skill_translation",
            "trust_scoring",
        ],
        "import_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 100},
                "description": {"type": "string", "maxLength": 5000},
                "capabilities": {"type": "array", "items": {"type": "string"}},
                "version": {"type": "string"},
                "skills": {"type": "array"},
            },
            "required": ["name"],
        },
        "module": "src.bridges.openclaw",
        "version": "1.0.0",
    },
    {
        "framework": "langchain",
        "capabilities": [
            "agent_import",
            "security_scan",
            "tool_translation",
            "trust_scoring",
        ],
        "import_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 100},
                "description": {"type": "string", "maxLength": 5000},
                "tools": {"type": "array"},
                "agent_type": {"type": "string"},
                "model": {"type": "string"},
                "version": {"type": "string"},
                "code": {"type": "string"},
            },
        },
        "module": "src.bridges.langchain",
        "version": "1.0.0",
    },
    {
        "framework": "crewai",
        "capabilities": [
            "agent_import",
            "security_scan",
            "crew_translation",
            "trust_scoring",
        ],
        "import_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 100},
                "description": {"type": "string", "maxLength": 5000},
                "agents": {"type": "array"},
                "tasks": {"type": "array"},
                "process": {"type": "string"},
                "version": {"type": "string"},
                "code": {"type": "string"},
            },
        },
        "module": "src.bridges.crewai",
        "version": "1.0.0",
    },
    {
        "framework": "autogen",
        "capabilities": [
            "agent_import",
            "security_scan",
            "conversation_translation",
            "trust_scoring",
        ],
        "import_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 100},
                "description": {"type": "string", "maxLength": 5000},
                "agents": {"type": "array"},
                "oai_config": {"type": "object"},
                "code_execution_config": {"type": "object"},
                "version": {"type": "string"},
                "code": {"type": "string"},
            },
        },
        "module": "src.bridges.autogen",
        "version": "1.0.0",
    },
    {
        "framework": "semantic_kernel",
        "capabilities": [
            "agent_import",
            "security_scan",
            "plugin_translation",
            "trust_scoring",
        ],
        "import_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 100},
                "description": {"type": "string", "maxLength": 5000},
                "plugins": {"type": "array"},
                "planner_config": {"type": "object"},
                "kernel_config": {"type": "object"},
                "version": {"type": "string"},
                "code": {"type": "string"},
            },
        },
        "module": "src.bridges.semantic_kernel",
        "version": "1.0.0",
    },
    {
        "framework": "pydantic_ai",
        "capabilities": [
            "agent_import",
            "security_scan",
            "structured_output",
            "tool_use",
            "type_safe_agents",
            "result_validation",
            "trust_scoring",
        ],
        "import_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 100},
                "description": {"type": "string", "maxLength": 5000},
                "tools": {"type": "array"},
                "result_type": {"type": "string"},
                "deps_type": {"type": "string"},
                "model": {"type": "string"},
                "system_prompt": {"type": "string"},
                "retries": {"type": "integer"},
                "version": {"type": "string"},
                "code": {"type": "string"},
            },
        },
        "module": "src.bridges.pydantic_ai",
        "version": "1.0.0",
    },
]


def _check_module_loaded(module_path: str) -> bool:
    """Check if a bridge module can be imported."""
    import importlib

    try:
        importlib.import_module(module_path)
        return True
    except ImportError:
        return False


def get_bridge_discovery() -> list[dict[str, Any]]:
    """Return discovery information for all supported framework bridges.

    Returns:
        List of framework capability dicts with:
        - framework: framework name
        - capabilities: list of capability strings
        - import_schema: JSON Schema for the import manifest
        - status: "available" or "unavailable"
    """
    frameworks: list[dict[str, Any]] = []
    for defn in _FRAMEWORK_DEFINITIONS:
        module_loaded = _check_module_loaded(defn["module"])
        frameworks.append({
            "framework": defn["framework"],
            "capabilities": defn["capabilities"],
            "import_schema": defn["import_schema"],
            "status": "available" if module_loaded else "unavailable",
        })
    return frameworks


def check_bridge_health() -> list[dict[str, Any]]:
    """Check health status of all bridge modules.

    Returns:
        List of health status dicts with:
        - framework: framework name
        - status: "healthy" or "unhealthy"
        - module_loaded: bool
        - version: version string
    """
    results: list[dict[str, Any]] = []
    for defn in _FRAMEWORK_DEFINITIONS:
        module_loaded = _check_module_loaded(defn["module"])
        results.append({
            "framework": defn["framework"],
            "status": "healthy" if module_loaded else "unhealthy",
            "module_loaded": module_loaded,
            "version": defn["version"],
        })
    return results
