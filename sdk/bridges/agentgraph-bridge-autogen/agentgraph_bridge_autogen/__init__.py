"""AgentGraph bridge for Microsoft AutoGen — trust-gated tools and agent registration."""
from __future__ import annotations

from agentgraph_bridge_autogen.guard import (
    TrustGuard,
    TrustResult,
    check_trust,
    trust_gated_function,
    trust_gated_tool,
)

__all__ = [
    "TrustGuard",
    "TrustResult",
    "check_trust",
    "trust_gated_function",
    "trust_gated_tool",
]
