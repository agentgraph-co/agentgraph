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
from src.marketing.config import PLATFORM_SCHEDULE, marketing_settings
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

# Day abbreviation map (datetime weekday int → 3-letter abbreviation)
_DAY_ABBR = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}


def _today_abbr() -> str:
    """Return today's 3-letter day abbreviation (e.g. 'mon', 'tue')."""
    return _DAY_ABBR[datetime.now(timezone.utc).weekday()]


def _is_platform_scheduled_today(platform: str) -> bool:
    """Check if *platform* is scheduled to post today per PLATFORM_SCHEDULE.

    Platforms not listed in PLATFORM_SCHEDULE are always allowed (legacy
    behaviour — e.g. discord, telegram, github_discussions).
    """
    schedule = PLATFORM_SCHEDULE.get(platform)
    if schedule is None:
        return True  # no schedule constraint → allow
    return _today_abbr() in schedule.get("days", [])


def _is_auto_post(platform: str) -> bool:
    """Return True if the platform can auto-post without human review."""
    schedule = PLATFORM_SCHEDULE.get(platform)
    if schedule is None:
        return False  # unlisted platforms default to human review
    return schedule.get("auto_post", False)


# Platforms that require human approval.  Now derived from PLATFORM_SCHEDULE
# for scheduled platforms; all others still require approval by default.
HUMAN_APPROVAL_PLATFORMS = {
    name
    for name, cfg in PLATFORM_SCHEDULE.items()
    if not cfg.get("auto_post", False)
} | {
    # Platforms not in PLATFORM_SCHEDULE that should always need approval
    "discord", "telegram", "github_discussions",
    "hackernews", "producthunt",
}


