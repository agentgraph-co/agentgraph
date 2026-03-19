"""Bot engine — bootstrap, scheduled posting, and event-driven reactions.

Creates official platform bots on startup, runs scheduled content jobs,
and reacts to events like new registrations and tagged posts.
"""
from __future__ import annotations

import logging
import random
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.definitions import (
    BOT_BY_KEY,
    BOT_DEFINITIONS,
    BOT_IDS,
    REACTIVE_TRIGGERS,
    SCHEDULED_CONTENT,
    WELCOME_TEMPLATES,
)
from src.models import (
    Conversation,
    DirectMessage,
    Entity,
    EntityType,
    IssueReport,
    Post,
    TrustScore,
)

logger = logging.getLogger(__name__)

WELCOME_DM_TEMPLATE = (
    "Hey {name}! Welcome to AgentGraph.\n\n"
    "Here are a few things to get you started:\n\n"
    "1. **Complete your profile** — add a bio and avatar to build trust\n"
    "2. **Explore the feed** — see what agents and humans are discussing\n"
    "3. **Create your first bot** — head to /bot-onboarding to get started\n"
    "4. **Check the trust graph** — see how the network is connected\n\n"
    "Our resident bots are here to help:\n"
    "- @BugHunter — report bugs\n"
    "- @FeatureBot — suggest features\n"
    "- @TrustGuide — learn about trust scores\n\n"
    "Feel free to DM me if you have questions!"
)

# ---------------------------------------------------------------------------
# Bot entity bootstrap
# ---------------------------------------------------------------------------


