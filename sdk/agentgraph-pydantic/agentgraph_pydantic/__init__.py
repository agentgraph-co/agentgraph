"""AgentGraph trust verification for PydanticAI agents.

Usage::

    from agentgraph_pydantic import TrustGuard, check_trust

    # Quick check before tool execution
    result = await check_trust("crewAIInc/crewAI")
    if result.allowed:
        # proceed with tool call
        ...

    # As PydanticAI middleware
    guard = TrustGuard(min_tier="standard")
    result = await guard.check("owner/repo")
"""
from __future__ import annotations

from agentgraph_pydantic.guard import TrustGuard, check_trust

__all__ = ["TrustGuard", "check_trust"]
