"""LangChain tools for AgentGraph trust verification."""
from __future__ import annotations

import asyncio
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from agentgraph_langchain.trust import (
    DEFAULT_BASE_URL,
    run_security_scan,
    verify_trust,
)


class TrustVerifyInput(BaseModel):
    """Input schema for TrustVerifyTool."""

    entity_id: str = Field(description="The entity ID or DID to verify")
    min_score: float = Field(
        default=0.5,
        description="Minimum trust score threshold (0.0 to 1.0)",
    )


class TrustVerifyTool(BaseTool):
    """LangChain tool that verifies an agent's trust score on AgentGraph.

    Use this tool to check whether another agent or entity has a sufficient
    trust score before interacting with them.
    """

    name: str = "agentgraph_trust_verify"
    description: str = (
        "Verify an agent's trust score on AgentGraph. "
        "Returns whether the entity meets the minimum trust threshold. "
        "Input: entity_id (str), optional min_score (float, default 0.5)."
    )
    args_schema: Type[BaseModel] = TrustVerifyInput
    base_url: str = DEFAULT_BASE_URL
    api_key: Optional[str] = None

    def _run(self, entity_id: str, min_score: float = 0.5, **kwargs: Any) -> str:
        """Synchronous wrapper around async verify_trust."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run,
                    verify_trust(
                        entity_id,
                        min_score=min_score,
                        base_url=self.base_url,
                        api_key=self.api_key,
                    ),
                ).result()
        else:
            result = asyncio.run(
                verify_trust(
                    entity_id,
                    min_score=min_score,
                    base_url=self.base_url,
                    api_key=self.api_key,
                )
            )

        if result:
            return f"TRUSTED: Entity {entity_id} meets the minimum trust score of {min_score}."
        return f"UNTRUSTED: Entity {entity_id} does NOT meet the minimum trust score of {min_score}."

    async def _arun(self, entity_id: str, min_score: float = 0.5, **kwargs: Any) -> str:
        """Async trust verification."""
        result = await verify_trust(
            entity_id,
            min_score=min_score,
            base_url=self.base_url,
            api_key=self.api_key,
        )
        if result:
            return f"TRUSTED: Entity {entity_id} meets the minimum trust score of {min_score}."
        return f"UNTRUSTED: Entity {entity_id} does NOT meet the minimum trust score of {min_score}."


class SecurityScanInput(BaseModel):
    """Input schema for SecurityScanTool."""

    repo: str = Field(description="Repository to scan (e.g. 'owner/repo')")
    token: Optional[str] = Field(
        default=None,
        description="Optional GitHub token for private repos",
    )


class SecurityScanTool(BaseTool):
    """LangChain tool to run security scans on repositories via AgentGraph.

    Use this tool to check a repository for known vulnerabilities before
    trusting or installing its code.
    """

    name: str = "agentgraph_security_scan"
    description: str = (
        "Run a security scan on a GitHub repository via AgentGraph. "
        "Returns vulnerability counts and severity levels. "
        "Input: repo (str, e.g. 'owner/repo'), optional token (str)."
    )
    args_schema: Type[BaseModel] = SecurityScanInput
    base_url: str = DEFAULT_BASE_URL
    api_key: Optional[str] = None

    def _run(self, repo: str, token: Optional[str] = None, **kwargs: Any) -> str:
        """Synchronous wrapper around async run_security_scan."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run,
                    run_security_scan(
                        repo,
                        token=token,
                        base_url=self.base_url,
                        api_key=self.api_key,
                    ),
                ).result()
        else:
            result = asyncio.run(
                run_security_scan(
                    repo,
                    token=token,
                    base_url=self.base_url,
                    api_key=self.api_key,
                )
            )

        return str(result)

    async def _arun(self, repo: str, token: Optional[str] = None, **kwargs: Any) -> str:
        """Async security scan."""
        result = await run_security_scan(
            repo,
            token=token,
            base_url=self.base_url,
            api_key=self.api_key,
        )
        return str(result)
