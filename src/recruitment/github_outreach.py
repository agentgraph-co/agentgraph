"""GitHub issue creation for operator recruitment outreach.

Creates templated issues on discovered repos, respecting rate limits
and ensuring one-issue-per-repo dedup.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models import RecruitmentProspect
from src.recruitment.templates import render_template

logger = logging.getLogger(__name__)

_TIMEOUT = 15  # seconds


def _github_headers() -> dict[str, str]:
    """Build GitHub API headers for issue creation."""
    headers = {
        "Accept": "application/vnd.github+json",
    }
    token = settings.github_outreach_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _pick_template(prospect: RecruitmentProspect) -> str:
    """Pick the best template key for a prospect."""
    fw = (prospect.framework_detected or "").lower()
    if "mcp" in fw:
        return "mcp_server"
    if fw in ("langchain", "crewai", "autogen", "semantic_kernel"):
        return "ai_agent"
    return "ai_tool"


async def _create_issue(
    owner: str, repo: str, title: str, body: str,
) -> str | None:
    """Create a GitHub issue and return the issue URL, or None on failure."""
    token = settings.github_outreach_token
    if not token:
        logger.error("GITHUB_OUTREACH_TOKEN not configured — skipping outreach")
        return None

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        url = f"https://api.github.com/repos/{owner}/{repo}/issues"
        resp = await client.post(
            url,
            headers=_github_headers(),
            json={"title": title, "body": body},
        )

        if resp.status_code == 201:
            issue_url = resp.json().get("html_url", "")
            logger.info("Created issue on %s/%s: %s", owner, repo, issue_url)
            return issue_url

        if resp.status_code == 403:
            logger.warning(
                "GitHub 403 for %s/%s: %s", owner, repo, resp.text[:200],
            )
            return "403"

        if resp.status_code == 410:
            # Issues disabled on this repo
            logger.info("Issues disabled on %s/%s — skipping", owner, repo)
            return "skip"

        if resp.status_code == 404:
            logger.info("Repo %s/%s not found — may be deleted", owner, repo)
            return "skip"

        logger.warning(
            "GitHub issue creation returned %d for %s/%s: %s",
            resp.status_code, owner, repo, resp.text[:200],
        )
        return None


async def run_outreach_cycle(db: AsyncSession) -> int:
    """Send outreach to up to RECRUITMENT_DAILY_LIMIT discovered prospects.

    Returns the number of issues successfully created.
    """
    limit = settings.recruitment_daily_limit

    # Get discovered prospects that haven't been contacted
    prospects = (
        await db.scalars(
            select(RecruitmentProspect)
            .where(RecruitmentProspect.status == "discovered")
            .order_by(RecruitmentProspect.stars.desc())
            .limit(limit)
        )
    ).all()

    if not prospects:
        return 0

    sent = 0
    for prospect in prospects:
        # Cross-channel dedup: check if same owner already contacted
        already_contacted = await db.scalar(
            select(RecruitmentProspect.id).where(
                RecruitmentProspect.owner_login == prospect.owner_login,
                RecruitmentProspect.status.in_(["contacted", "visited", "onboarded"]),
            ).limit(1)
        )
        if already_contacted:
            prospect.status = "skipped"
            prospect.notes = "Owner already contacted via another repo"
            continue

        template_key = _pick_template(prospect)
        repo_name = prospect.repo_name or prospect.platform_id.split("/")[-1]

        try:
            title, body = render_template(
                template_key,
                repo_name=repo_name,
                stars=prospect.stars or 0,
            )
        except KeyError:
            logger.warning("Unknown template %s for %s", template_key, prospect.platform_id)
            prospect.status = "skipped"
            continue

        owner = prospect.owner_login
        issue_url = await _create_issue(owner, repo_name, title, body)

        if issue_url and issue_url.startswith("http"):
            prospect.status = "contacted"
            prospect.contacted_at = datetime.now(timezone.utc)
            prospect.issue_url = issue_url
            sent += 1
        elif issue_url == "skip":
            # 410 (issues disabled) or 404 (repo gone) — permanent skip
            prospect.status = "skipped"
            prospect.notes = "Issues disabled or repo not found"
        elif issue_url == "403":
            # Could be repo-level restriction or rate limit — skip
            prospect.status = "skipped"
            prospect.notes = "GitHub 403 — issues may be restricted on this repo"
        # None = token missing, leave as discovered for retry

    await db.flush()
    return sent
