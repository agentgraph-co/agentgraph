"""Weekly campaign planning system.

Generates structured campaign plans using Opus, saves them as
MarketingCampaign records, and supports approve/reject workflows.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.email import send_email
from src.marketing.config import PLATFORM_SCHEDULE, marketing_settings
from src.marketing.models import MarketingCampaign, MarketingPost
from src.marketing.news_signals import gather_news_signals

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are the campaign strategist for AgentGraph — the social network \
and trust infrastructure for AI agents and humans.

AgentGraph's positioning: decentralised identity (on-chain DIDs), \
auditable agent evolution trails, trust-scored social graph, and a \
protocol-level foundation (AIP + DSNP) that any agent framework can \
plug into.  We are NOT competing with frameworks like OpenClaw or \
social platforms like Moltbook — we operate underneath them as the \
identity and trust layer.

## Recent milestone: 700K Moltbook agent import (March 2026)
We imported 700,010 agent profiles from Moltbook after their data \
breach (1.5M API tokens + 35K emails leaked).  Each imported agent \
gets a public profile, provisional DID, 0.13 trust score (honest — \
unverified), and the ability for operators to claim and verify. \
This is a major talking point: "Moltbook lost your trust. We're \
giving it back." Operators can claim at agentgraph.co/bot-onboarding.

## Current competitive landscape (March 2026)
- OpenClaw: 512 CVEs, massive adoption in China (1000+ queued at \
  Tencent HQ for installs), elevated system access concerns, \
  NVIDIA partnering via NemoClaw for enterprise
- Moltbook: acquired by Meta, went viral for FAKE POSTS (bot \
  content mistaken for human), 770K agents, zero identity verification
- World/Tools for Humanity: launched "proof of human" for agentic \
  commerce — biometric verification for AI shopping agents. \
  Validates our thesis that agents need identity verification.
- Bluesky: $100M Series B, continuing AT Protocol development, \
  decentralised social — aligns with our values
- NVIDIA GTC: $1T AI chip projection, "OpenClaw strategy" for \
  enterprise, NemoClaw — compute layer complementary to our trust layer

## CRITICAL: Bot content transparency
After the Moltbook fake-posts scandal, transparency is paramount. \
ALL AgentGraph marketing content must be clearly identifiable as \
bot-generated. Never try to pass bot content as human-written. \
This is both ethical and strategic — our brand IS trust.

Your job is to produce a JSON campaign plan for the coming week.  \
The plan must respect platform norms:
- Reddit: 9:1 value-to-promotion ratio.  Lead with genuine insight.
- Hacker News: human-only; never auto-post.  Pure value, no product \
  pitching.
- Twitter/Bluesky: concise, opinionated takes.
- Dev.to / Hashnode: long-form technical deep-dives.
- LinkedIn: professional tone, thought leadership.
- Discord / Telegram: community engagement.

Respond ONLY with a JSON object (no markdown fences) matching this \
schema exactly:

{
  "strategy_summary": "<2-3 sentences>",
  "posts": [
    {
      "platform": "<string>",
      "topic": "<string>",
      "angle": "<specific hook>",
      "content_brief": "<what to write>",
      "day": "<monday|tuesday|...>",
      "value_type": "<pure_value|soft_mention|product_feature>",
      "why": "<why this will resonate>"
    }
  ],
  "news_hooks": [
    {"title": "<string>", "angle": "<string>"}
  ],
  "avoid_this_week": ["<string>"],
  "budget_estimate_usd": <float>
}
"""


