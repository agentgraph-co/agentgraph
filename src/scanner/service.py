"""Security scan service — runs scans and stores results.

Bridges the standalone mcp-security-scan engine with the AgentGraph
database. Used by bot onboarding, re-scan triggers, and the scheduler.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, outerjoin, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models import Entity, FrameworkSecurityScan

logger = logging.getLogger(__name__)


async def run_security_scan(
    db: AsyncSession,
    entity_id: uuid.UUID,
    *,
    force: bool = False,
) -> FrameworkSecurityScan | None:
    """Run a security scan for an entity's source repo.

    Args:
        db: Database session
        entity_id: Entity to scan
        force: If True, re-scan even if a recent scan exists

    Returns:
        FrameworkSecurityScan record, or None if no scannable source.
    """
    entity = await db.get(Entity, entity_id)
    if not entity or not entity.is_active:
        return None

    # Need a GitHub source URL to scan
    repo_full_name = _extract_github_repo(entity.source_url)
    if not repo_full_name:
        logger.debug("Entity %s has no GitHub source URL, skipping scan", entity_id)
        return None

    # Check for recent scan (skip if <24h old and not forced)
    if not force:
        existing = await db.execute(
            select(FrameworkSecurityScan)
            .where(FrameworkSecurityScan.entity_id == entity_id)
            .order_by(FrameworkSecurityScan.scanned_at.desc())
            .limit(1)
        )
        latest = existing.scalar_one_or_none()
        if latest:
            age_hours = (
                datetime.now(timezone.utc) - latest.scanned_at
            ).total_seconds() / 3600
            if age_hours < 24:
                logger.debug(
                    "Entity %s scanned %.1fh ago, skipping", entity_id, age_hours,
                )
                return latest

    # Run the scan
    token = settings.github_outreach_token or settings.github_token
    try:
        from src.scanner.scan import scan_repo

        result = await scan_repo(
            full_name=repo_full_name,
            stars=0,
            description=entity.bio_markdown or "",
            framework=entity.framework_source or "",
            token=token,
        )
    except Exception:
        logger.exception("Security scan failed for %s", repo_full_name)
        return None

    if result.error:
        logger.warning("Scan error for %s: %s", repo_full_name, result.error)
        # Still store the result so we don't retry immediately
        scan_record = FrameworkSecurityScan(
            id=uuid.uuid4(),
            entity_id=entity_id,
            framework=entity.framework_source or "unknown",
            scan_result="error",
            vulnerabilities={"error": result.error},
        )
        db.add(scan_record)
        await db.flush()
        return scan_record

    # Determine overall result
    if result.critical_count > 0:
        scan_result = "critical"
    elif result.high_count > 0:
        scan_result = "warnings"
    else:
        scan_result = "clean"

    # Build structured vulnerabilities
    categories: dict[str, int] = {}
    for f in result.findings:
        categories[f.category] = categories.get(f.category, 0) + 1

    vulns = {
        "trust_score": result.trust_score,
        "files_scanned": result.files_scanned,
        "primary_language": result.primary_language,
        "critical_count": result.critical_count,
        "high_count": result.high_count,
        "medium_count": result.medium_count,
        "total_findings": len(result.findings),
        "categories": categories,
        "positive_signals": list(set(result.positive_signals)),
        "has_readme": result.has_readme,
        "has_license": result.has_license,
        "has_tests": result.has_tests,
        "findings": [
            {
                "category": f.category,
                "name": f.name,
                "severity": f.severity,
                "file_path": f.file_path,
                "line_number": f.line_number,
            }
            for f in result.findings[:100]  # Cap at 100 for DB storage
        ],
    }

    scan_record = FrameworkSecurityScan(
        id=uuid.uuid4(),
        entity_id=entity_id,
        framework=entity.framework_source or "unknown",
        scan_result=scan_result,
        vulnerabilities=vulns,
    )
    db.add(scan_record)
    await db.flush()

    logger.info(
        "Security scan complete for %s: %s (score=%d, findings=%d)",
        repo_full_name, scan_result, result.trust_score, len(result.findings),
    )

    return scan_record


async def get_latest_scan(
    db: AsyncSession,
    entity_id: uuid.UUID,
) -> FrameworkSecurityScan | None:
    """Get the most recent scan for an entity."""
    result = await db.execute(
        select(FrameworkSecurityScan)
        .where(FrameworkSecurityScan.entity_id == entity_id)
        .order_by(FrameworkSecurityScan.scanned_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def rescan_all_agents(db: AsyncSession, limit: int = 50) -> int:
    """Re-scan all agents with GitHub source URLs.

    Used by the scheduler for weekly re-scans. Skips entities
    scanned in the last 7 days.
    """
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    # Find agents with GitHub source URLs that haven't been scanned recently
    # Subquery: latest scan per entity
    latest_scans = (
        select(
            FrameworkSecurityScan.entity_id,
            func.max(FrameworkSecurityScan.scanned_at).label("last_scan"),
        )
        .group_by(FrameworkSecurityScan.entity_id)
        .subquery()
    )

    query = (
        select(Entity.id)
        .select_from(
            outerjoin(Entity, latest_scans, Entity.id == latest_scans.c.entity_id)
        )
        .where(
            Entity.is_active.is_(True),
            Entity.source_url.isnot(None),
            Entity.source_url.like("%github.com%"),
        )
        .where(
            (latest_scans.c.last_scan.is_(None)) | (latest_scans.c.last_scan < cutoff)
        )
        .limit(limit)
    )

    result = await db.execute(query)
    entity_ids = [row[0] for row in result.all()]

    scanned = 0
    for eid in entity_ids:
        scan = await run_security_scan(db, eid, force=True)
        if scan:
            scanned += 1
        await db.commit()

    logger.info("Re-scanned %d/%d agents", scanned, len(entity_ids))
    return scanned


def _extract_github_repo(source_url: str | None) -> str | None:
    """Extract 'owner/repo' from a GitHub URL."""
    if not source_url:
        return None
    url = source_url.rstrip("/")
    if "github.com" not in url:
        return None
    # Handle https://github.com/owner/repo and git@github.com:owner/repo.git
    parts = url.split("github.com")[-1]
    parts = parts.lstrip(":/").rstrip(".git")
    segments = parts.split("/")
    if len(segments) >= 2:
        return f"{segments[0]}/{segments[1]}"
    return None
