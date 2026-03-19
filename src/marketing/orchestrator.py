"""Marketing orchestrator — coordinates proactive, reactive, and
data-driven content across all configured platforms.

Called by the background scheduler (Job 7) every 30 minutes.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.marketing.adapters.base import AbstractPlatformAdapter
from src.marketing.config import marketing_settings
from src.marketing.content.engine import (
    GeneratedContent,
    generate_proactive,
)
from src.marketing.draft_queue import enqueue_draft
from src.marketing.models import MarketingPost
from src.marketing.scheduler import (
    get_platform_intervals,
    get_recent_topics,
    record_post,
    record_topic,
    should_post,
)

logger = logging.getLogger(__name__)

# Platforms that require human approval — draft only, never auto-post
HUMAN_APPROVAL_PLATFORMS = {"hackernews", "producthunt"}


def _get_adapters() -> dict[str, AbstractPlatformAdapter]:
    """Lazy-load configured platform adapters."""
    from src.marketing.adapters.bluesky import BlueskyAdapter
    from src.marketing.adapters.reddit import RedditAdapter
    from src.marketing.adapters.twitter import TwitterAdapter

    return {
        "twitter": TwitterAdapter(),
        "reddit": RedditAdapter(),
        "bluesky": BlueskyAdapter(),
        # Phase 3 adapters added here as implemented
    }


async def _is_duplicate(db: AsyncSession, h: str, platform: str) -> bool:
    """Check if content was already posted (dedup by hash + platform)."""
    window = datetime.now(timezone.utc) - timedelta(
        days=marketing_settings.content_dedup_window_days,
    )
    result = await db.execute(
        select(MarketingPost.id).where(
            MarketingPost.content_hash == h,
            MarketingPost.platform == platform,
            MarketingPost.created_at >= window,
        ).limit(1),
    )
    return result.scalar_one_or_none() is not None


async def _save_post(
    db: AsyncSession,
    content: GeneratedContent,
    status: str = "queued",
    external_id: str | None = None,
    url: str | None = None,
    error: str | None = None,
    campaign_id: uuid.UUID | None = None,
) -> MarketingPost:
    """Persist a marketing post to the database."""
    post = MarketingPost(
        id=uuid.uuid4(),
        campaign_id=campaign_id,
        platform=content.platform,
        external_id=external_id,
        content=content.text,
        content_hash=content.content_hash,
        post_type=content.post_type,
        topic=content.topic,
        status=status,
        llm_model=content.llm_model,
        llm_tokens_in=content.llm_tokens_in,
        llm_tokens_out=content.llm_tokens_out,
        llm_cost_usd=content.llm_cost_usd,
        utm_params=content.utm_params,
        error_message=error,
        posted_at=datetime.now(timezone.utc) if status == "posted" else None,
    )
    db.add(post)
    await db.flush()
    return post


async def _post_planned_campaign_posts(
    db: AsyncSession,
) -> dict:
    """Post planned posts from approved campaigns for today."""
    from src.marketing.campaign_planner import (
        get_planned_posts_for_today,
    )

    adapters = _get_adapters()
    results: dict = {
        "posted": [], "skipped": [], "errors": [],
    }
    planned = await get_planned_posts_for_today(db)

    for post in planned:
        adapter = adapters.get(post.platform)
        if not adapter or not await adapter.is_configured():
            results["skipped"].append({
                "id": str(post.id),
                "platform": post.platform,
                "reason": "not_configured",
            })
            continue

        if post.platform in HUMAN_APPROVAL_PLATFORMS:
            await enqueue_draft(
                db,
                platform=post.platform,
                content=post.content,
                topic=post.topic,
                llm_model=None,
                llm_tokens_in=0,
                llm_tokens_out=0,
                llm_cost_usd=0.0,
                utm_params=None,
            )
            post.status = "human_review"
            results["skipped"].append({
                "id": str(post.id),
                "platform": post.platform,
                "reason": "human_review",
            })
            continue

        try:
            result = await adapter.post(post.content)
            if result.success:
                post.status = "posted"
                post.external_id = result.external_id
                post.posted_at = datetime.now(timezone.utc)
                await record_post(post.platform)
                if post.topic:
                    await record_topic(
                        post.platform, post.topic,
                    )
                results["posted"].append({
                    "id": str(post.id),
                    "platform": post.platform,
                    "topic": post.topic,
                    "external_id": result.external_id,
                })
            else:
                post.status = "failed"
                post.error_message = result.error
                results["errors"].append({
                    "id": str(post.id),
                    "error": result.error,
                })
        except Exception as exc:
            logger.exception(
                "Campaign post %s failed", post.id,
            )
            post.status = "failed"
            post.error_message = str(exc)
            results["errors"].append({
                "id": str(post.id),
                "error": str(exc),
            })

    await db.flush()
    return results


async def run_proactive_cycle(db: AsyncSession) -> dict:
    """Run one proactive posting cycle across all platforms.

    For each platform:
    0. Check for planned campaign posts first
    1. Check if it's time to post (respecting cadence)
    2. Pick a topic (respecting cooldowns)
    3. Generate content
    4. Post (or enqueue for human review)
    5. Record in DB
    """
    campaign_results = await _post_planned_campaign_posts(db)
    campaign_platforms = {
        p["platform"]
        for p in campaign_results["posted"]
    }

    adapters = _get_adapters()
    intervals = await get_platform_intervals()

    results: dict = {
        "posted": list(campaign_results["posted"]),
        "skipped": list(campaign_results["skipped"]),
        "errors": list(campaign_results["errors"]),
        "drafts": [],
        "campaign_posts": len(campaign_results["posted"]),
    }

    for platform_name, adapter in adapters.items():
        # Skip platforms that already got a campaign post
        if platform_name in campaign_platforms:
            results["skipped"].append(
                {
                    "platform": platform_name,
                    "reason": "campaign_post_sent",
                },
            )
            continue
        try:
            # Check if adapter is configured
            if not await adapter.is_configured():
                results["skipped"].append(
                    {"platform": platform_name, "reason": "not_configured"},
                )
                continue

            # Check cadence
            interval = intervals.get(platform_name, 86400)
            if not await should_post(platform_name, interval):
                results["skipped"].append(
                    {"platform": platform_name, "reason": "cadence_not_met"},
                )
                continue

            # Get recent topics for cooldown
            recent_topics = await get_recent_topics(platform_name)

            # Generate content
            content = await generate_proactive(
                platform_name, recent_topics=recent_topics,
            )
            if content.error:
                results["errors"].append(
                    {"platform": platform_name, "error": content.error},
                )
                continue

            # Dedup check
            if await _is_duplicate(db, content.content_hash, platform_name):
                results["skipped"].append(
                    {"platform": platform_name, "reason": "duplicate"},
                )
                continue

            # Human approval platforms → draft queue
            if platform_name in HUMAN_APPROVAL_PLATFORMS:
                await enqueue_draft(
                    db, platform=platform_name, content=content.text,
                    topic=content.topic, llm_model=content.llm_model,
                    llm_tokens_in=content.llm_tokens_in,
                    llm_tokens_out=content.llm_tokens_out,
                    llm_cost_usd=content.llm_cost_usd,
                    utm_params=content.utm_params,
                )
                results["drafts"].append({"platform": platform_name, "topic": content.topic})
                continue

            # Post it
            result = await adapter.post(content.text)

            if result.success:
                await _save_post(
                    db, content, status="posted",
                    external_id=result.external_id, url=result.url,
                )
                await record_post(platform_name)
                await record_topic(platform_name, content.topic)
                results["posted"].append({
                    "platform": platform_name,
                    "topic": content.topic,
                    "external_id": result.external_id,
                })
                logger.info(
                    "Posted to %s: topic=%s external_id=%s",
                    platform_name, content.topic, result.external_id,
                )
            elif result.rate_limited:
                results["skipped"].append(
                    {"platform": platform_name, "reason": "rate_limited"},
                )
            else:
                await _save_post(
                    db, content, status="failed", error=result.error,
                )
                results["errors"].append(
                    {"platform": platform_name, "error": result.error},
                )

        except Exception:
            logger.exception("Proactive cycle failed for %s", platform_name)
            results["errors"].append(
                {"platform": platform_name, "error": "unexpected_exception"},
            )

    return results


async def post_approved_drafts(db: AsyncSession) -> dict:
    """Post any drafts that were approved by a human (status='queued')."""
    adapters = _get_adapters()
    results: dict = {"posted": [], "errors": []}

    queued = await db.execute(
        select(MarketingPost).where(
            MarketingPost.status == "queued",
        ).order_by(MarketingPost.created_at.asc()).limit(10),
    )
    posts = list(queued.scalars().all())

    for post in posts:
        adapter = adapters.get(post.platform)
        if not adapter or not await adapter.is_configured():
            post.status = "failed"
            post.error_message = f"Adapter not configured: {post.platform}"
            results["errors"].append({"id": str(post.id), "error": post.error_message})
            continue

        try:
            result = await adapter.post(post.content)
            if result.success:
                post.status = "posted"
                post.external_id = result.external_id
                post.posted_at = datetime.now(timezone.utc)
                await record_post(post.platform)
                if post.topic:
                    await record_topic(post.platform, post.topic)
                results["posted"].append({
                    "id": str(post.id),
                    "platform": post.platform,
                    "external_id": result.external_id,
                })
            else:
                post.retry_count += 1
                if post.retry_count >= marketing_settings.max_retry_count:
                    post.status = "permanently_failed"
                else:
                    post.status = "queued"  # Will retry next cycle
                post.error_message = result.error
                results["errors"].append({
                    "id": str(post.id), "error": result.error,
                })
        except Exception as exc:
            logger.exception("Failed to post approved draft %s", post.id)
            post.retry_count += 1
            post.error_message = str(exc)
            results["errors"].append({"id": str(post.id), "error": str(exc)})

    await db.flush()
    return results


async def run_marketing_tick(db: AsyncSession) -> dict:
    """Main entry point — called by the scheduler every 30 minutes.

    Runs proactive posting and processes approved drafts.
    """
    if not marketing_settings.marketing_enabled:
        return {"status": "disabled"}

    results: dict = {}

    # 1. Post any approved drafts
    draft_results = await post_approved_drafts(db)
    results["drafts"] = draft_results

    # 2. Run proactive cycle
    proactive_results = await run_proactive_cycle(db)
    results["proactive"] = proactive_results

    # 3. Run reactive monitoring cycle
    try:
        from src.marketing.monitor import run_monitoring_cycle

        monitor_results = await run_monitoring_cycle(db)
        results["monitoring"] = monitor_results
    except Exception:
        logger.exception("Monitoring cycle failed")
        results["monitoring"] = {"error": "cycle_failed"}

    # 4. Check for failures and alert admin
    try:
        from src.marketing.alerts import check_and_alert_failures

        await check_and_alert_failures(db, results)
    except Exception:
        logger.exception("Failure alerting failed")

    logger.info("Marketing tick complete: %s", results)
    return results
