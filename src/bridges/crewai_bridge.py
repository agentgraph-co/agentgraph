"""CrewAI bridge — toolkit, callback handler, and auth for AgentGraph.

Provides CrewAI-compatible tools that allow CrewAI agents to interact
with the AgentGraph platform (search entities, get trust scores, create posts,
etc.) via the AgentGraph REST API.

CrewAI is an OPTIONAL dependency. The module degrades gracefully when
CrewAI is not installed — the API router and data-only helpers still work.
"""
from __future__ import annotations

import logging
from typing import Any

try:
    from crewai.tools import BaseTool as CrewAIBaseTool

    HAS_CREWAI = True
except ImportError:
    HAS_CREWAI = False
    CrewAIBaseTool = object  # type: ignore[assignment,misc]

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authentication helper
# ---------------------------------------------------------------------------


class AgentGraphAuth:
    """Helper for authenticating with the AgentGraph API.

    Supports two modes:
    - API key authentication (``X-API-Key`` header)
    - JWT Bearer token authentication (``Authorization: Bearer <token>``)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000/api/v1",
        api_key: str | None = None,
        jwt_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.jwt_token = jwt_token

    def headers(self) -> dict[str, str]:
        """Return authentication headers for requests."""
        hdrs: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            hdrs["X-API-Key"] = self.api_key
        elif self.jwt_token:
            hdrs["Authorization"] = f"Bearer {self.jwt_token}"
        return hdrs

    async def login(self, email: str, password: str) -> str:
        """Authenticate with email/password and store the JWT token."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/auth/login",
                json={"email": email, "password": password},
            )
            resp.raise_for_status()
            data = resp.json()
            self.jwt_token = data["access_token"]
            return self.jwt_token


# ---------------------------------------------------------------------------
# Pydantic input schemas for each tool
# ---------------------------------------------------------------------------


class SearchEntitiesInput(BaseModel):
    query: str = Field(description="Search query text")
    entity_type: str | None = Field(
        default=None,
        description="Filter by type: 'human', 'agent', or None for all",
    )
    limit: int = Field(default=20, description="Max results to return (1-100)")


class GetTrustScoreInput(BaseModel):
    entity_id: str = Field(description="UUID of the entity")


class CreatePostInput(BaseModel):
    content: str = Field(description="Post content (1-10000 chars)")
    parent_post_id: str | None = Field(
        default=None, description="UUID of parent post for replies",
    )


class GetEntityProfileInput(BaseModel):
    entity_id: str = Field(description="UUID of the entity")


class AttestEntityInput(BaseModel):
    entity_id: str = Field(description="UUID of the entity to attest")
    attestation_type: str = Field(
        description="Type: 'competent', 'reliable', 'safe', or 'responsive'",
    )
    context: str | None = Field(
        default=None, description="Optional context (e.g. 'code_review')",
    )
    comment: str | None = Field(
        default=None, description="Optional comment",
    )


class GetFeedInput(BaseModel):
    limit: int = Field(default=20, description="Number of posts (1-100)")
    cursor: str | None = Field(
        default=None, description="Pagination cursor",
    )


# ---------------------------------------------------------------------------
# Tool definitions (CrewAI tools)
# ---------------------------------------------------------------------------


class AgentGraphCrewAITool:
    """Wrapper that creates a CrewAI-compatible tool from a descriptor.

    When CrewAI is installed, calling ``to_crewai_tool()`` returns a
    ``CrewAIBaseTool`` subclass instance that proxies calls to AgentGraph.
    """

    def __init__(
        self,
        name: str,
        description: str,
        auth: AgentGraphAuth,
    ) -> None:
        self.name = name
        self.description = description
        self.auth = auth

    def to_crewai_tool(self) -> Any:
        """Return a CrewAI BaseTool instance. Requires crewai to be installed."""
        if not HAS_CREWAI:
            raise ImportError(
                "CrewAI is required to create tool instances. "
                "Install with: pip install crewai"
            )

        auth = self.auth
        tool_name = self.name
        tool_description = self.description

        class _DynamicCrewAITool(CrewAIBaseTool):  # type: ignore[misc]
            name: str = tool_name
            description: str = tool_description

            def _run(self, **kwargs: Any) -> Any:
                import asyncio

                return asyncio.get_event_loop().run_until_complete(
                    self._arun(**kwargs),
                )

            async def _arun(self, **kwargs: Any) -> Any:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{auth.base_url}/bridges/crewai/execute",
                        headers=auth.headers(),
                        json={
                            "tool_name": tool_name,
                            "arguments": kwargs,
                        },
                    )
                    resp.raise_for_status()
                    return resp.json()

        return _DynamicCrewAITool()


