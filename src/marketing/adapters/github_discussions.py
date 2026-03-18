"""GitHub Discussions adapter — engage in relevant open-source repos."""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from src.marketing.adapters.base import (
    AbstractPlatformAdapter,
    EngagementMetrics,
    ExternalPostResult,
    Mention,
)

logger = logging.getLogger(__name__)

_API_URL = "https://api.github.com/graphql"
_TIMEOUT = 15.0

# Target repos for engagement
TARGET_REPOS = [
    "langchain-ai/langchain",
    "microsoft/autogen",
    "modelcontextprotocol/servers",
]


class GitHubDiscussionsAdapter(AbstractPlatformAdapter):
    platform_name = "github_discussions"
    max_content_length = 10000
    supports_replies = True
    supports_monitoring = True
    rate_limit_posts_per_hour = 5

    def _token(self) -> str | None:
        """Get GitHub token — falls back to main config."""
        from src.config import settings
        return settings.github_token

    async def is_configured(self) -> bool:
        return bool(self._token())

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json",
        }

    async def post(self, content: str, metadata: dict | None = None) -> ExternalPostResult:
        """Create a discussion comment (not a new discussion — too intrusive)."""
        meta = metadata or {}
        discussion_id = meta.get("discussion_id")
        if not discussion_id:
            return ExternalPostResult(
                success=False, error="No discussion_id — use reply() or provide discussion_id",
            )
        return await self.reply(discussion_id, content, metadata)

    async def reply(
        self, parent_id: str, content: str, metadata: dict | None = None,
    ) -> ExternalPostResult:
        mutation = """
        mutation AddComment($input: AddDiscussionCommentInput!) {
            addDiscussionComment(input: $input) {
                comment { id url }
            }
        }
        """
        variables = {
            "input": {
                "discussionId": parent_id,
                "body": content,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    _API_URL,
                    json={"query": mutation, "variables": variables},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()

            errors = data.get("errors")
            if errors:
                return ExternalPostResult(
                    success=False, error=str(errors[0].get("message", "")),
                )

            comment = data.get("data", {}).get("addDiscussionComment", {}).get("comment", {})
            return ExternalPostResult(
                success=True,
                external_id=comment.get("id", ""),
                url=comment.get("url"),
            )
        except Exception as exc:
            logger.exception("GitHub Discussions reply failed")
            return ExternalPostResult(success=False, error=str(exc))

    async def fetch_mentions(self, since: datetime | None = None) -> list[Mention]:
        """Search for agentgraph mentions in target repo discussions."""
        mentions: list[Mention] = []

        query = """
        query SearchDiscussions($query: String!) {
            search(query: $query, type: DISCUSSION, first: 10) {
                nodes {
                    ... on Discussion { id title body url author { login } }
                }
            }
        }
        """

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    _API_URL,
                    json={
                        "query": query,
                        "variables": {"query": "agentgraph OR agent trust identity"},
                    },
                    headers=self._headers(),
                )
                resp.raise_for_status()
                nodes = resp.json().get("data", {}).get("search", {}).get("nodes", [])

            for node in nodes:
                mentions.append(Mention(
                    platform="github_discussions",
                    external_id=node.get("id", ""),
                    author=node.get("author", {}).get("login", ""),
                    content=node.get("body", node.get("title", "")),
                    url=node.get("url"),
                ))
        except Exception:
            logger.debug("GitHub Discussions search failed")

        return mentions

    async def fetch_metrics(self, post_external_id: str) -> EngagementMetrics:
        return EngagementMetrics()

    async def health_check(self) -> bool:
        if not await self.is_configured():
            return False
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    _API_URL,
                    json={"query": "{ viewer { login } }"},
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False
