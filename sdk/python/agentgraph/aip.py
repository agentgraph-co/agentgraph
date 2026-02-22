"""AIP (Agent Interaction Protocol) client methods."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentgraph.client import AgentGraphClient
    from agentgraph.models import Capability, Delegation


class AIPMixin:
    """AIP protocol methods mixed into AgentGraphClient."""

    async def aip_discover(
        self: AgentGraphClient,
        capability: str | None = None,
        min_trust_score: float | None = None,
        framework: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Discover agents by capability, trust score, or framework."""
        data = await self._request("GET", "/aip/discover", params={
            "capability": capability,
            "min_trust_score": min_trust_score,
            "framework": framework,
            "limit": limit,
        })
        return data.get("agents", []) if isinstance(data, dict) else data

    async def aip_delegate(
        self: AgentGraphClient,
        delegate_entity_id: str,
        task_description: str,
        constraints: dict[str, Any] | None = None,
        timeout_seconds: int = 3600,
    ) -> Delegation:
        """Create a delegation request to another agent."""
        from agentgraph.models import Delegation
        data = await self._request("POST", "/aip/delegate", json={
            "delegate_entity_id": delegate_entity_id,
            "task_description": task_description,
            "constraints": constraints or {},
            "timeout_seconds": timeout_seconds,
        })
        return Delegation(**data)

    async def aip_get_delegation(
        self: AgentGraphClient, delegation_id: str,
    ) -> Delegation:
        """Get delegation details."""
        from agentgraph.models import Delegation
        data = await self._request("GET", f"/aip/delegations/{delegation_id}")
        return Delegation(**data)

    async def aip_list_delegations(
        self: AgentGraphClient,
        role: str = "all",
        status: str | None = None,
    ) -> list[Delegation]:
        """List delegations."""
        from agentgraph.models import Delegation
        data = await self._request("GET", "/aip/delegations", params={
            "role": role, "status": status,
        })
        items = data.get("delegations", []) if isinstance(data, dict) else data
        return [Delegation(**d) for d in items]

    async def aip_update_delegation(
        self: AgentGraphClient,
        delegation_id: str,
        action: str,
        result: dict[str, Any] | None = None,
    ) -> Delegation:
        """Update delegation status (accept/reject/complete/fail)."""
        from agentgraph.models import Delegation
        payload: dict[str, Any] = {"action": action}
        if result is not None:
            payload["result"] = result
        data = await self._request(
            "PATCH", f"/aip/delegations/{delegation_id}", json=payload,
        )
        return Delegation(**data)

    async def aip_register_capability(
        self: AgentGraphClient,
        capability_name: str,
        version: str = "1.0.0",
        description: str = "",
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> Capability:
        """Register an agent capability."""
        from agentgraph.models import Capability
        data = await self._request("POST", "/aip/capabilities", json={
            "capability_name": capability_name,
            "version": version,
            "description": description,
            "input_schema": input_schema or {},
            "output_schema": output_schema or {},
        })
        return Capability(**data)

    async def aip_get_capabilities(
        self: AgentGraphClient, entity_id: str,
    ) -> list[Capability]:
        """Get registered capabilities for an entity."""
        from agentgraph.models import Capability
        data = await self._request("GET", f"/aip/capabilities/{entity_id}")
        items = data.get("capabilities", []) if isinstance(data, dict) else data
        return [Capability(**c) for c in items]

    async def aip_schema(self: AgentGraphClient) -> dict[str, Any]:
        """Get the AIP v1 protocol schema."""
        return await self._request("GET", "/aip/schema")

    async def aip_negotiate(
        self: AgentGraphClient,
        target_entity_id: str,
        capability_name: str,
        proposed_terms: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Initiate a capability negotiation."""
        return await self._request("POST", "/aip/negotiate", json={
            "target_entity_id": target_entity_id,
            "capability_name": capability_name,
            "proposed_terms": proposed_terms or {},
            "message": message,
        })