def _get_adapters() -> dict[str, AbstractPlatformAdapter]:
    """Lazy-load configured platform adapters."""
    from src.marketing.adapters.bluesky import BlueskyAdapter
    from src.marketing.adapters.devto import DevtoAdapter
    from src.marketing.adapters.discord_bot import DiscordAdapter
    from src.marketing.adapters.github_discussions import GitHubDiscussionsAdapter
    from src.marketing.adapters.hashnode import HashnodeAdapter
    from src.marketing.adapters.huggingface import HuggingFaceAdapter
    from src.marketing.adapters.linkedin import LinkedInAdapter
    from src.marketing.adapters.reddit import RedditAdapter
    from src.marketing.adapters.telegram_bot import TelegramAdapter
    from src.marketing.adapters.twitter import TwitterAdapter

    return {
        "twitter": TwitterAdapter(),
        "reddit": RedditAdapter(),
        "bluesky": BlueskyAdapter(),
        "linkedin": LinkedInAdapter(),
        "discord": DiscordAdapter(),
        "devto": DevtoAdapter(),
        "github_discussions": GitHubDiscussionsAdapter(),
        "huggingface": HuggingFaceAdapter(),
        "telegram": TelegramAdapter(),
        "hashnode": HashnodeAdapter(),
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
    0. Budget pre-check (skip entire cycle if daily LLM budget exhausted)
    1. Check for planned campaign posts first
    2. Check if it's time to post (respecting cadence)
    3. Pick a topic (respecting cooldowns)
    4. Generate content
    5. Post (or enqueue for human review)
    6. Record in DB
    """
    from src.marketing.llm.cost_tracker import get_daily_spend

    daily_spend = await get_daily_spend()
    if daily_spend >= marketing_settings.marketing_llm_daily_budget:
        logger.info(
            "Daily LLM budget exhausted ($%.2f/$%.2f), skipping proactive cycle",
            daily_spend, marketing_settings.marketing_llm_daily_budget,
        )
        return {"skipped": True, "reason": "budget_exhausted"}

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

        # Skip platforms not scheduled for today
        if not _is_platform_scheduled_today(platform_name):
            results["skipped"].append(
                {"platform": platform_name, "reason": "not_scheduled_today"},
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

            # Non-auto-post platforms → draft queue for human review
            if not _is_auto_post(platform_name):
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

            # Post it (with image if available)
            post_metadata = {}
            if content.image_path:
                post_metadata["image_path"] = content.image_path
            result = await adapter.post(
                content.text,
                metadata=post_metadata or None,
            )

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
                # Increment rate-limit counter for watchdog
                try:
                    from src.redis_client import get_redis

                    _r = get_redis()
                    await _r.incr("ag:mktg:rate_limit_count")
                    await _r.expire(
                        "ag:mktg:rate_limit_count", 86400,
                    )
                except Exception:
                    pass
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


async def generate_and_post_for_platform(
    db: AsyncSession, platform: str,
) -> dict:
    """Generate and enqueue a post for a single platform (admin trigger).

    Bypasses cadence checks — always generates content.
    """
    if not marketing_settings.marketing_enabled:
        return {"status": "disabled"}

    adapters = _get_adapters()
    adapter = adapters.get(platform)
    if adapter is None:
        return {"status": "error", "error": f"Unknown platform: {platform}"}

    if not await adapter.is_configured():
        return {"status": "error", "error": f"{platform} is not configured"}

    recent_topics = await get_recent_topics(platform)

    content = await generate_proactive(platform, recent_topics=recent_topics)
    if content.error:
        return {"status": "error", "error": content.error}

    if await _is_duplicate(db, content.content_hash, platform):
        return {"status": "skipped", "reason": "duplicate"}

    # Always go through human approval for manual triggers
    draft = await enqueue_draft(
        db, platform=platform, content=content.text,
        topic=content.topic, llm_model=content.llm_model,
        llm_tokens_in=content.llm_tokens_in,
        llm_tokens_out=content.llm_tokens_out,
        llm_cost_usd=content.llm_cost_usd,
        utm_params=content.utm_params,
    )
    return {
        "status": "draft_created",
        "platform": platform,
        "topic": content.topic,
        "draft_id": str(draft.id),
    }


async def generate_milestone_drafts(
    db: AsyncSession,
    topic_key: str,
    platforms: list[str] | None = None,
) -> dict:
    """Generate drafts for a specific topic across all (or selected) platforms.

    All drafts go to ``human_review`` status — no auto-posting.
    Bypasses cadence and schedule checks (this is a manual milestone trigger).

    Returns a summary dict with lists of created drafts and any errors.
    """
    from src.marketing.content.topics import TOPIC_BY_KEY

    topic = TOPIC_BY_KEY.get(topic_key)
    if not topic:
        return {"status": "error", "error": f"Unknown topic: {topic_key}"}

    adapters = _get_adapters()
    target_platforms = platforms or list(adapters.keys())

    results: dict = {"status": "ok", "drafts": [], "errors": [], "skipped": []}

    for platform_name in target_platforms:
        adapter = adapters.get(platform_name)
        if adapter is None:
            results["skipped"].append(
                {"platform": platform_name, "reason": "unknown_platform"},
            )
            continue

        if not await adapter.is_configured():
            results["skipped"].append(
                {"platform": platform_name, "reason": "not_configured"},
            )
            continue

        # Check if the topic has an angle for this platform
        if platform_name not in topic.angles:
            results["skipped"].append(
                {"platform": platform_name, "reason": "no_angle_for_platform"},
            )
            continue

        try:
            content = await generate_proactive(
                platform_name,
                recent_topics=None,  # bypass cooldown
                topic_override=topic,
            )
            if content.error:
                results["errors"].append(
                    {"platform": platform_name, "error": content.error},
                )
                continue

            # Dedup check — skip if already generated for this platform
            if await _is_duplicate(db, content.content_hash, platform_name):
                results["skipped"].append(
                    {"platform": platform_name, "reason": "duplicate"},
                )
                continue

            draft = await enqueue_draft(
                db,
                platform=platform_name,
                content=content.text,
                topic=content.topic,
                llm_model=content.llm_model,
                llm_tokens_in=content.llm_tokens_in,
                llm_tokens_out=content.llm_tokens_out,
                llm_cost_usd=content.llm_cost_usd,
                utm_params=content.utm_params,
            )
            results["drafts"].append({
                "platform": platform_name,
                "topic": content.topic,
                "draft_id": str(draft.id),
            })
            logger.info(
                "Milestone draft created for %s: %s (topic=%s)",
                platform_name, draft.id, topic_key,
            )

        except Exception:
            logger.exception(
                "Milestone draft generation failed for %s", platform_name,
            )
            results["errors"].append(
                {"platform": platform_name, "error": "unexpected_exception"},
            )

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

    # 2b. Notify admin if new drafts were created for human review
    new_drafts = proactive_results.get("drafts", [])
    if new_drafts:
        try:
            from src.marketing.draft_notify import notify_pending_drafts

            await notify_pending_drafts(new_drafts)
        except Exception:
            logger.exception("Draft notification failed")

    # 3. Run HF auto-pick cycle on posting days (Wed/Sat)
    try:
        from datetime import date as _date

        _today = _date.today().strftime("%a").lower()
        hf_days = {"wed", "sat"}
        if _today in hf_days:
            from src.marketing.hf_autopick import run_hf_autopick_cycle

            hf_result = await run_hf_autopick_cycle()
            results["hf_autopick"] = hf_result
            logger.info("HF auto-pick result: %s", hf_result.get("status"))
        else:
            results["hf_autopick"] = {"status": "not_hf_day", "today": _today}
    except Exception:
        logger.exception("HF auto-pick cycle failed")
        results["hf_autopick"] = {"error": "cycle_failed"}

    # 4. Run reactive monitoring cycle
    try:
        from src.marketing.monitor import run_monitoring_cycle

        monitor_results = await run_monitoring_cycle(db)
        results["monitoring"] = monitor_results
    except Exception:
        logger.exception("Monitoring cycle failed")
        results["monitoring"] = {"error": "cycle_failed"}

    # 5. Send Reddit posting day reminder (Tue/Thu)
    try:
        from src.marketing.reddit_reminder import send_reddit_reminder

        reddit_reminded = await send_reddit_reminder(db)
        results["reddit_reminder"] = reddit_reminded
    except Exception:
        logger.exception("Reddit reminder failed")
        results["reddit_reminder"] = False

    # 6. Send weekly plan reminder (Sunday)
    try:
        from src.marketing.plan_reminder import send_plan_reminder

        plan_reminded = await send_plan_reminder(db)
        results["plan_reminder"] = plan_reminded
    except Exception:
        logger.exception("Plan reminder failed")
        results["plan_reminder"] = False

    # 7. Check for failures and alert admin
    try:
        from src.marketing.alerts import check_and_alert_failures

        await check_and_alert_failures(db, results)
    except Exception:
        logger.exception("Failure alerting failed")

    logger.info("Marketing tick complete: %s", results)
    return results
