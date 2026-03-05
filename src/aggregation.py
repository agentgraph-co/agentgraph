from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, Post

logger = logging.getLogger(__name__)


# Supported source types
SOURCE_TYPES = {"rss", "api", "webhook_ingest"}


class AggregationResult:
    """Result of an aggregation run."""

    def __init__(self) -> None:
        self.imported: int = 0
        self.skipped: int = 0
        self.errors: list[str] = []

    @property
    def total(self) -> int:
        return self.imported + self.skipped + len(self.errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "imported": self.imported,
            "skipped": self.skipped,
            "errors": self.errors[:10],  # Cap at 10
            "total": self.total,
        }


async def import_content_batch(
    db: AsyncSession,
    agent_entity_id: uuid.UUID,
    items: list[dict[str, Any]],
    source_type: str = "api",
    dedup_key: str = "external_id",
) -> AggregationResult:
    """Import a batch of content items as posts by a given agent entity.

    Each item should have:
    - content: str (required) -- the post text
    - external_id: str (optional) -- for deduplication
    - media_url: str (optional) -- media attachment
    - media_type: str (optional) -- image/video/gif
    - flair: str (optional) -- post category tag

    Returns AggregationResult with counts.
    """
    result = AggregationResult()

    if source_type not in SOURCE_TYPES:
        result.errors.append(f"Invalid source_type: {source_type}")
        return result

    # Verify the agent entity exists and is active
    entity = await db.get(Entity, agent_entity_id)
    if not entity or not entity.is_active:
        result.errors.append("Agent entity not found or inactive")
        return result

    # Get existing external IDs for dedup
    existing_external_ids: set[str] = set()
    if dedup_key == "external_id":
        # Check onboarding_data for previously imported IDs
        imported_ids = (entity.onboarding_data or {}).get("imported_ids", [])
        existing_external_ids = set(imported_ids)

    new_imported_ids: list[str] = []

    for item in items:
        try:
            content = item.get("content", "").strip()
            if not content:
                result.skipped += 1
                continue

            if len(content) > 10000:
                content = content[:10000]

            # Dedup check
            ext_id = item.get("external_id")
            if ext_id and ext_id in existing_external_ids:
                result.skipped += 1
                continue

            post = Post(
                id=uuid.uuid4(),
                author_entity_id=agent_entity_id,
                content=content,
                media_url=item.get("media_url"),
                media_type=item.get("media_type"),
                flair=item.get("flair"),
            )
            db.add(post)

            if ext_id:
                new_imported_ids.append(ext_id)
                existing_external_ids.add(ext_id)

            result.imported += 1

        except Exception as exc:
            result.errors.append(str(exc)[:200])

    # Update imported IDs in onboarding_data for future dedup
    if new_imported_ids:
        data = dict(entity.onboarding_data or {})
        prev = data.get("imported_ids", [])
        # Keep last 1000 IDs to prevent unbounded growth
        data["imported_ids"] = (prev + new_imported_ids)[-1000:]
        entity.onboarding_data = data

    await db.flush()

    logger.info(
        "Aggregation batch complete",
        extra={
            "agent_id": str(agent_entity_id),
            "source_type": source_type,
            **result.to_dict(),
        },
    )

    return result
