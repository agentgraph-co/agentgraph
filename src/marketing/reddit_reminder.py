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


async def _find_best_thread(allow_used: bool = False) -> dict | None:
    """Pick the single best thread to reply to today.

    Sources (in order):
    1. Reddit scout cache (from news-digest on Windows server)
    2. digest_history.json fallback

    With ``allow_used=False`` (default) only fresh, never-drafted threads are
    returned. With ``allow_used=True`` it falls back to re-surfacing the best
    already-used thread when the feed has run dry, so we still have something to
    post. Returned dict carries ``recycled`` to flag that fallback.
    """
    from src.marketing.reddit_scout import get_cached_threads

    threads = await get_cached_threads()

    # Fallback: iterate reddit_thread_details directly from
    # digest_history.json — these have selftext + comments cached
    # and are the only threads we can draft replies for on EC2
    if not threads:
        try:
            import json as _json
            from pathlib import Path

            from src.marketing.reddit_scout import _DIGEST_PATHS
            from src.redis_client import get_redis

            # Load used-threads set so we don't repeat
            used_urls: set[str] = set()
            try:
                _r = get_redis()
                _data = await _r.get("ag:reddit:used_threads")
                if _data:
                    used_urls = set(_json.loads(_data))
            except Exception:
                pass

            # Read reddit_thread_details directly
            for p in _DIGEST_PATHS:
                path = Path(p)
                if not path.exists():
                    continue
                with open(path) as f:
                    data = _json.load(f)
                details = data.get("reddit_thread_details", {})
                recycle = None
                for url, detail in details.items():
                    if not detail.get("title"):
                        continue
                    if url not in used_urls:
                        return {
                            "url": url,
                            "title": detail["title"],
                            "subreddit": detail.get("subreddit", ""),
                            "recycled": False,
                        }
                    if recycle is None:
                        recycle = {
                            "url": url,
                            "title": detail["title"],
                            "subreddit": detail.get("subreddit", ""),
                            "recycled": True,
                        }
                if allow_used and recycle:
                    return recycle
                break  # Only read from the first available path
        except Exception:
            logger.debug("Failed to read digest thread details", exc_info=True)
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

    recycle = None
    for t in threads:
        if t.url not in used_urls:
            return {
                "url": t.url,
                "title": t.title,
                "subreddit": t.subreddit,
                "score": t.score,
                "num_comments": t.num_comments,
                "recycled": False,
            }
        if recycle is None:
            recycle = {
                "url": t.url,
                "title": t.title,
                "subreddit": t.subreddit,
                "score": t.score,
                "num_comments": t.num_comments,
                "recycled": True,
            }
    if allow_used and recycle:
        return recycle
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
    # Reply-guy: reply to ONE specific comment a real person wrote (not the
    # whole thread). Pick the top-scored comment as the target.
    top_comments = detail.get("top_comments", [])
    target = top_comments[0] if top_comments else None
    target_author = target["author"] if target else "OP"
    target_body = (target["body"] if target else thread_body)[:400]
    target_permalink = (target.get("permalink") if target else "") or thread_url

    # 10% self-promotion rule (on-topic / visible / non-promo post-selection
    # stays upstream in thread-finding — unchanged).
    promo_eligible = False
    try:
        from src.redis_client import get_redis

        redis = get_redis()
        post_number = await redis.incr("ag:reddit:post_count")
        promo_eligible = post_number % 10 == 0
    except Exception:
        pass

    promo_line = (
        "You MAY work in agentgraph.co/check ONLY if it's literally the punchline "
        "— never a pitch."
        if promo_eligible
        else "Do NOT mention AgentGraph or any product. Pure community snark."
    )

    from src.marketing.content.ai_tells import VOICE_PROMPT_FRAGMENT

    prompt = (
        f"You're a real dev lurking in r/{subreddit}. Reply to THIS comment like "
        f"you'd thumb it out on your phone:\n\n"
        f'Thread: "{thread_title}"\n'
        f'u/{target_author} wrote: "{target_body}"\n\n'
        f"Write ONE sentence (two MAX, and keep them short). Fun, a little snarky, "
        f"genuinely on-topic — the kind of reply that gets upvoted for being funny "
        f"and true, not for being a helpful bot. {promo_line}\n\n"
        f"{VOICE_PROMPT_FRAGMENT}\n"
        "Hard no's: emojis, hashtags, 'Great point/question', em-dashes, bullet "
        "lists, corporate voice, 'it's worth noting'. lowercase is fine. It must "
        "read like a human shitposting, not an AI being helpful.\n\n"
        "Reply (just the text):"
    )

    system = (
        "You write Reddit comments that pass for a real, slightly-snarky "
        "developer. Short, specific, funny. You never sound like AI or marketing."
    )

    result = await llm_generate(
        prompt,
        content_type="reddit_scout_draft",
        system=system,
        max_tokens=120,
        temperature=0.85,
    )

    if result.error:
        logger.warning("LLM failed for Reddit draft: %s", result.error)
        return None, None, None

    # Flag if it still reads like AI (human reviews + posts Reddit anyway).
    from src.marketing.content.ai_tells import check as check_ai_tells

    tells = check_ai_tells(result.text, platform="reddit", strict=True)
    if not tells.passed:
        logger.warning(
            "Reddit draft tripped AI-tell check (%s): %s",
            tells.reasons, result.text[:120],
        )

    # Save as draft. utm_params carries the REPLY TARGET so review shows exactly
    # which comment this answers, plus a direct permalink to it.
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
        utm_params={
            "thread_url": thread_url,
            "thread_title": thread_title,
            "reply_to_author": target_author,
            "reply_to_excerpt": target_body[:280],
            "reply_to_permalink": target_permalink,
            "ai_tells_ok": tells.passed,
        },
    )
    await db.flush()

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


