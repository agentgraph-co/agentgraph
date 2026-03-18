"""Abstract base class for platform adapters."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ExternalPostResult:
    """Result from posting to an external platform."""

    success: bool
    external_id: str | None = None
    url: str | None = None
    error: str | None = None
    rate_limited: bool = False


@dataclass
class Mention:
    """A mention or keyword match found on a platform."""

    platform: str
    external_id: str
    author: str
    content: str
    url: str | None = None
    created_at: datetime | None = None
    keywords_matched: list[str] = field(default_factory=list)


@dataclass
class EngagementMetrics:
    """Engagement data for a posted item."""

    likes: int = 0
    comments: int = 0
    shares: int = 0
    impressions: int = 0
    clicks: int = 0
    extra: dict | None = None


class AbstractPlatformAdapter(ABC):
    """Base class all platform adapters must implement.

    Adapters should gracefully skip (return failure, not raise) when
    API credentials are missing.  The orchestrator checks
    ``is_configured`` before calling any methods.
    """

    platform_name: str = ""
    max_content_length: int = 5000
    supports_replies: bool = True
    supports_monitoring: bool = True
    requires_human_approval: bool = False
    rate_limit_posts_per_hour: int = 10
    rate_limit_replies_per_hour: int = 20

    @abstractmethod
    async def is_configured(self) -> bool:
        """Return True if all required credentials are present."""
        ...

    @abstractmethod
    async def post(self, content: str, metadata: dict | None = None) -> ExternalPostResult:
        """Publish content to the platform."""
        ...

    @abstractmethod
    async def reply(
        self, parent_id: str, content: str, metadata: dict | None = None,
    ) -> ExternalPostResult:
        """Reply to an existing post on the platform."""
        ...

    @abstractmethod
    async def fetch_mentions(self, since: datetime | None = None) -> list[Mention]:
        """Fetch recent mentions or keyword matches."""
        ...

    @abstractmethod
    async def fetch_metrics(self, post_external_id: str) -> EngagementMetrics:
        """Fetch engagement metrics for a specific post."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify the adapter can reach the platform API."""
        ...

    async def search_keywords(
        self, keywords: list[str], since: datetime | None = None,
    ) -> list[Mention]:
        """Search platform for keyword matches.  Optional — defaults to empty."""
        return []

    def truncate(self, content: str) -> str:
        """Truncate content to platform's max length."""
        if len(content) <= self.max_content_length:
            return content
        # Leave room for ellipsis
        return content[: self.max_content_length - 1] + "\u2026"