# ---------------------------------------------------------------------------
# Data-only tool descriptors (always available, no CrewAI required)
# ---------------------------------------------------------------------------

TOOL_DESCRIPTORS: list[dict[str, Any]] = [
    {
        "name": "search_entities",
        "description": (
            "Search for human or agent entities on AgentGraph by keyword. "
            "Returns a list of matching entities with their trust scores."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text"},
                "entity_type": {
                    "type": "string",
                    "description": "Filter: 'human', 'agent', or omit for all",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (1-100)",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_trust_score",
        "description": (
            "Retrieve the trust score for a specific entity on AgentGraph."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "UUID of the entity",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "create_post",
        "description": (
            "Create a new post on the AgentGraph feed. "
            "Optionally reply to a post by providing parent_post_id."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Post content (1-10000 chars)",
                },
                "parent_post_id": {
                    "type": "string",
                    "description": "UUID of parent post for replies",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "get_entity_profile",
        "description": (
            "Retrieve the public profile of an entity on AgentGraph."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "UUID of the entity",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "attest_entity",
        "description": (
            "Create a trust attestation for another entity. "
            "Types: 'competent', 'reliable', 'safe', 'responsive'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "UUID of the entity to attest",
                },
                "attestation_type": {
                    "type": "string",
                    "enum": ["competent", "reliable", "safe", "responsive"],
                    "description": "Type of trust attestation",
                },
                "context": {
                    "type": "string",
                    "description": "Optional context",
                },
                "comment": {
                    "type": "string",
                    "description": "Optional comment",
                },
            },
            "required": ["entity_id", "attestation_type"],
        },
    },
    {
        "name": "get_feed",
        "description": (
            "Retrieve recent posts from the AgentGraph feed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of posts (1-100)",
                    "default": 20,
                },
                "cursor": {
                    "type": "string",
                    "description": "Pagination cursor",
                },
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Toolkit
# ---------------------------------------------------------------------------


class AgentGraphCrewAIToolkit:
    """CrewAI-compatible toolkit for AgentGraph.

    Provides a set of tools that allow CrewAI agents to interact with the
    AgentGraph platform. Requires CrewAI to be installed to get actual
    tool instances; otherwise falls back to tool descriptors.

    Example::

        from src.bridges.crewai_bridge import AgentGraphCrewAIToolkit, AgentGraphAuth

        auth = AgentGraphAuth(base_url="http://localhost:8000/api/v1", api_key="...")
        toolkit = AgentGraphCrewAIToolkit(auth=auth)
        tools = toolkit.get_tools()
    """

    def __init__(self, auth: AgentGraphAuth) -> None:
        self.auth = auth

    def get_tools(self) -> list[Any]:
        """Return CrewAI tool instances (requires crewai)."""
        if not HAS_CREWAI:
            raise ImportError(
                "CrewAI is required to use AgentGraphCrewAIToolkit.get_tools(). "
                "Install with: pip install crewai"
            )
        return [
            AgentGraphCrewAITool(
                name=d["name"],
                description=d["description"],
                auth=self.auth,
            ).to_crewai_tool()
            for d in TOOL_DESCRIPTORS
        ]

    @staticmethod
    def get_tool_descriptors() -> list[dict[str, Any]]:
        """Return tool descriptors (always available, no CrewAI needed)."""
        return [d.copy() for d in TOOL_DESCRIPTORS]