async def _send_dry_feed_alert() -> None:
    """Email the admin when the Reddit feed has nothing to draft from.

    Throttled to once every 2 days so it nudges without nagging. Fires when the
    upstream news-digest stops populating ``reddit_thread_details`` — AgentGraph
    is fine, the feed is just dry.
    """
    try:
        from src.redis_client import get_redis

        r = get_redis()
        if await r.get("ag:mktg:reddit_dry_alert"):
            return
        await r.set("ag:mktg:reddit_dry_alert", "1", ex=86400 * 2)
    except Exception:
        pass
    try:
        from src.email import send_email

        html = (
            "<p>No Reddit threads were available to draft a reply from "
            "(fresh or re-surfaced).</p>"
            "<p>AgentGraph is working as intended — the upstream "
            "<b>news-digest</b> isn't populating <code>reddit_thread_details</code>, "
            "so the Reddit feed is dry. Check the news-digest's Reddit capture "
            "(Windows server).</p>"
            "<p>Reply drafts resume automatically once the feed returns.</p>"
        )
        await send_email(
            marketing_settings.marketing_notify_email,
            "Reddit feed is dry — no reply drafts (check the news-digest)",
            html,
        )
        logger.info("Sent Reddit dry-feed alert")
    except Exception:
        logger.debug("Failed to send Reddit dry-feed alert", exc_info=True)


