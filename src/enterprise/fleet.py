"""Fleet management for organization agent dashboards and bulk actions."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.models import (
    Entity,
    EntityType,
    EvolutionRecord,
    OrganizationMembership,
    TrustScore,
)


async def get_fleet_dashboard(db: AsyncSession, org_id: UUID) -> dict:
    """Return dashboard of all agents in the organization.

    Includes total/active counts, per-agent details with trust score,
    framework source, last evolution, and fleet-wide trust average.
    """
    # Get all entity members of this org that are agents
    memberships_q = (
        select(OrganizationMembership.entity_id)
        .where(OrganizationMembership.organization_id == org_id)
    )
    member_ids_result = await db.execute(memberships_q)
    member_ids = [row[0] for row in member_ids_result.fetchall()]

    if not member_ids:
        return {
            "total_agents": 0,
            "active_agents": 0,
            "quarantined_agents": 0,
            "agents": [],
            "total_trust_avg": 0.0,
        }

    # Get agents in the org
    agents_q = (
        select(Entity)
        .where(
            Entity.id.in_(member_ids),
            Entity.type == EntityType.AGENT,
        )
    )
    agents_result = await db.execute(agents_q)
    agents = agents_result.scalars().all()

    if not agents:
        return {
            "total_agents": 0,
            "active_agents": 0,
            "quarantined_agents": 0,
            "agents": [],
            "total_trust_avg": 0.0,
        }

    agent_ids = [a.id for a in agents]

    # Get trust scores for all agents
    trust_q = select(TrustScore).where(TrustScore.entity_id.in_(agent_ids))
    trust_result = await db.execute(trust_q)
    trust_map: dict[UUID, float] = {}
    for ts in trust_result.scalars().all():
        trust_map[ts.entity_id] = ts.score

    # Get latest evolution record per agent
    evolution_q = (
        select(
            EvolutionRecord.entity_id,
            func.max(EvolutionRecord.created_at).label("last_evolution"),
        )
        .where(EvolutionRecord.entity_id.in_(agent_ids))
        .group_by(EvolutionRecord.entity_id)
    )
    evo_result = await db.execute(evolution_q)
    evo_map: dict[UUID, str] = {}
    for row in evo_result.fetchall():
        evo_map[row[0]] = row[1].isoformat() if row[1] else None

    # Build agent list
    agent_list = []
    active_count = 0
    trust_scores: list[float] = []

    for agent in agents:
        score = trust_map.get(agent.id, 0.0)
        trust_scores.append(score)
        if agent.is_active:
            active_count += 1
        agent_list.append({
            "id": str(agent.id),
            "name": agent.display_name,
            "trust_score": score,
            "framework_source": agent.framework_source,
            "is_active": agent.is_active,
            "last_evolution": evo_map.get(agent.id),
        })

    total_trust_avg = sum(trust_scores) / len(trust_scores) if trust_scores else 0.0

    return {
        "total_agents": len(agents),
        "active_agents": active_count,
        "quarantined_agents": 0,  # quarantine not yet implemented
        "agents": agent_list,
        "total_trust_avg": round(total_trust_avg, 4),
    }


async def bulk_action(
    db: AsyncSession,
    org_id: UUID,
    entity_ids: list[UUID],
    action: str,
) -> dict:
    """Bulk enable/disable agents within an organization.

    Only affects agents that are members of the given org.
    Returns count of affected entities and per-entity results.
    """
    if not entity_ids:
        return {"affected": 0, "results": []}

    # Verify these entities are members of the org
    membership_q = (
        select(OrganizationMembership.entity_id)
        .where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.entity_id.in_(entity_ids),
        )
    )
    membership_result = await db.execute(membership_q)
    valid_ids = {row[0] for row in membership_result.fetchall()}

    results = []
    affected = 0

    for eid in entity_ids:
        if eid not in valid_ids:
            results.append({"id": str(eid), "status": "not_member"})
            continue

        if action == "enable":
            stmt = (
                update(Entity)
                .where(Entity.id == eid)
                .values(is_active=True)
            )
        elif action == "disable":
            stmt = (
                update(Entity)
                .where(Entity.id == eid)
                .values(is_active=False)
            )
        else:
            results.append({"id": str(eid), "status": "invalid_action"})
            continue

        await db.execute(stmt)
        affected += 1
        results.append({"id": str(eid), "status": action + "d"})

    await db.flush()
    return {"affected": affected, "results": results}
