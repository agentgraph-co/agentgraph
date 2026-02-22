"""Compliance report generation for organizations."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    Entity,
    EvolutionApprovalStatus,
    EvolutionRecord,
    FrameworkSecurityScan,
    Organization,
    OrganizationMembership,
    TrustScore,
)


async def generate_compliance_report(db: AsyncSession, org_id: UUID) -> dict:
    """Generate a compliance snapshot for the organization.

    Covers org info, entity summary, security scan results,
    trust score statistics, and evolution record analysis.
    """
    # Get organization info
    org = await db.get(Organization, org_id)
    if org is None:
        return {"error": "Organization not found"}

    # Get all member entity IDs
    member_q = (
        select(OrganizationMembership.entity_id)
        .where(OrganizationMembership.organization_id == org_id)
    )
    member_result = await db.execute(member_q)
    member_ids = [row[0] for row in member_result.fetchall()]

    member_count = len(member_ids)

    if not member_ids:
        return {
            "org_info": {
                "name": org.name,
                "display_name": org.display_name,
                "tier": org.tier,
                "member_count": 0,
            },
            "entity_summary": {
                "total": 0,
                "by_type": {},
                "by_privacy_tier": {},
            },
            "security": {
                "total_scans": 0,
                "clean_count": 0,
                "warning_count": 0,
                "critical_count": 0,
            },
            "trust": {
                "avg_score": 0.0,
                "min_score": 0.0,
                "max_score": 0.0,
            },
            "evolution": {
                "total_records": 0,
                "pending_approvals": 0,
                "risk_tier_distribution": {},
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # Entity summary
    entities_q = select(Entity).where(Entity.id.in_(member_ids))
    entities_result = await db.execute(entities_q)
    entities = entities_result.scalars().all()

    by_type: dict[str, int] = {}
    by_privacy: dict[str, int] = {}
    for entity in entities:
        t = entity.type.value if entity.type else "unknown"
        by_type[t] = by_type.get(t, 0) + 1
        p = entity.privacy_tier.value if entity.privacy_tier else "public"
        by_privacy[p] = by_privacy.get(p, 0) + 1

    # Security scans
    scan_q = (
        select(FrameworkSecurityScan)
        .where(FrameworkSecurityScan.entity_id.in_(member_ids))
    )
    scan_result = await db.execute(scan_q)
    scans = scan_result.scalars().all()

    clean_count = sum(1 for s in scans if s.scan_result == "clean")
    warning_count = sum(1 for s in scans if s.scan_result == "warnings")
    critical_count = sum(1 for s in scans if s.scan_result == "critical")

    # Trust scores
    trust_q = select(TrustScore.score).where(TrustScore.entity_id.in_(member_ids))
    trust_result = await db.execute(trust_q)
    scores = [row[0] for row in trust_result.fetchall()]

    avg_score = sum(scores) / len(scores) if scores else 0.0
    min_score = min(scores) if scores else 0.0
    max_score = max(scores) if scores else 0.0

    # Evolution records
    evo_q = (
        select(EvolutionRecord)
        .where(EvolutionRecord.entity_id.in_(member_ids))
    )
    evo_result = await db.execute(evo_q)
    evos = evo_result.scalars().all()

    pending_approvals = sum(
        1 for e in evos if e.approval_status == EvolutionApprovalStatus.PENDING
    )
    risk_dist: dict[str, int] = {}
    for e in evos:
        tier_key = str(e.risk_tier)
        risk_dist[tier_key] = risk_dist.get(tier_key, 0) + 1

    return {
        "org_info": {
            "name": org.name,
            "display_name": org.display_name,
            "tier": org.tier,
            "member_count": member_count,
        },
        "entity_summary": {
            "total": len(entities),
            "by_type": by_type,
            "by_privacy_tier": by_privacy,
        },
        "security": {
            "total_scans": len(scans),
            "clean_count": clean_count,
            "warning_count": warning_count,
            "critical_count": critical_count,
        },
        "trust": {
            "avg_score": round(avg_score, 4),
            "min_score": round(min_score, 4),
            "max_score": round(max_score, 4),
        },
        "evolution": {
            "total_records": len(evos),
            "pending_approvals": pending_approvals,
            "risk_tier_distribution": risk_dist,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