async def _generate_news_post(db: AsyncSession) -> bool:
    """Fallback when there's no thread to reply to: the old-style 3-paragraph
    Reddit post grounded in the news-digest signals (the news/reddit items the
    digest collected — `sent_articles`, which keep flowing even when the reply
    thread feed is dry). Goes to the review queue + email. Reply-guy stays
    primary; this only fires when there's no thread to reply to.

    Returns True if a draft was produced, False if there's no news to post about.
    """
    try:
        from src.marketing.news_signals import gather_news_signals

        signals = await gather_news_signals(limit=5, days=7)
    except Exception:
        logger.debug("Failed to gather news signals", exc_info=True)
        signals = []
    if not signals:
        return False

    headlines = "\n".join(
        f"- {s['title']} ({s.get('source', '')})"
        + (f": {s['summary'][:160]}" if s.get("summary") else "")
        for s in signals[:5]
    )

    from src.marketing.content.ai_tells import VOICE_PROMPT_FRAGMENT
    from src.marketing.content.ai_tells import check as check_ai_tells
    from src.marketing.llm.cost_tracker import estimate_cost
    from src.marketing.llm.router import generate as llm_generate

    prompt = (
        "You're a developer who works on AI-agent trust/security, writing a Reddit "
        "post for a sub like r/LocalLLaMA or r/programming. React to what's actually "
        "happening in the news below — pick the most interesting item and write about "
        "IT, with a real point of view, not about your product.\n\n"
        f"Today's AI/agent news:\n{headlines}\n\n"
        "Write a hooky one-line title, then ~3 short paragraphs. Be specific and a "
        "little opinionated. You MAY mention agentgraph.co/check once, only if it's "
        "genuinely relevant to the point — never as a pitch, and it's fine to leave "
        "it out entirely.\n\n"
        f"{VOICE_PROMPT_FRAGMENT}\n"
        "Hard no's: emojis, hashtags, 'Great point', em-dash spam, corporate voice, "
        "listicles. Read like a human with an opinion.\n\n"
        "Format:\nTitle: <title>\n\n<post body>"
    )
    system = (
        "You write Reddit posts that pass for a real, opinionated developer reacting "
        "to industry news. You never sound like AI or marketing."
    )

    result = await llm_generate(
        prompt,
        content_type="reddit_news_post",
        system=system,
        max_tokens=420,
        temperature=0.8,
    )
    if result.error or not result.text:
        logger.warning("LLM failed for Reddit news post: %s", result.error)
        return False

    tells = check_ai_tells(result.text, platform="reddit", strict=True)
    if not tells.passed:
        logger.warning("Reddit news-post tripped AI-tell check: %s", tells.reasons)

    top = signals[0]
    # Clickable source links so the draft says exactly what it's reacting to
    # (rendered as links in the admin playbook + the email).
    sources = [
        {"url": s["url"], "anchor": f"{s['title']} ({s.get('source', '')})"}
        for s in signals[:5] if s.get("url")
    ]
    playbook = {
        "mode": "news-grounded 3-paragraph post — FALLBACK (no thread to reply to)",
        "sources": sources or [
            f"{s['title']} ({s.get('source', '')})" for s in signals[:5]
        ],
        "subreddits": ["r/LocalLLaMA", "r/programming", "r/SideProject"],
        "tips": [
            "Standalone post reacting to news, not a reply — pick a self-post-friendly sub.",
            "Lead with the take; link a source above if it fits.",
            "You post manually, then mark Posted + paste the URL.",
        ],
    }
    try:
        from src.marketing.draft_queue import enqueue_draft

        cost = estimate_cost(result.model, result.tokens_in, result.tokens_out)
        await enqueue_draft(
            db, platform="reddit", content=result.text, topic="news_post",
            post_type="proactive", llm_model=result.model,
            llm_tokens_in=result.tokens_in, llm_tokens_out=result.tokens_out,
            llm_cost_usd=cost,
            utm_params={
                "platform_playbook": {"reddit": playbook},
                "ai_tells_ok": tells.passed,
            },
        )
        await db.flush()
    except Exception:
        logger.debug("Failed to enqueue Reddit news-post draft", exc_info=True)

    try:
        from src.email import send_email

        sources_html = (
            "".join(f"<li><a href=\"{s['url']}\">{s['anchor']}</a></li>" for s in sources)
            if sources
            else f"<li>{top['title']} ({top.get('source', '')})</li>"
        )
        html = (
            "<p><b>No Reddit thread to reply to today</b> — the reply thread feed is "
            "dry, so here's a news-grounded post draft instead (in your review queue "
            "too).</p>"
            f"<p><b>Reacting to (sources — click to read/discuss):</b></p>"
            f"<ul>{sources_html}</ul>"
            "<p>Post to a self-post-friendly sub, lead with the take — you post "
            "manually.</p>"
            f"<hr><pre style='white-space:pre-wrap'>{result.text}</pre>"
        )
        await send_email(
            marketing_settings.marketing_notify_email,
            "Reddit post draft (news-based — no thread to reply to)",
            html,
        )
    except Exception:
        logger.debug("Failed to email Reddit news-post draft", exc_info=True)
    return True


async def send_reddit_reminder(db: AsyncSession) -> bool:
    """Send a daily Reddit reply reminder email.

    Finds the best thread (fresh, or a re-surfaced older one if the feed has run
    dry), generates a draft, and emails it. If there's genuinely nothing to draft,
    sends a throttled dry-feed alert instead of going silent.

    Returns True if a draft email was sent, False otherwise.
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

    # Find the best thread — fresh first, then recycle an older one if the feed
    # has run dry, so we still surface something to post.
    thread_info = await _find_best_thread()
    if not thread_info:
        thread_info = await _find_best_thread(allow_used=True)
    recycled = bool(thread_info and thread_info.get("recycled"))

    draft_content = llm_model = detail = None
    if thread_info:
        draft_content, llm_model, detail = await _generate_thread_reply(
            thread_info["url"], db,
        )

    # No thread to reply to → fall back to a standalone post draft (reply-guy
    # stays primary). Only if that also fails do we send the dry-feed alert.
    if not draft_content:
        logger.info("No Reddit thread to reply to — trying news-grounded post fallback")
        produced = await _generate_news_post(db)
        if not produced:
            await _send_dry_feed_alert()
        try:
            from src.redis_client import get_redis

            r = get_redis()
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            await r.set(f"ag:mktg:reddit_reminder:{today_str}", "1", ex=86400)
        except Exception:
            pass
        return produced

    thread_url = thread_info["url"]
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

    subject = f"Reddit reply draft — r/{subreddit}"
    if recycled:
        subject = f"Reddit reply draft (re-surfaced older thread) — r/{subreddit}"
    sent = await send_email(
        marketing_settings.marketing_notify_email,
        subject,
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
