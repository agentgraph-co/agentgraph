"""Daily Reddit reply reminder.

Finds ONE relevant Reddit thread per day, generates a targeted draft
reply, and emails it to the admin. Skips the day if no good thread
is available.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.marketing.config import marketing_settings

logger = logging.getLogger(__name__)


async def _find_best_thread() -> dict | None:
    """Pick the single best thread to reply to today.

    Sources (in order):
    1. Reddit scout cache (from news-digest on Windows server)
    2. digest_history.json fallback

    Returns the thread dict or None if nothing worth replying to.
    """
    from src.marketing.reddit_scout import get_cached_threads

    threads = await get_cached_threads()

    # Fallback: digest history
    if not threads:
        try:
            from src.api.marketing_router import _reddit_from_digest_history

            digest_threads = _reddit_from_digest_history()
            if digest_threads:
                # Convert RedditThreadResponse → dict for fetch_thread_detail
                # Pick the first one with a URL
                for dt in digest_threads:
                    if dt.url:
                        return {"url": dt.url, "title": dt.title, "subreddit": dt.subreddit}
                return None
        except Exception:
            pass
        return None

    # Score threads: prefer more keywords matched, higher score, some comments
    def _score(t):  # type: ignore[no-untyped-def]
        s = len(t.keywords_matched) * 3
        if t.score > 50:
            s += 2
        if t.score > 200:
            s += 2
        if 3 <= t.num_comments <= 50:
            s += 2  # Active but not overwhelming
        return s

    threads.sort(key=_score, reverse=True)

    # Check Redis for threads we've already drafted replies to
    used_urls: set[str] = set()
    try:
        import json

        from src.redis_client import get_redis

        r = get_redis()
        data = await r.get("ag:reddit:used_threads")
        if data:
            used_urls = set(json.loads(data))
    except Exception:
        pass

    for t in threads:
        if t.url not in used_urls:
            return {
                "url": t.url,
                "title": t.title,
                "subreddit": t.subreddit,
                "score": t.score,
                "num_comments": t.num_comments,
            }

    return None


async def _generate_thread_reply(
    thread_url: str,
    db: AsyncSession,
) -> tuple[str | None, str | None, dict | None]:
    """Generate a draft reply for a specific thread.

    Returns (draft_content, llm_model, thread_detail) or (None, None, None).
    """
    from src.marketing.llm.cost_tracker import estimate_cost
    from src.marketing.llm.router import generate as llm_generate
    from src.marketing.reddit_scout import fetch_thread_detail

    detail = await fetch_thread_detail(thread_url)
    if not detail:
        logger.warning("Could not fetch thread detail: %s", thread_url)
        return None, None, None

    thread_title = detail["title"]
    thread_body = detail.get("selftext", "")[:1000]
    subreddit = detail.get("subreddit", "")
    top_comments_text = ""
    for c in detail.get("top_comments", [])[:3]:
        top_comments_text += (
            f"\n- u/{c['author']} ({c['score']} pts): "
            f"{c['body'][:200]}"
        )

    # 10% self-promotion rule
    promo_eligible = False
    try:
        from src.redis_client import get_redis

        redis = get_redis()
        post_number = await redis.incr("ag:reddit:post_count")
        promo_eligible = post_number % 10 == 0
    except Exception:
        pass

    if promo_eligible:
        rules = (
            "\n\nWrite a helpful, insightful reply that adds genuine "
            "value to the discussion. Rules:\n"
            "- Be helpful FIRST. Share knowledge or perspectives.\n"
            "- Where relevant, link to specific GitHub repos, tools, "
            "or libraries that help answer the question.\n"
            "- This thread is a good fit to naturally mention "
            "AgentGraph (agentgraph.co) if it's relevant to the "
            "topic. Work it in organically — NOT as an ad. Pair it "
            "with other useful recommendations.\n"
            "- Do NOT be promotional. No 'check out' or 'sign up'.\n"
            "- Match the subreddit's tone and culture.\n"
            "- Keep it concise — 2-4 paragraphs max.\n"
            "- No emojis, no hashtags, no marketing speak.\n"
            "- Sound like a knowledgeable developer, not a brand.\n"
        )
    else:
        rules = (
            "\n\nWrite a helpful, insightful reply that adds genuine "
            "value to the discussion. Rules:\n"
            "- Be helpful FIRST. Answer the question or add insight.\n"
            "- Do NOT mention AgentGraph, agentgraph.co, or any "
            "product/project you work on. Pure community contribution.\n"
            "- Where relevant, link to specific GitHub repos, tools, "
            "or libraries that help. Use real, well-known repos — do "
            "NOT invent URLs.\n"
            "- Match the subreddit's tone and culture.\n"
            "- Keep it concise — 2-4 paragraphs max.\n"
            "- No emojis, no hashtags, no marketing speak.\n"
            "- Sound like a knowledgeable developer sharing expertise.\n"
        )

    prompt = (
        f"You are writing a Reddit comment for r/{subreddit}.\n\n"
        f"Thread title: {thread_title}\n"
        f"Thread body: {thread_body}\n"
    )
    if top_comments_text:
        prompt += f"\nTop comments:{top_comments_text}\n"
    prompt += rules

    system = (
        "You are a knowledgeable developer and AI researcher who "
        "genuinely participates in Reddit discussions. You are NOT "
        "a marketing bot. Write like a real person sharing expertise."
    )

    result = await llm_generate(
        prompt,
        content_type="reddit_scout_draft",
        system=system,
        max_tokens=512,
        temperature=0.7,
    )

    if result.error:
        logger.warning("LLM failed for Reddit draft: %s", result.error)
        return None, None, None

    # Save as draft in the marketing_posts table
    from src.marketing.draft_queue import enqueue_draft

    cost = estimate_cost(result.model, result.tokens_in, result.tokens_out)
    await enqueue_draft(
        db,
        platform="reddit",
        content=result.text,
        topic=f"reply:{subreddit}",
        post_type="reactive",
        llm_model=result.model,
        llm_tokens_in=result.tokens_in,
        llm_tokens_out=result.tokens_out,
        llm_cost_usd=cost,
        utm_params={"thread_url": thread_url, "thread_title": thread_title},
    )
    await db.commit()

    return result.text, result.model, detail


async def _mark_thread_used(thread_url: str) -> None:
    """Track that we've drafted a reply for this thread so we don't repeat."""
    import json

    try:
        from src.redis_client import get_redis

        r = get_redis()
        key = "ag:reddit:used_threads"
        data = await r.get(key)
        used = json.loads(data) if data else []
        used.append(thread_url)
        # Keep last 100 URLs
        await r.set(key, json.dumps(used[-100:]), ex=86400 * 30)
    except Exception:
        pass


async def send_reddit_reminder(db: AsyncSession) -> bool:
    """Send a daily Reddit reply reminder email.

    Finds the best thread to reply to, generates a draft, and emails
    it. Skips the day if no good thread is found.

    Returns True if the email was sent, False otherwise.
    """
    # Guard against sending multiple reminders per day
    try:
        from src.redis_client import get_redis

        r = get_redis()
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sent_key = f"ag:mktg:reddit_reminder:{today_str}"
        already_sent = await r.get(sent_key)
        if already_sent:
            logger.debug("Reddit reminder already sent today")
            return False
    except Exception:
        pass

    # Find the best thread
    thread_info = await _find_best_thread()
    if not thread_info:
        logger.info("No good Reddit thread found today, skipping reminder")
        return False

    thread_url = thread_info["url"]

    # Generate a reply
    draft_content, llm_model, detail = await _generate_thread_reply(
        thread_url, db,
    )
    if not draft_content:
        logger.info("Could not generate Reddit draft, skipping reminder")
        return False

    await _mark_thread_used(thread_url)

    # Build email
    today_date = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
    thread_title = (detail or {}).get("title", thread_info.get("title", ""))
    subreddit = (detail or {}).get("subreddit", thread_info.get("subreddit", ""))

    from src.email import _load_template, send_email

    html = _load_template(
        "marketing_reddit_reminder.html",
        today_date=today_date,
        subreddit=f"r/{subreddit}" if subreddit else "Reddit",
        thread_title=thread_title,
        thread_url=thread_url,
        draft_content=draft_content,
        fallback=(
            f"Reddit reply: {thread_title}. "
            f"Review at https://agentgraph.co/admin"
        ),
    )

    sent = await send_email(
        marketing_settings.marketing_notify_email,
        f"Reddit reply draft — r/{subreddit}",
        html,
    )

    if sent:
        logger.info(
            "Reddit reminder sent: r/%s — %s", subreddit, thread_title[:60],
        )
        try:
            from src.redis_client import get_redis

            r = get_redis()
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            sent_key = f"ag:mktg:reddit_reminder:{today_str}"
            await r.set(sent_key, "1", ex=86400)
        except Exception:
            pass
    else:
        logger.warning("Failed to send Reddit reminder email")

    return sent
