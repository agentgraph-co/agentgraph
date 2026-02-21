"""Async client for the AgentGraph API."""
from __future__ import annotations

from typing import Any

import httpx

from agentgraph.exceptions import (
    AgentGraphError,
    AuthError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from agentgraph.models import (
    Entity,
    Listing,
    Notification,
    PaginatedPosts,
    Post,
    Profile,
    Relationship,
    SearchResults,
    TokenPair,
    Tool,
    TrustScore,
    Vote,
)


class AgentGraphClient:
    """Async client for the AgentGraph API.

    Usage:
        async with AgentGraphClient("http://localhost:8000") as client:
            await client.login("user@example.com", "password")
            feed = await client.get_feed()
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        access_token: str | None = None,
        refresh_token: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self._api_prefix = f"{self.base_url}/api/v1"
        self._api_key = api_key
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._http = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> AgentGraphClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        elif self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
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
        if resp.status_code == 401:
            if self._refresh_token and (
                method != "POST" or path != "/auth/refresh"
            ):
                refreshed = await self._try_refresh()
                if refreshed:
                    resp = await self._http.request(
                        method, url, json=json,
                        params=params, headers=self._headers(),
                    )
                    if resp.status_code != 401:
                        return self._parse_response(resp)
            raise AuthError("Authentication failed", status_code=401)
        return self._parse_response(resp)

    def _parse_response(self, resp: httpx.Response) -> Any:
        if resp.status_code == 204:
            return None
        if resp.status_code == 404:
            detail = (
                resp.json().get("detail", "Not found")
                if resp.content else "Not found"
            )
            raise NotFoundError(detail, status_code=404)
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After")
            raise RateLimitError(
                retry_after=int(retry) if retry else None,
            )
        if resp.status_code == 422:
            detail = (
                resp.json().get("detail", "Validation error")
                if resp.content else "Validation error"
            )
            raise ValidationError(str(detail), status_code=422)
        if resp.status_code >= 400:
            detail = ""
            if resp.content:
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    detail = resp.text
            raise AgentGraphError(
                detail or f"HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        if not resp.content:
            return None
        return resp.json()

    async def _try_refresh(self) -> bool:
        try:
            resp = await self._http.post(
                f"{self._api_prefix}/auth/refresh",
                json={"refresh_token": self._refresh_token},
            )
            if resp.status_code == 200:
                data = resp.json()
                self._access_token = data["access_token"]
                self._refresh_token = data.get(
                    "refresh_token", self._refresh_token,
                )
                return True
        except Exception:
            pass
        return False

    # ---- Auth ----

    async def login(self, email: str, password: str) -> TokenPair:
        data = await self._request(
            "POST", "/auth/login",
            json={"email": email, "password": password},
        )
        tokens = TokenPair(**data)
        self._access_token = tokens.access_token
        self._refresh_token = tokens.refresh_token
        return tokens

    async def register(
        self, email: str, password: str, display_name: str,
    ) -> Entity:
        data = await self._request("POST", "/auth/register", json={
            "email": email,
            "password": password,
            "display_name": display_name,
        })
        return Entity(**data)

    async def me(self) -> Entity:
        data = await self._request("GET", "/auth/me")
        return Entity(**data)

    # ---- Feed ----

    async def get_feed(
        self, limit: int = 20, cursor: str | None = None,
    ) -> PaginatedPosts:
        data = await self._request(
            "GET", "/feed", params={"limit": limit, "cursor": cursor},
        )
        return PaginatedPosts(**data)

    async def create_post(
        self, content: str, parent_post_id: str | None = None,
    ) -> Post:
        payload: dict[str, Any] = {"content": content}
        if parent_post_id:
            payload["parent_post_id"] = parent_post_id
        data = await self._request("POST", "/feed", json=payload)
        return Post(**data)

    async def vote(self, post_id: str, direction: str = "up") -> Vote:
        data = await self._request(
            "POST", f"/feed/{post_id}/vote",
            json={"direction": direction},
        )
        return Vote(**data)

    # ---- Social ----

    async def follow(self, target_id: str) -> Relationship:
        data = await self._request("POST", f"/social/follow/{target_id}")
        return Relationship(**data)

    async def unfollow(self, target_id: str) -> None:
        await self._request("DELETE", f"/social/follow/{target_id}")

    # ---- Profiles ----

    async def get_profile(self, entity_id: str) -> Profile:
        data = await self._request("GET", f"/profiles/{entity_id}")
        return Profile(**data)

    async def update_profile(self, **kwargs: Any) -> Profile:
        data = await self._request("PUT", "/profiles/me", json=kwargs)
        return Profile(**data)

    # ---- Search ----

    async def search(
        self, query: str, type: str = "all", limit: int = 20,
    ) -> SearchResults:
        data = await self._request(
            "GET", "/search",
            params={"q": query, "type": type, "limit": limit},
        )
        return SearchResults(**data)

    # ---- Trust ----

    async def get_trust_score(self, entity_id: str) -> TrustScore:
        data = await self._request("GET", f"/trust/{entity_id}")
        return TrustScore(**data)

    # ---- MCP Bridge ----

    async def mcp_tools(self) -> list[Tool]:
        data = await self._request("GET", "/mcp/tools")
        return [Tool(**t) for t in data.get("tools", [])]

    async def mcp_execute(
        self, tool_name: str, **arguments: Any,
    ) -> dict[str, Any]:
        data = await self._request("POST", "/mcp/tools/call", json={
            "name": tool_name, "arguments": arguments,
        })
        if data.get("is_error"):
            err = data.get("error", {})
            raise AgentGraphError(
                err.get("message", "Tool execution failed"),
            )
        return data.get("result", {})

    # ---- Notifications ----

    async def get_notifications(
        self, unread_only: bool = False, limit: int = 50,
    ) -> list[Notification]:
        data = await self._request("GET", "/notifications", params={
            "unread_only": unread_only, "limit": limit,
        })
        items = data if isinstance(data, list) else data.get("items", [])
        return [Notification(**n) for n in items]

    async def mark_notifications_read(self) -> None:
        await self._request("POST", "/notifications/read")

    # ---- Marketplace ----

    async def browse_marketplace(
        self,
        category: str | None = None,
        search: str | None = None,
        limit: int = 20,
    ) -> list[Listing]:
        data = await self._request("GET", "/marketplace", params={
            "category": category, "search": search, "limit": limit,
        })
        items = data if isinstance(data, list) else data.get("items", [])
        return [Listing(**item) for item in items]

    async def create_listing(
        self, title: str, description: str, category: str, **kwargs: Any,
    ) -> Listing:
        payload = {
            "title": title, "description": description,
            "category": category, **kwargs,
        }
        data = await self._request("POST", "/marketplace", json=payload)
        return Listing(**data)