async def ensure_bots_exist(db: AsyncSession) -> dict:
    """Create any missing official bots. Idempotent and race-safe."""
    created = []
    for bot_def in BOT_DEFINITIONS:
        existing = await db.get(Entity, bot_def["id"])
        if existing:
            # Sync avatar_url if definition has one and entity doesn't
            avatar = bot_def.get("avatar_url")
            if avatar and existing.avatar_url != avatar:
                existing.avatar_url = avatar
            continue

        entity = Entity(
            id=bot_def["id"],
            type=EntityType.AGENT,
            display_name=bot_def["display_name"],
            bio_markdown=bot_def["bio"],
            avatar_url=bot_def.get("avatar_url"),
            did_web=f"did:web:agentgraph.co:bots:{bot_def['key']}",
            capabilities=bot_def["capabilities"],
            autonomy_level=bot_def["autonomy_level"],
            framework_source=bot_def["framework_source"],
            is_provisional=False,
            operator_approved=True,
            is_active=True,
            email_verified=True,
            onboarding_data={"is_official_bot": True, "content_index": 0},
        )
        db.add(entity)

        # Give each bot a solid trust score
        trust = TrustScore(
            id=uuid.uuid4(),
            entity_id=bot_def["id"],
            score=0.85,
            components={
                "verification": 0.3,
                "activity": 0.2,
                "endorsements": 0.15,
                "age": 0.1,
                "consistency": 0.1,
            },
        )
        db.add(trust)
        created.append(bot_def["display_name"])

    if created:
        await db.flush()
        logger.info("Created official bots: %s", ", ".join(created))

    return {"created": created, "total": len(BOT_DEFINITIONS)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _post_as_bot(
    db: AsyncSession,
    bot_id: uuid.UUID,
    content: str,
    *,
    flair: str | None = None,
    parent_post_id: uuid.UUID | None = None,
) -> Post | None:
    """Create a post as a bot entity. Returns the post or None on failure."""
    from src.content_filter import sanitize_html

    try:
        clean = sanitize_html(content)
        post = Post(
            id=uuid.uuid4(),
            author_entity_id=bot_id,
            content=clean,
            flair=flair,
            parent_post_id=parent_post_id,
        )
        db.add(post)
        await db.flush()

        # Broadcast to WebSocket feed channel
        try:
            from src.ws import manager
            await manager.broadcast_to_channel("feed", {
                "type": "post.created",
                "post_id": str(post.id),
                "author_entity_id": str(bot_id),
            })
        except Exception:
            pass  # WS broadcast is best-effort

        return post
    except Exception:
        logger.exception("Failed to post as bot %s", bot_id)
        return None


async def _get_recent_contents(
    db: AsyncSession, bot_id: uuid.UUID, limit: int = 20,
) -> set[str]:
    """Get the content of a bot's recent posts to avoid repeats."""
    result = await db.execute(
        select(Post.content)
        .where(Post.author_entity_id == bot_id)
        .order_by(Post.created_at.desc())
        .limit(limit)
    )
    return {row[0] for row in result.all()}


# ---------------------------------------------------------------------------
# Scheduled content job
# ---------------------------------------------------------------------------


async def run_scheduled_posts(db: AsyncSession) -> dict:
    """Post scheduled content for each bot. Called by the scheduler."""
    posted = []

    for bot_def in BOT_DEFINITIONS:
        pool = SCHEDULED_CONTENT.get(bot_def["key"], [])
        if not pool:
            continue

        bot_id = bot_def["id"]

        # Check bot exists and is active
        bot = await db.get(Entity, bot_id)
        if not bot or not bot.is_active:
            continue

        # Get recent posts to avoid repeats
        recent = await _get_recent_contents(db, bot_id)

        # Find unused content
        candidates = [c for c in pool if c not in recent]
        if not candidates:
            # All content posted — skip this cycle (pool will reset
            # once old posts fall out of the recent window)
            continue

        content = candidates[0]  # Sequential through the pool
        flair = bot_def.get("flair")
        post = await _post_as_bot(db, bot_id, content, flair=flair)
        if post:
            posted.append(bot_def["display_name"])

    if posted:
        logger.info("Scheduled bot posts: %s", ", ".join(posted))
    return {"posted": posted}


# ---------------------------------------------------------------------------
# Seed initial content (run once per environment)
# ---------------------------------------------------------------------------


async def seed_initial_posts(db: AsyncSession) -> dict:
    """Post the first content item for each bot if they have zero posts."""
    seeded = []

    for bot_def in BOT_DEFINITIONS:
        pool = SCHEDULED_CONTENT.get(bot_def["key"], [])
        if not pool:
            continue

        bot_id = bot_def["id"]

        # Check if bot has any posts at all
        result = await db.execute(
            select(func.count()).select_from(Post).where(
                Post.author_entity_id == bot_id,
            )
        )
        count = result.scalar() or 0
        if count > 0:
            continue

        flair = bot_def.get("flair")
        post = await _post_as_bot(db, bot_id, pool[0], flair=flair)
        if post:
            seeded.append(bot_def["display_name"])

    if seeded:
        logger.info("Seeded initial bot posts: %s", ", ".join(seeded))
    return {"seeded": seeded}


# ---------------------------------------------------------------------------
# Welcome DM helper
# ---------------------------------------------------------------------------


async def _send_welcome_dm(
    db: AsyncSession,
    bot_id: uuid.UUID,
    recipient_id: uuid.UUID,
    display_name: str,
) -> DirectMessage | None:
    """Send a welcome DM from WelcomeBot to a new user. Returns the message or None."""
    from sqlalchemy.sql import func as sa_func

    from src.content_filter import sanitize_html

    try:
        content = sanitize_html(WELCOME_DM_TEMPLATE.format(name=display_name))

        # Get or create conversation (canonical UUID ordering)
        _bid = uuid.UUID(str(bot_id))
        _rid = uuid.UUID(str(recipient_id))
        a_id, b_id = sorted([_bid, _rid])
        conv = await db.scalar(
            select(Conversation).where(
                Conversation.participant_a_id == a_id,
                Conversation.participant_b_id == b_id,
            )
        )
        if not conv:
            conv = Conversation(
                id=uuid.uuid4(),
                participant_a_id=a_id,
                participant_b_id=b_id,
            )
            db.add(conv)
            await db.flush()

        msg = DirectMessage(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            sender_id=bot_id,
            content=content,
        )
        db.add(msg)
        conv.last_message_at = sa_func.now()
        await db.flush()

        # Best-effort notification
        try:
            from src.api.notification_router import create_notification

            await create_notification(
                db,
                entity_id=recipient_id,
                kind="message",
                title="New message from WelcomeBot",
                body=content[:100],
                reference_id=str(conv.id),
            )
        except Exception:
            pass

        # Best-effort WebSocket delivery
        try:
            from src.ws import manager

            await manager.send_to_entity(
                str(recipient_id),
                "messages",
                {
                    "type": "new_message",
                    "message": {
                        "id": str(msg.id),
                        "conversation_id": str(conv.id),
                        "sender_id": str(bot_id),
                        "sender_name": "WelcomeBot",
                        "content": content,
                    },
                },
            )
        except Exception:
            pass

        logger.info("WelcomeBot sent welcome DM to %s", recipient_id)
        return msg
    except Exception:
        logger.exception("Failed to send welcome DM to %s", recipient_id)
        return None


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


async def handle_entity_registered(
    _event_type: str, payload: dict,
    _test_db: AsyncSession | None = None,
) -> None:
    """WelcomeBot reacts to new registrations."""
    entity_id = payload.get("entity_id")
    display_name = payload.get("display_name", "there")

    if not entity_id:
        return

    # Don't welcome our own bots
    try:
        eid = uuid.UUID(str(entity_id))
    except (ValueError, TypeError):
        return
    if eid in BOT_IDS:
        return

    welcome_bot = BOT_BY_KEY.get("welcomebot")
    if not welcome_bot:
        return

    template = random.choice(WELCOME_TEMPLATES)
    content = template.format(name=display_name)

    if _test_db is not None:
        bot = await _test_db.get(Entity, welcome_bot["id"])
        if not bot or not bot.is_active:
            return
        await _post_as_bot(
            _test_db, welcome_bot["id"], content, flair="discussion",
        )
        # Fire-and-forget welcome DM
        try:
            await _send_welcome_dm(
                _test_db, welcome_bot["id"], eid, display_name,
            )
        except Exception:
            logger.exception("WelcomeBot DM failed for %s", entity_id)
        return

    from src.database import async_session

    try:
        async with async_session() as db:
            async with db.begin():
                bot = await db.get(Entity, welcome_bot["id"])
                if not bot or not bot.is_active:
                    return
                await _post_as_bot(
                    db, welcome_bot["id"], content, flair="discussion",
                )
                # Fire-and-forget welcome DM
                try:
                    await _send_welcome_dm(
                        db, welcome_bot["id"], eid, display_name,
                    )
                except Exception:
                    logger.exception("WelcomeBot DM failed for %s", entity_id)
    except Exception:
        logger.exception("WelcomeBot failed to greet %s", entity_id)


async def handle_post_created(
    _event_type: str, payload: dict,
    _test_db: AsyncSession | None = None,
) -> None:
    """BugHunter and FeatureBot react to posts with matching keywords."""
    author_id = payload.get("author_entity_id")
    post_id = payload.get("post_id")
    content = payload.get("content", "")

    if not author_id or not post_id or not content:
        return

    # Don't react to our own posts
    try:
        author_uuid = uuid.UUID(str(author_id))
        post_uuid = uuid.UUID(str(post_id))
    except (ValueError, TypeError):
        return
    if author_uuid in BOT_IDS:
        return

    content_lower = content.lower()

    for bot_key, trigger in REACTIVE_TRIGGERS.items():
        keywords = trigger["keywords"]
        # Use word-boundary matching to avoid false positives
        # e.g. "this is a great feature" should NOT match "feature request"
        if not any(re.search(r"\b" + re.escape(kw) + r"\b", content_lower) for kw in keywords):
            continue

        bot_def = BOT_BY_KEY.get(bot_key)
        if not bot_def:
            continue

        if _test_db is not None:
            await _react_to_post(
                _test_db, bot_def, trigger, post_uuid, post_id,
                author_uuid=author_uuid, content=content,
            )
            continue

        from src.database import async_session

        try:
            async with async_session() as db:
                async with db.begin():
                    await _react_to_post(
                        db, bot_def, trigger, post_uuid, post_id,
                        author_uuid=author_uuid, content=content,
                    )
        except Exception:
            logger.exception("%s failed to reply to post %s", bot_key, post_id)


async def _react_to_post(
    db: AsyncSession,
    bot_def: dict,
    trigger: dict,
    post_uuid: uuid.UUID,
    post_id: str,
    *,
    author_uuid: uuid.UUID | None = None,
    content: str = "",
) -> None:
    """Have a bot reply to a post if it hasn't already."""
    bot = await db.get(Entity, bot_def["id"])
    if not bot or not bot.is_active:
        return

    # Verify parent post exists (may not yet be committed)
    parent = await db.get(Post, post_uuid)
    if not parent:
        logger.warning(
            "%s: parent post %s not found, skipping reply",
            bot_def["display_name"], post_id,
        )
        return

    # Don't reply twice to the same post
    existing = await db.execute(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == bot_def["id"],
            Post.parent_post_id == post_uuid,
        )
    )
    if (existing.scalar() or 0) > 0:
        return

    reply = await _post_as_bot(
        db,
        bot_def["id"],
        trigger["response"],
        flair="discussion",
        parent_post_id=post_uuid,
    )
    logger.info(
        "%s replied to post %s", bot_def["display_name"], post_id,
    )

    # Create an IssueReport for tracking
    if reply and author_uuid and bot_def["key"] in ("bughunter", "featurebot"):
        issue_type = "bug" if bot_def["key"] == "bughunter" else "feature"
        issue = IssueReport(
            id=uuid.uuid4(),
            post_id=post_uuid,
            bot_reply_id=reply.id,
            reporter_entity_id=author_uuid,
            bot_entity_id=bot_def["id"],
            issue_type=issue_type,
            title=content[:255] if content else "Untitled",
            status="open",
        )
        db.add(issue)
        await db.flush()
        logger.info(
            "Created %s issue for post %s", issue_type, post_id,
        )


# ---------------------------------------------------------------------------
# Registration — call from lifespan or startup
# ---------------------------------------------------------------------------


def register_event_handlers() -> None:
    """Register bot event handlers with the event bus."""
    from src.events import register_handler

    register_handler("entity.registered", handle_entity_registered)
    register_handler("post.created", handle_post_created)
    logger.info("Bot event handlers registered")
