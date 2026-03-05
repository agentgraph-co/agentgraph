"""AgentGraph SDK — Python client and CLI for the AgentGraph platform."""
from __future__ import annotations

from agentgraph_sdk.cli import cli as agentgraph_cli
from agentgraph_sdk.client import AgentGraphClient

AgentGraphCLI = agentgraph_cli

__all__ = ["AgentGraphClient", "AgentGraphCLI"]
__version__ = "0.1.0"
