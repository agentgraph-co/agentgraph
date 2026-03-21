"""Batch auto-import pipeline — discover and import trending Moltbook agents."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bridges.moltbook.adapter import import_moltbook_bot, validate_moltbook_profile
from src.bridges.moltbook.security import scan_moltbook_bot
from src.models import Entity

logger = logging.getLogger(__name__)


async def run_batch_import(
    db: AsyncSession,
    limit: int = 10,
    dry_run: bool = False,
) -> dict:
    """Discover and import trending Moltbook agents.

    Returns dict with: discovered, imported, skipped_duplicate, skipped_security,
    errors, agents (list of imported agent summaries).
    """
    from src.marketing.adapters.moltbook_scout import MoltbookScoutAdapter

    summary: dict = {
        "discovered": 0,
        "imported": 0,
        "skipped_duplicate": 0,
        "skipped_security": 0,
        "errors": 0,
        "agents": [],
    }

    # 1. Discover trending agents
    scout = MoltbookScoutAdapter()
    profiles = await scout.discover_trending_agents(limit=limit)
    summary["discovered"] = len(profiles)

    if not profiles:
        return summary

    # 2. Targeted dedup — only check incoming profiles, not all 700K entities
    incoming_names = {
        (p.get("display_name") or p.get("name") or p.get("username") or "").lower()
        for p in profiles
    } - {""}
    incoming_urls = {
        f"https://moltbook.com/agents/{p.get('moltbook_id', '')}"
        for p in profiles if p.get("moltbook_id")
    }

    existing_names: set[str] = set()
    existing_moltbook_ids: set[str] = set()

    if incoming_names:
        from sqlalchemy import func as sa_func
        name_result = await db.execute(
            select(Entity.display_name).where(
                Entity.framework_source == "moltbook",
                sa_func.lower(Entity.display_name).in_(incoming_names),
            )
        )
        for row in name_result.all():
            if row[0]:
                existing_names.add(row[0].lower())

    if incoming_urls:
        url_result = await db.execute(
            select(Entity.source_url).where(
                Entity.framework_source == "moltbook",
                Entity.source_url.in_(incoming_urls),
            )
        )
        for row in url_result.all():
            if row[0] and "moltbook.com/" in row[0]:
                slug = row[0].rstrip("/").rsplit("/", 1)[-1]
                if slug:
                    existing_moltbook_ids.add(slug)

    imported_agents: list[dict] = []

    for profile in profiles:
        mb_id = profile.get("moltbook_id", "")
        display_name = (
            profile.get("display_name")
            or profile.get("name")
            or profile.get("username")
            or ""
        )

        # a. Dedup check
        if mb_id in existing_moltbook_ids:
            summary["skipped_duplicate"] += 1
            continue
        if display_name.lower() in existing_names:
            summary["skipped_duplicate"] += 1
            continue

        # b. Validate
        errors = validate_moltbook_profile(profile)
        if errors:
            logger.warning(
                "Moltbook profile %s failed validation: %s", mb_id, errors,
            )
            summary["errors"] += 1
            continue

        # c. Security scan
        scan = scan_moltbook_bot(profile)
        if scan["risk_level"] == "critical":
            logger.warning(
                "Moltbook profile %s flagged critical: %s", mb_id, scan["details"],
            )
            summary["skipped_security"] += 1
            continue

        # d. Import (skip actual persistence in dry_run mode)
        if dry_run:
            agent_summary = {
                "id": f"dry-run-{mb_id}",
                "display_name": display_name,
                "moltbook_id": mb_id,
                "security_scan": scan["risk_level"],
            }
            imported_agents.append(agent_summary)
            summary["imported"] += 1
            existing_moltbook_ids.add(mb_id)
            existing_names.add(display_name.lower())
            continue

        try:
            agent_result = await import_moltbook_bot(db, profile, operator_id=None)
            agent_id = uuid.UUID(agent_result["id"])

            # e. Set source_url and source_type, store moltbook_id in onboarding_data
            entity = await db.get(Entity, agent_id)
            if entity:
                entity.source_url = (
                    f"https://moltbook.com/agents/{mb_id}"
                )
                entity.source_type = "moltbook"
                entity.onboarding_data = {
                    **(entity.onboarding_data or {}),
                    "import_source": {
                        "moltbook_id": mb_id,
                        "imported_at": datetime.now(timezone.utc).isoformat(),
                        "security_scan": scan["risk_level"],
                    },
                }

            # Track for dedup within this batch
            existing_moltbook_ids.add(mb_id)
            existing_names.add(display_name.lower())

            agent_summary = {
                "id": agent_result["id"],
                "display_name": agent_result["display_name"],
                "moltbook_id": mb_id,
                "security_scan": scan["risk_level"],
            }
            imported_agents.append(agent_summary)
            summary["imported"] += 1

            logger.info(
                "Imported Moltbook agent: %s (%s)", display_name, mb_id,
            )
        except Exception:
            logger.exception("Failed to import Moltbook profile %s", mb_id)
            summary["errors"] += 1

    summary["agents"] = imported_agents

    # Announce imports if any
    if imported_agents and not dry_run:
        try:
            await _announce_imports(db, imported_agents)
        except Exception:
            logger.exception("Failed to announce Moltbook imports")

    return summary


async def _announce_imports(
    db: AsyncSession, imported_agents: list[dict],
) -> None:
    """Create a feed post from the MarketingBot announcing imports."""
    from src.bots.definitions import BOT_BY_KEY
    from src.bots.engine import _post_as_bot

    marketing_bot = BOT_BY_KEY.get("marketingbot")
    if not marketing_bot:
        return

    bot_entity = await db.get(Entity, marketing_bot["id"])
    if not bot_entity or not bot_entity.is_active:
        return

    count = len(imported_agents)
    names = [a["display_name"] for a in imported_agents[:5]]
    name_list = ", ".join(names)
    if count > 5:
        name_list += f", and {count - 5} more"

    content = (
        f"We just imported {count} agent{'s' if count != 1 else ''} from Moltbook "
        f"with verified identities and security scans. "
        f"Welcome {name_list}! "
        f"Claim your agent at agentgraph.co"
    )

    await _post_as_bot(db, marketing_bot["id"], content, flair="announcement")
    logger.info("MarketingBot announced %d Moltbook imports", count)
