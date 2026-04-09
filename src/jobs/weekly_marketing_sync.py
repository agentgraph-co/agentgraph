"""Weekly marketing sync — Friday job that generates a progress digest.

Runs every Friday. Aggregates the week's activity (commits, scans,
partner replies, new features) into a digest that the marketing bot
uses to plan the following week's content.

Job 22 in the scheduler.
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DIGEST_PATH = Path("data/marketing_weekly_digest.json")


async def generate_weekly_digest() -> dict:
    """Generate a weekly progress digest for the marketing bot."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    digest: dict = {
        "generated_at": now.isoformat(),
        "period_start": week_ago.isoformat(),
        "period_end": now.isoformat(),
        "commits": [],
        "scan_stats": {},
        "partner_activity": [],
        "new_features": [],
        "pypi_packages": [],
        "social_posts": [],
        "key_metrics": {},
    }

    # 1. Recent commits (last 7 days)
    try:
        result = subprocess.run(
            ["git", "log", "--since=7 days ago", "--oneline", "--no-merges"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            commits = [
                line.strip() for line in result.stdout.strip().split("\n")
                if line.strip()
            ]
            digest["commits"] = commits[:20]  # Cap at 20
            digest["key_metrics"]["commits_this_week"] = len(commits)
    except Exception:
        logger.warning("Could not fetch git log for weekly digest")

    # 2. Scan stats (if report exists)
    scan_report = Path("data/openclaw_scan_report_full.json")
    if scan_report.exists():
        try:
            data = json.loads(scan_report.read_text())
            summary = data.get("summary", {})
            digest["scan_stats"] = {
                "repos_scanned": summary.get("successfully_scanned", 0),
                "total_findings": summary.get("total_findings", 0),
                "critical": summary.get("critical_findings", 0),
                "average_score": summary.get("average_trust_score", 0),
            }
        except Exception:
            pass

    # 3. Gateway metrics (from Redis)
    try:
        from src.api.trust_gateway_router import _get_metric
        digest["key_metrics"]["gateway_checks"] = await _get_metric("checks:total")
        digest["key_metrics"]["gateway_allowed"] = await _get_metric("decisions:allowed")
        digest["key_metrics"]["gateway_blocked"] = await _get_metric("decisions:blocked")
    except Exception:
        pass

    # 4. Reply guy stats
    try:
        from src.database import async_session
        from src.models import ReplyOpportunity
        import sqlalchemy as sa

        async with async_session() as db:
            result = await db.execute(
                sa.select(sa.func.count()).where(
                    ReplyOpportunity.status == "posted",
                    ReplyOpportunity.posted_at >= week_ago,
                )
            )
            digest["key_metrics"]["replies_posted_this_week"] = result.scalar() or 0
    except Exception:
        pass

    # 5. Summarize for content engine
    commit_count = digest["key_metrics"].get("commits_this_week", 0)
    scan_count = digest["scan_stats"].get("repos_scanned", 0)
    findings = digest["scan_stats"].get("total_findings", 0)

    digest["content_suggestions"] = []
    if scan_count > 0:
        digest["content_suggestions"].append(
            f"Security scan data: {scan_count} repos scanned, "
            f"{findings} findings. Use in posts."
        )
    if commit_count > 10:
        digest["content_suggestions"].append(
            f"High development velocity: {commit_count} commits this week."
        )

    # Write digest
    DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_PATH.write_text(json.dumps(digest, indent=2))
    logger.info("Weekly marketing digest generated: %s", DIGEST_PATH)

    return digest
