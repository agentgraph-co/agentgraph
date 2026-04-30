"""Core trust verification module for AgentGraph + LangChain integration."""
from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://agentgraph.co/api/v1"


class AgentGraphTrustCallback(BaseCallbackHandler):
    """LangChain callback handler that logs agent activity to AgentGraph.

    On chain start, logs the agent's DID. On chain end, optionally reports
    the execution result back to AgentGraph for trust scoring.
    """

    def __init__(
        self,
        did: str,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        report_results: bool = False,
    ) -> None:
        self.did = did
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.report_results = report_results

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        chain_name = serialized.get("name", serialized.get("id", ["unknown"])[-1])
        logger.info("AgentGraph: chain_start did=%s chain=%s", self.did, chain_name)

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        logger.info("AgentGraph: chain_end did=%s", self.did)
        if self.report_results:
            try:
                with httpx.Client(timeout=10) as client:
                    client.post(
                        f"{self.base_url}/activity",
                        headers=self._headers(),
                        json={
                            "did": self.did,
                            "action": "chain_execution",
                            "status": "completed",
                        },
                    )
            except httpx.HTTPError:
                logger.warning("AgentGraph: failed to report chain result")

    def on_chain_error(
        self,
        error: BaseException,
        **kwargs: Any,
    ) -> None:
        logger.warning("AgentGraph: chain_error did=%s error=%s", self.did, error)

    def on_llm_end(
        self,
        response: LLMResult,
        **kwargs: Any,
    ) -> None:
        pass


async def verify_trust(
    entity_id: str,
    min_score: float = 0.5,
    base_url: str = DEFAULT_BASE_URL,
    api_key: str | None = None,
) -> bool:
    """Check if an entity meets the minimum trust threshold.

    Args:
        entity_id: The entity ID or DID to verify.
        min_score: Minimum trust score required (0.0 to 1.0).
        base_url: AgentGraph API base URL.
        api_key: Optional API key for authenticated requests.

    Returns:
        True if the entity's trust score meets or exceeds min_score.
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{base_url}/trust/{entity_id}",
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        score = float(data.get("score", 0.0))
        return score >= min_score


def get_trust_badge_url(
    entity_id: str,
    style: str = "compact",
    base_url: str = DEFAULT_BASE_URL,
) -> str:
    """Generate a trust badge URL for embedding.

    Args:
        entity_id: The entity ID to generate a badge for.
        style: Badge style — "compact", "full", or "minimal".
        base_url: AgentGraph API base URL.

    Returns:
        URL string for the trust badge image.
    """
    return f"{base_url}/trust/{entity_id}/badge?style={style}"


async def run_security_scan(
    repo: str,
    token: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    api_key: str | None = None,
) -> dict:
    """Run a security scan on a repository via the AgentGraph API.

    Args:
        repo: Repository identifier (e.g. "owner/repo").
        token: Optional GitHub token for private repos.
        base_url: AgentGraph API base URL.
        api_key: Optional API key for authenticated requests.

    Returns:
        Dict with scan results including vulnerability counts and severity.
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict[str, Any] = {"repo": repo}
    if token:
        payload["token"] = token

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{base_url}/security/scan",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()