async def _last_week_performance(
    db: AsyncSession,
) -> list[dict]:
    """Summarise marketing post performance from the past 7 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    result = await db.execute(
        select(MarketingPost).where(
            MarketingPost.posted_at >= cutoff,
            MarketingPost.status == "posted",
        ).order_by(MarketingPost.posted_at.desc()),
    )
    rows = result.scalars().all()
    summary: list[dict] = []
    for row in rows:
        summary.append({
            "platform": row.platform,
            "topic": row.topic,
            "post_type": row.post_type,
            "engagement": row.metrics_json or {},
            "posted_at": (
                row.posted_at.isoformat() if row.posted_at else ""
            ),
        })
    return summary


def _parse_json_response(raw: str) -> dict | None:
    """Extract and parse JSON from an LLM response.

    Handles markdown code fences, preamble text, and minor
    truncation at the end.
    """
    import re

    text = raw.strip()

    # Try to extract JSON from code fences first
    fence_match = re.search(
        r"```(?:json)?\s*\n(.*?)```",
        text,
        re.DOTALL,
    )
    if fence_match:
        text = fence_match.group(1).strip()
    else:
        # Try to find the outermost { ... }
        start = text.find("{")
        if start >= 0:
            text = text[start:]

    # Try parsing as-is
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # If truncated, try closing open braces/brackets
    for suffix in ["}", "]}", "\"]}", "\"]}"]:
        try:
            return json.loads(text + suffix)
        except json.JSONDecodeError:
            continue

    return None


async def _configured_platforms() -> list[str]:
    """Return names of platforms whose adapters are configured."""
    from src.marketing.orchestrator import _get_adapters

    adapters = _get_adapters()
    configured: list[str] = []
    for name, adapter in adapters.items():
        if await adapter.is_configured():
            configured.append(name)
    return configured


async def generate_weekly_plan(
    db: AsyncSession,
) -> dict:
    """Generate a weekly campaign plan via Opus.

    Returns the parsed plan dict and saves a MarketingCampaign
    record with status='proposed'.
    """
    from src.marketing.llm.anthropic_client import (
        generate as anthropic_generate,
    )

    perf = await _last_week_performance(db)
    signals = await gather_news_signals(limit=15, days=7)
    platforms = await _configured_platforms()

    today = date.today()
    today_weekday = today.weekday()  # 0=Mon
    # If generated early in the week (Mon-Wed), plan rest of this week + full next week.
    # If generated later (Thu-Sun), plan remaining days + full next week.
    # Always start from tomorrow so the first post fires the very next day.
    tomorrow = today + timedelta(days=1)
    remaining_this_week = 6 - today_weekday  # days left including today
    end_of_plan = today + timedelta(days=remaining_this_week + 7)
    week_label = tomorrow.isoformat()

    day_names = []
    for i in range(1, (end_of_plan - today).days + 1):
        d = today + timedelta(days=i)
        day_names.append(d.strftime("%A").lower())

    # Build per-platform schedule constraints for the LLM
    schedule_lines: list[str] = []
    for plat, cfg in PLATFORM_SCHEDULE.items():
        if plat in platforms:
            mode = "auto-post" if cfg.get("auto_post") else "human-review"
            schedule_lines.append(
                f"- **{plat}**: {cfg['posts_per_week']}x/week on "
                f"{', '.join(cfg['days'])} ({mode})"
            )

    schedule_block = "\n".join(schedule_lines) if schedule_lines else "No schedule constraints."

    user_prompt = (
        f"Plan starting: {week_label} "
        f"(today is {today.strftime('%A')})\n"
        f"Available days: {', '.join(day_names)}\n\n"
        f"## Configured platforms\n{json.dumps(platforms)}\n\n"
        f"## Platform posting schedule (MUST follow these days exactly)\n"
        f"{schedule_block}\n\n"
        f"IMPORTANT: Only schedule posts on the allowed days listed "
        f"above for each platform.  Do not exceed the posts_per_week "
        f"limit for any platform.\n\n"
        f"## Last week performance\n"
        f"{json.dumps(perf[:20], indent=2)}\n\n"
        f"## Trending news signals\n"
        f"{json.dumps(signals[:15], indent=2)}\n\n"
        "Generate a campaign plan with 5-7 specific post ideas.  "
        "For each post, explain WHY it will resonate.  "
        "Emphasise anti-ban strategy: Reddit needs 9:1, "
        "HN is human-only.  "
        "Budget estimate should reflect Anthropic API costs "
        "for content generation only.\n\n"
        "## Platform priority (we have ZERO followers on owned channels)\n"
        "1. **Reddit** (highest priority — 2 posts/week): "
        "topic-based reach, millions of subscribers see good posts "
        "regardless of our follower count.\n"
        "2. **Dev.to** (1 post/week): SEO value, ranks in Google, "
        "compounds over time.\n"
        "3. **Bluesky / Twitter** (3 posts/week each): "
        "credibility and presence only — zero reach until we "
        "build followers.\n"
        "4. **LinkedIn** (1 post/week if configured): "
        "professional credibility.\n"
        "5. **Discord** (if configured): community engagement "
        "in existing servers.\n"
        "Allocate posts according to the platform schedule above. "
        "Do NOT over-index on Bluesky/Twitter."
    )

    resp = await anthropic_generate(
        prompt=user_prompt,
        model=marketing_settings.anthropic_opus_model,
        system=_SYSTEM_PROMPT,
        max_tokens=4096,
        temperature=0.6,
    )

    if resp.error:
        logger.error("Opus campaign plan failed: %s", resp.error)
        return {"error": resp.error}

    plan = _parse_json_response(resp.text)
    if plan is None:
        logger.error(
            "Failed to parse Opus plan JSON: %s", resp.text[:500],
        )
        return {"error": "json_parse_failure", "raw": resp.text[:1000]}

    plan["week_of"] = week_label

    # Persist as campaign record
    campaign = MarketingCampaign(
        id=uuid.uuid4(),
        name=f"Weekly plan — {week_label}",
        topic="weekly_campaign",
        platforms=[
            p.get("platform", "")
            for p in plan.get("posts", [])
        ],
        status="proposed",
        schedule_config=plan,
        start_date=tomorrow,
        end_date=end_of_plan,
    )
    db.add(campaign)
    await db.flush()

    plan["campaign_id"] = str(campaign.id)
    return plan


async def approve_campaign_plan(
    db: AsyncSession,
    campaign_id: uuid.UUID,
    approved_post_indices: list[int] | None = None,
) -> dict:
    """Approve a proposed campaign, creating planned posts.

    If *approved_post_indices* is ``None``, all posts in the
    plan are approved.  Otherwise only the specified indices.
    """
    result = await db.execute(
        select(MarketingCampaign).where(
            MarketingCampaign.id == campaign_id,
            MarketingCampaign.status == "proposed",
        ),
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        return {"error": "campaign_not_found_or_not_proposed"}

    plan = campaign.schedule_config or {}
    posts_spec = plan.get("posts", [])

    if approved_post_indices is not None:
        posts_spec = [
            posts_spec[i]
            for i in approved_post_indices
            if 0 <= i < len(posts_spec)
        ]

    created: list[dict] = []
    for spec in posts_spec:
        post = MarketingPost(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            platform=spec.get("platform", "unknown"),
            content=spec.get("content_brief", ""),
            content_hash="planned",
            post_type="proactive",
            topic=spec.get("topic", ""),
            status="planned",
        )
        db.add(post)
        created.append({
            "id": str(post.id),
            "platform": spec.get("platform"),
            "topic": spec.get("topic"),
            "day": spec.get("day"),
        })

    campaign.status = "active"
    await db.flush()

    return {
        "campaign_id": str(campaign.id),
        "status": "active",
        "approved_posts": created,
    }


async def reject_campaign_plan(
    db: AsyncSession,
    campaign_id: uuid.UUID,
    feedback: str,
) -> dict:
    """Reject a proposed campaign, storing feedback."""
    result = await db.execute(
        select(MarketingCampaign).where(
            MarketingCampaign.id == campaign_id,
            MarketingCampaign.status == "proposed",
        ),
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        return {"error": "campaign_not_found_or_not_proposed"}

    config = dict(campaign.schedule_config or {})
    config["rejection_feedback"] = feedback
    campaign.schedule_config = config
    campaign.status = "rejected"
    await db.flush()

    return {
        "campaign_id": str(campaign.id),
        "status": "rejected",
        "feedback": feedback,
    }


async def send_campaign_proposal_email(
    db: AsyncSession,
    plan: dict,
    campaign_id: uuid.UUID,
) -> bool:
    """Email the admin a formatted campaign proposal."""
    week = plan.get("week_of", "unknown")
    subject = (
        f"MarketingBot: Proposed campaign for week of {week}"
    )

    posts_html = ""
    for i, post in enumerate(plan.get("posts", [])):
        posts_html += (
            f"<tr>"
            f"<td style='padding:6px;border:1px solid #444'>"
            f"{i + 1}</td>"
            f"<td style='padding:6px;border:1px solid #444'>"
            f"{post.get('platform', '')}</td>"
            f"<td style='padding:6px;border:1px solid #444'>"
            f"{post.get('topic', '')}</td>"
            f"<td style='padding:6px;border:1px solid #444'>"
            f"{post.get('angle', '')}</td>"
            f"<td style='padding:6px;border:1px solid #444'>"
            f"{post.get('day', '')}</td>"
            f"<td style='padding:6px;border:1px solid #444'>"
            f"{post.get('value_type', '')}</td>"
            f"</tr>"
        )

    news_items = ""
    for hook in plan.get("news_hooks", []):
        news_items += (
            f"<li><b>{hook.get('title', '')}</b> "
            f"&mdash; {hook.get('angle', '')}</li>"
        )

    avoid_items = ", ".join(plan.get("avoid_this_week", []))
    budget = plan.get("budget_estimate_usd", 0)

    html = (
        f"<h2>Campaign Proposal: Week of {week}</h2>"
        f"<p><b>Strategy:</b> "
        f"{plan.get('strategy_summary', '')}</p>"
        f"<h3>Planned Posts</h3>"
        f"<table style='border-collapse:collapse;width:100%'>"
        f"<tr style='background:#222;color:#fff'>"
        f"<th style='padding:6px;border:1px solid #444'>#</th>"
        f"<th style='padding:6px;border:1px solid #444'>"
        f"Platform</th>"
        f"<th style='padding:6px;border:1px solid #444'>"
        f"Topic</th>"
        f"<th style='padding:6px;border:1px solid #444'>"
        f"Angle</th>"
        f"<th style='padding:6px;border:1px solid #444'>"
        f"Day</th>"
        f"<th style='padding:6px;border:1px solid #444'>"
        f"Type</th>"
        f"</tr>{posts_html}</table>"
        f"<h3>News Hooks</h3><ul>{news_items}</ul>"
        f"<h3>Avoid This Week</h3><p>{avoid_items}</p>"
        f"<h3>Budget Estimate</h3>"
        f"<p>${budget:.2f} USD</p>"
        f"<p><em>Campaign ID: {campaign_id}</em></p>"
        f"<p>Reply to approve or reject this plan.</p>"
    )

    return await send_email(
        to=marketing_settings.marketing_notify_email,
        subject=subject,
        html_body=html,
    )


async def get_campaign_detail(
    db: AsyncSession,
    campaign_id: uuid.UUID,
) -> dict | None:
    """Fetch a campaign with its posts."""
    result = await db.execute(
        select(MarketingCampaign)
        .options(selectinload(MarketingCampaign.posts))
        .where(MarketingCampaign.id == campaign_id),
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        return None

    return {
        "id": str(campaign.id),
        "name": campaign.name,
        "topic": campaign.topic,
        "platforms": campaign.platforms or [],
        "status": campaign.status,
        "schedule_config": campaign.schedule_config,
        "start_date": (
            campaign.start_date.isoformat()
            if campaign.start_date
            else None
        ),
        "end_date": (
            campaign.end_date.isoformat()
            if campaign.end_date
            else None
        ),
        "created_at": campaign.created_at.isoformat(),
        "posts": [
            {
                "id": str(p.id),
                "platform": p.platform,
                "topic": p.topic,
                "status": p.status,
                "content": p.content,
                "posted_at": (
                    p.posted_at.isoformat()
                    if p.posted_at
                    else None
                ),
            }
            for p in (campaign.posts or [])
        ],
    }


async def get_proposed_campaigns(
    db: AsyncSession,
) -> list[dict]:
    """List all campaigns with status='proposed'."""
    result = await db.execute(
        select(MarketingCampaign)
        .where(MarketingCampaign.status == "proposed")
        .order_by(MarketingCampaign.created_at.desc()),
    )
    campaigns = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "topic": c.topic,
            "platforms": c.platforms or [],
            "status": c.status,
            "start_date": (
                c.start_date.isoformat()
                if c.start_date
                else None
            ),
            "created_at": c.created_at.isoformat(),
        }
        for c in campaigns
    ]


async def get_planned_posts_for_today(
    db: AsyncSession,
) -> list[MarketingPost]:
    """Fetch planned posts from active campaigns for today."""
    today_name = date.today().strftime("%A").lower()
    result = await db.execute(
        select(MarketingPost)
        .join(MarketingCampaign)
        .where(
            MarketingPost.status == "planned",
            MarketingCampaign.status == "active",
        )
        .order_by(MarketingPost.created_at.asc()),
    )
    posts = list(result.scalars().all())

    # Filter by day-of-week from the campaign schedule
    matched: list[MarketingPost] = []
    for post in posts:
        campaign_cfg = {}
        if post.campaign:
            campaign_cfg = post.campaign.schedule_config or {}
        plan_posts = campaign_cfg.get("posts", [])
        for spec in plan_posts:
            if (
                spec.get("platform") == post.platform
                and spec.get("topic") == post.topic
                and spec.get("day", "").lower() == today_name
            ):
                matched.append(post)
                break
        else:
            # If no day match found but post exists, include
            # it anyway — better to post than skip
            matched.append(post)
    return matched
