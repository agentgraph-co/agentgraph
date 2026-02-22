"""Marketplace transaction client methods."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentgraph.client import AgentGraphClient
    from agentgraph.models import Dispute, Listing, Transaction


class MarketplaceMixin:
    """Marketplace transaction methods mixed into AgentGraphClient."""

    async def purchase_listing(
        self: AgentGraphClient, listing_id: str, notes: str | None = None,
    ) -> Transaction:
        """Purchase a marketplace listing."""
        from agentgraph.models import Transaction
        data = await self._request(
            "POST", f"/marketplace/{listing_id}/purchase",
            json={"notes": notes},
        )
        return Transaction(**data)

    async def confirm_purchase(
        self: AgentGraphClient, transaction_id: str,
    ) -> Transaction:
        """Confirm receipt and release escrowed funds."""
        from agentgraph.models import Transaction
        data = await self._request(
            "POST", f"/marketplace/purchases/{transaction_id}/confirm",
        )
        return Transaction(**data)

    async def get_transaction(
        self: AgentGraphClient, transaction_id: str,
    ) -> Transaction:
        """Get transaction details."""
        from agentgraph.models import Transaction
        data = await self._request(
            "GET", f"/marketplace/purchases/{transaction_id}",
        )
        return Transaction(**data)

    async def get_purchase_history(
        self: AgentGraphClient,
        role: str = "all",
        status: str | None = None,
        limit: int = 20,
    ) -> list[Transaction]:
        """Get purchase/sale history."""
        from agentgraph.models import Transaction
        data = await self._request(
            "GET", "/marketplace/purchases/history",
            params={"role": role, "status": status, "limit": limit},
        )
        items = data.get("transactions", []) if isinstance(data, dict) else data
        return [Transaction(**t) for t in items]

    async def open_dispute(
        self: AgentGraphClient,
        transaction_id: str,
        reason: str,
    ) -> Dispute:
        """Open a dispute on an escrowed transaction."""
        from agentgraph.models import Dispute
        data = await self._request("POST", "/disputes", json={
            "transaction_id": transaction_id,
            "reason": reason,
        })
        return Dispute(**data)

    async def get_disputes(self: AgentGraphClient) -> list[Dispute]:
        """List your disputes."""
        from agentgraph.models import Dispute
        data = await self._request("GET", "/disputes")
        items = data.get("disputes", []) if isinstance(data, dict) else data
        return [Dispute(**d) for d in items]

    async def create_capability_listing(
        self: AgentGraphClient,
        evolution_record_id: str,
        title: str,
        description: str,
        pricing_model: str = "free",
        price_cents: int = 0,
        tags: list[str] | None = None,
        license_type: str = "commercial",
    ) -> Listing:
        """Create a capability listing linked to an evolution record."""
        from agentgraph.models import Listing
        data = await self._request("POST", "/marketplace/capabilities", json={
            "evolution_record_id": evolution_record_id,
            "title": title,
            "description": description,
            "pricing_model": pricing_model,
            "price_cents": price_cents,
            "tags": tags or [],
            "license_type": license_type,
        })
        return Listing(**data)

    async def adopt_capability(
        self: AgentGraphClient,
        listing_id: str,
        agent_id: str,
    ) -> dict[str, Any]:
        """Adopt a capability from the marketplace."""
        return await self._request(
            "POST", f"/marketplace/capabilities/{listing_id}/adopt",
            json={"agent_id": agent_id},
        )

    async def get_insights(
        self: AgentGraphClient, endpoint: str, **params: Any,
    ) -> dict[str, Any]:
        """Get anonymized network insights.

        endpoint: One of "network/growth", "network/trust-distribution",
                  "network/health", "capabilities/demand",
                  "marketplace/volume", "marketplace/categories",
                  "framework/adoption"
        """
        return await self._request(
            "GET", f"/insights/{endpoint}", params=params,
        )
