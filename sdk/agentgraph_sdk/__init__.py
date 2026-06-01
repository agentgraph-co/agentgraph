"""AgentGraph SDK — Python client and CLI for the AgentGraph platform."""
from __future__ import annotations

from agentgraph_sdk.cli import cli as agentgraph_cli
from agentgraph_sdk.client import AgentGraphClient
from agentgraph_sdk.verify import VerificationResult, is_fresh, verify_envelope

AgentGraphCLI = agentgraph_cli

__all__ = [
    "AgentGraphClient",
    "AgentGraphCLI",
    "verify_envelope",
    "VerificationResult",
    "is_fresh",
]
__version__ = "0.2.0"
