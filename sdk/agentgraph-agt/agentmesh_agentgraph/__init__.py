"""AgentGraph trust provider for Microsoft Agent Governance Toolkit.

Usage with AGT::

    from agentmesh_agentgraph import AgentGraphTrustProvider

    provider = AgentGraphTrustProvider()
    engine = TrustEngine(external_providers=[provider])
    score = await engine.get_trust_score("agent-123")
"""
from __future__ import annotations

from agentmesh_agentgraph.provider import AgentGraphTrustProvider

__all__ = ["AgentGraphTrustProvider"]
