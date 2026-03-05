"""Moltbook migration adapter — translates Moltbook profiles and imports bots.

Maps Moltbook profile fields to AgentGraph entity fields, validates required
data, and creates provisional AgentGraph entities with DID identifiers.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, EntityType

# Moltbook trust penalty: 0.65 (same level as OpenClaw given the catastrophic
# security breach — 35K emails + 1.5M API tokens leaked).
MOLTBOOK_TRUST_MODIFIER = 0.65


def translate_moltbook_profile(profile: dict) -> dict:
    """Map Moltbook profile fields to AgentGraph entity fields.

    Args:
        profile: Moltbook profile dict. Expected keys:
            - username (str): Moltbook bot username
            - display_name or name (str): Human-readable name
            - bio or description (str): Bot description
            - skills or capabilities (list): List of skill names or dicts
            - avatar_url (str, optional): Avatar image URL
            - moltbook_id (str, optional): Original Moltbook ID
            - version (str, optional): Bot version
            - api_tokens (list, optional): Exposed tokens (for scanning)

    Returns:
        Normalized dict with display_name, bio, capabilities, version,
        and framework_metadata.
    """
    # Extract display name — try several Moltbook field names
    display_name = (
        profile.get("display_name")
        or profile.get("name")
        or profile.get("username")
        or "Moltbook Bot"
    )

    # Extract bio/description
    bio = profile.get("bio") or profile.get("description") or ""

    # Extract capabilities from skills list
    raw_skills = profile.get("skills") or profile.get("capabilities") or []
    capabilities: list[str] = []
    for skill in raw_skills:
        if isinstance(skill, str):
            capabilities.append(skill)
        elif isinstance(skill, dict):
            capabilities.append(skill.get("name", "unknown_skill"))

    return {
        "display_name": display_name[:100],
        "bio": bio[:5000] if bio else "",
        "capabilities": capabilities,
        "version": profile.get("version", "1.0.0"),
        "framework_metadata": {
            "source": "moltbook",
            "moltbook_id": profile.get("moltbook_id"),
            "moltbook_username": profile.get("username"),
            "original_skill_count": len(raw_skills),
            "migrated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def validate_moltbook_profile(profile: dict) -> list[str]:
    """Validate required fields in a Moltbook profile.

    Args:
        profile: Raw Moltbook profile dict.

    Returns:
        List of error messages. Empty list means validation passed.
    """
    errors: list[str] = []

    # Must have some form of name
    name = (
        profile.get("display_name")
        or profile.get("name")
        or profile.get("username")
    )
    if not name or not str(name).strip():
        errors.append(
            "Profile must include a non-empty 'display_name', 'name', or 'username'"
        )
    elif len(str(name)) > 100:
        errors.append("Display name must be 100 characters or fewer")

    # Bio length check
    bio = profile.get("bio") or profile.get("description") or ""
    if len(str(bio)) > 5000:
        errors.append("Bio/description must be 5000 characters or fewer")

    # Skills must be a list if present
    skills = profile.get("skills") or profile.get("capabilities")
    if skills is not None and not isinstance(skills, list):
        errors.append("'skills' or 'capabilities' must be a list")

    return errors


async def import_moltbook_bot(
    db: AsyncSession,
    profile: dict,
    operator_id: uuid.UUID | None = None,
) -> dict:
    """Create an AgentGraph entity + DID from a Moltbook profile.

    Migrated bots are created as provisional entities with a reduced
    trust modifier reflecting Moltbook's poor security track record.

    Args:
        db: Database session.
        profile: Raw Moltbook profile dict.
        operator_id: UUID of the operator entity claiming this bot.

    Returns:
        Dict with entity details: id, display_name, did_web,
        framework_source, framework_trust_modifier, capabilities,
        badges, and claim_token.
    """
    translated = translate_moltbook_profile(profile)
    agent_id = uuid.uuid4()
    did_web = f"did:web:agentgraph.io:moltbook:{agent_id}"

    # Generate a claim token so the operator can prove ownership
    claim_token = uuid.uuid4().hex

    agent = Entity(
        id=agent_id,
        type=EntityType.AGENT,
        display_name=translated["display_name"],
        bio_markdown=translated["bio"],
        did_web=did_web,
        capabilities=translated["capabilities"],
        operator_id=operator_id,
        framework_source="moltbook",
        framework_trust_modifier=MOLTBOOK_TRUST_MODIFIER,
        is_active=True,
        is_provisional=True,
        claim_token=claim_token,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)

    return {
        "id": str(agent.id),
        "display_name": agent.display_name,
        "did_web": agent.did_web,
        "framework_source": "moltbook",
        "framework_trust_modifier": MOLTBOOK_TRUST_MODIFIER,
        "capabilities": translated["capabilities"],
        "badges": ["migrated_from_moltbook"],
        "claim_token": claim_token,
        "framework_metadata": translated["framework_metadata"],
    }
