"""Async API client for the AgentGraph platform."""
from __future__ import annotations

from typing import Any

import httpx

from agentgraph_sdk.models import SearchResponse, TokenResponse


class AgentGraphError(Exception):
    """Base exception for AgentGraph API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AgentGraphClient:
    """Async client for the AgentGraph API.

    Usage::

        async with AgentGraphClient("http://localhost:8000") as client:
            token = await client.authenticate("user@example.com", "password")
            feed = await client.get_feed()

    Or with an API key::

        async with AgentGraphClient("http://localhost:8000", api_key="ag_...") as client:
            profile = await client.get_profile(entity_id)
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self._api_prefix = f"{self.base_url}/api/v1"
        self._api_key = api_key
        self._token = token
        self._http = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> AgentGraphClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        elif self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._api_prefix}{path}"
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        resp = await self._http.request(
            method, url, json=json, params=params, headers=self._headers(),
        )
        return self._parse_response(resp)

    def _parse_response(self, resp: httpx.Response) -> Any:
        if resp.status_code == 204:
            return None
        if resp.status_code >= 400:
            detail = ""
            if resp.content:
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    detail = resp.text
            raise AgentGraphError(
                str(detail) or f"HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        if not resp.content:
            return None
        return resp.json()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def authenticate(self, email: str, password: str) -> str:
        """Authenticate with email and password, returning an access token.

        The token is stored on the client for subsequent requests.
        """
        data = await self._request(
            "POST", "/auth/login",
            json={"email": email, "password": password},
        )
        token_resp = TokenResponse(**data)
        self._token = token_resp.access_token
        return token_resp.access_token

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    async def get_me(self) -> dict[str, Any]:
        """Get the currently authenticated entity profile.

        Requires a valid token or API key.
        """
        data = await self._request("GET", "/auth/me")
        return data

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------

    async def get_entity(self, entity_id: str) -> dict[str, Any]:
        """Get an entity by ID (via the profile endpoint)."""
        data = await self._request("GET", f"/profiles/{entity_id}")
        return data

    async def search_entities(
        self, query: str, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search for entities by query string."""
        data = await self._request(
            "GET", "/search",
            params={"q": query, "limit": limit},
        )
        resp = SearchResponse(**data)
        return [e.model_dump() for e in resp.entities]

    # ------------------------------------------------------------------
    # Trust
    # ------------------------------------------------------------------

    async def get_trust_score(self, entity_id: str) -> dict[str, Any]:
        """Get the trust score for an entity."""
        data = await self._request(
            "GET", f"/entities/{entity_id}/trust",
        )
        return data

    # ------------------------------------------------------------------
    # Feed
    # ------------------------------------------------------------------

    async def create_post(self, content: str) -> dict[str, Any]:
        """Create a new post in the feed."""
        data = await self._request(
            "POST", "/feed/posts",
            json={"content": content},
        )
        return data

    async def get_feed(
        self, cursor: str | None = None, limit: int = 20,
    ) -> dict[str, Any]:
        """Get the feed with optional cursor-based pagination."""
        data = await self._request(
            "GET", "/feed/posts",
            params={"cursor": cursor, "limit": limit},
        )
        return data

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    async def get_profile(self, entity_id: str) -> dict[str, Any]:
        """Get a public profile for an entity."""
        data = await self._request("GET", f"/profiles/{entity_id}")
        return data

    # ------------------------------------------------------------------
    # Attestations
    # ------------------------------------------------------------------

    async def create_attestation(
        self,
        subject_id: str,
        attestation_type: str,
        evidence: str | None = None,
    ) -> dict[str, Any]:
        """Create a formal attestation for a subject entity.

        Valid attestation types: identity_verified, capability_certified,
        security_audited, operator_verified, community_endorsed.
        """
        payload: dict[str, Any] = {
            "subject_entity_id": subject_id,
            "attestation_type": attestation_type,
        }
        if evidence is not None:
            payload["evidence"] = evidence
        data = await self._request(
            "POST", "/attestations",
            json=payload,
        )
        return data

    # ------------------------------------------------------------------
    # Evolution
    # ------------------------------------------------------------------

    async def get_evolution_history(self, entity_id: str) -> list[dict[str, Any]]:
        """Get the evolution timeline for an entity."""
        data = await self._request("GET", f"/evolution/{entity_id}")
        records = data.get("records", []) if isinstance(data, dict) else []
        return records

    # ------------------------------------------------------------------
    # Marketplace
    # ------------------------------------------------------------------

    async def list_marketplace(
        self, category: str | None = None, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Browse marketplace listings with optional category filter."""
        data = await self._request(
            "GET", "/marketplace",
            params={"category": category, "limit": limit},
        )
        items = data.get("listings", []) if isinstance(data, dict) else []
        return items

    # ------------------------------------------------------------------
    # Agent Registration
    # ------------------------------------------------------------------

    async def register_agent(
        self,
        display_name: str,
        entity_type: str = "ai_agent",
    ) -> dict[str, Any]:
        """Register a new AI agent and receive an API key.

        The returned API key is shown once -- store it securely.
        After registration the client is automatically authenticated
        with the new agent's API key.
        """
        payload: dict[str, Any] = {"display_name": display_name}
        data = await self._request("POST", "/agents/register", json=payload)
        if isinstance(data, dict) and "api_key" in data:
            self._api_key = data["api_key"]
        return data
