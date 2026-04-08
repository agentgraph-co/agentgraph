"""External reputation scoring for linked accounts.

Computes normalized reputation scores (0.0–1.0) from external platform data
(GitHub, npm, PyPI, HuggingFace).
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# Trust weight multipliers by verification status
VERIFICATION_WEIGHTS = {
    "verified_oauth": 1.0,
    "verified_challenge": 0.85,
    "unverified_claim": 0.25,
    "pending": 0.0,
}


def _log_normalize(value: float, cap: float = 1000.0) -> float:
    """Log-scale normalize a value to 0.0–1.0."""
    if value <= 0:
        return 0.0
    return min(math.log(value + 1) / math.log(cap + 1), 1.0)


def compute_github_reputation(
    profile_data: dict, repos_data: list[dict]
) -> tuple[float, dict]:
    """Compute GitHub reputation score from profile and repo data.

    Returns (score, metrics_dict) where score is 0.0–1.0.
    """
    if not profile_data:
        return 0.0, {}

    total_stars = sum(r.get("stargazers_count", 0) for r in repos_data)
    total_forks = sum(r.get("forks_count", 0) for r in repos_data)
    repo_count = len(repos_data)
    followers = profile_data.get("followers", 0)
    public_repos = profile_data.get("public_repos", 0)

    # Account age in days
    created_str = profile_data.get("created_at", "")
    account_age_days = 0
    if created_str:
        try:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            account_age_days = (datetime.now(timezone.utc) - created).days
        except (ValueError, TypeError):
            pass

    # Recent activity: repos updated in last 90 days
    now = datetime.now(timezone.utc)
    recent_repos = 0
    for r in repos_data:
        updated = r.get("updated_at", "")
        if updated:
            try:
                updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                if (now - updated_dt).days <= 90:
                    recent_repos += 1
            except (ValueError, TypeError):
                pass

    recent_ratio = recent_repos / max(repo_count, 1)

    # Component scores (all 0.0–1.0)
    repo_quality = _log_normalize(total_stars, 500)
    community_engagement = _log_normalize(followers + total_forks, 200)
    activity_recency = min(recent_ratio * 1.5, 1.0)
    account_maturity = min(account_age_days / 1095, 1.0)  # 3 years cap
    code_volume = _log_normalize(public_repos, 100)

    # Weighted score
    score = (
        0.20 * repo_quality
        + 0.25 * community_engagement
        + 0.20 * activity_recency
        + 0.15 * account_maturity
        + 0.20 * code_volume
    )

    metrics = {
        "repo_count": repo_count,
        "total_stars": total_stars,
        "total_forks": total_forks,
        "followers": followers,
        "public_repos": public_repos,
        "account_age_days": account_age_days,
        "recent_activity_ratio": round(recent_ratio, 4),
        "component_scores": {
            "repo_quality": round(repo_quality, 4),
            "community_engagement": round(community_engagement, 4),
            "activity_recency": round(activity_recency, 4),
            "account_maturity": round(account_maturity, 4),
            "code_volume": round(code_volume, 4),
        },
    }

    return round(score, 4), metrics


def compute_npm_reputation(package_data: dict) -> tuple[float, dict]:
    """Compute npm package reputation from registry data."""
    if not package_data:
        return 0.0, {}

    downloads = package_data.get("downloads", 0)
    raw_versions = package_data.get("versions", {})
    versions = len(raw_versions) if isinstance(raw_versions, dict) else 0
    maintainers = len(package_data.get("maintainers", []))

    download_score = _log_normalize(downloads, 100000)
    version_score = _log_normalize(versions, 50)
    maintainer_score = min(maintainers / 5, 1.0)

    score = 0.50 * download_score + 0.30 * version_score + 0.20 * maintainer_score

    metrics = {
        "downloads": downloads,
        "versions": versions,
        "maintainers": maintainers,
    }
    return round(score, 4), metrics


def compute_pypi_reputation(package_data: dict) -> tuple[float, dict]:
    """Compute PyPI package reputation from package JSON."""
    if not package_data:
        return 0.0, {}

    info = package_data.get("info", {})
    releases = package_data.get("releases", {})

    release_count = len(releases)
    classifiers = len(info.get("classifiers", []))
    downloads = package_data.get("downloads", 0)  # from pypistats

    release_score = _log_normalize(release_count, 50)
    classifier_score = min(classifiers / 10, 1.0)
    download_score = _log_normalize(downloads, 100000)

    score = 0.40 * download_score + 0.35 * release_score + 0.25 * classifier_score

    metrics = {
        "release_count": release_count,
        "classifiers": classifiers,
        "downloads": downloads,
    }
    return round(score, 4), metrics


def compute_huggingface_reputation(model_data: dict) -> tuple[float, dict]:
    """Compute HuggingFace model/space reputation."""
    if not model_data:
        return 0.0, {}

    downloads = model_data.get("downloads", 0)
    likes = model_data.get("likes", 0)
    has_card = bool(model_data.get("cardData"))

    download_score = _log_normalize(downloads, 50000)
    like_score = _log_normalize(likes, 200)
    card_score = 1.0 if has_card else 0.0

    score = 0.45 * download_score + 0.35 * like_score + 0.20 * card_score

    metrics = {
        "downloads": downloads,
        "likes": likes,
        "has_model_card": has_card,
    }
    return round(score, 4), metrics


def compute_docker_reputation(data: dict) -> tuple[float, dict]:
    """Compute Docker Hub repository reputation.

    Weights: pulls (log-scaled, cap 1M) 60%, stars (log-scaled, cap 500) 25%,
    is_official bonus 15%.
    """
    if not data:
        return 0.0, {}

    pulls = data.get("pull_count", 0)
    stars = data.get("star_count", 0)
    is_official = data.get("is_official", False)

    pull_score = _log_normalize(pulls, 1000000)
    star_score = _log_normalize(stars, 500)
    official_score = 1.0 if is_official else 0.0

    score = 0.60 * pull_score + 0.25 * star_score + 0.15 * official_score

    metrics = {
        "pull_count": pulls,
        "star_count": stars,
        "is_official": is_official,
    }
    return round(score, 4), metrics


def compute_api_health_reputation(data: dict) -> tuple[float, dict]:
    """Compute API health reputation from uptime monitoring data.

    uptime >= 99% = 0.8 base, response < 200ms = +0.2 bonus.
    """
    if not data:
        return 0.0, {}

    uptime_pct = data.get("uptime_pct_30d", 0.0)
    response_ms = data.get("last_response_ms")
    total_checks = data.get("total_checks", 0)

    if total_checks < 3:
        # Not enough data yet
        return 0.0, {"uptime_pct": uptime_pct, "total_checks": total_checks}

    base = 0.0
    if uptime_pct >= 99.0:
        base = 0.8
    elif uptime_pct >= 95.0:
        base = 0.6
    elif uptime_pct >= 90.0:
        base = 0.4
    elif uptime_pct >= 80.0:
        base = 0.2

    bonus = 0.0
    if response_ms is not None and response_ms < 200:
        bonus = 0.2
    elif response_ms is not None and response_ms < 500:
        bonus = 0.1

    score = min(base + bonus, 1.0)

    metrics = {
        "uptime_pct": uptime_pct,
        "last_response_ms": response_ms,
        "total_checks": total_checks,
    }
    return round(score, 4), metrics


async def sync_github_data(db, linked_account) -> None:
    """Fetch latest GitHub data, compute score, update linked_account."""
    from src.api.github_oauth import fetch_github_repos
    from src.crypto import decrypt_token

    access_token = None
    if linked_account.access_token:
        try:
            access_token = decrypt_token(linked_account.access_token)
        except Exception:
            logger.warning("Failed to decrypt GitHub token for %s", linked_account.id)

    profile_data = linked_account.profile_data or {}

    if access_token:
        repos = await fetch_github_repos(access_token)
    else:
        # Fall back to public API for unverified claims
        username = linked_account.provider_username
        if username:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        f"https://api.github.com/users/{username}/repos",
                        params={"per_page": 100, "sort": "updated"},
                        headers={"Accept": "application/vnd.github+json"},
                    )
                    repos = resp.json() if resp.status_code == 200 else []
                    # Also refresh profile data
                    profile_resp = await client.get(
                        f"https://api.github.com/users/{username}",
                        headers={"Accept": "application/vnd.github+json"},
                    )
                    if profile_resp.status_code == 200:
                        profile_data = profile_resp.json()
            except Exception:
                logger.exception("GitHub public API fetch failed")
                repos = []
        else:
            repos = []

    score, metrics = compute_github_reputation(profile_data, repos)

    linked_account.profile_data = profile_data
    linked_account.reputation_data = metrics
    linked_account.reputation_score = score
    linked_account.last_synced_at = datetime.now(timezone.utc)

    await db.flush()


async def sync_provider_data(db, linked_account) -> None:
    """Dispatch to the right sync function based on provider."""
    provider = linked_account.provider
    if provider == "github":
        await sync_github_data(db, linked_account)
    elif provider == "npm":
        await _sync_npm_data(db, linked_account)
    elif provider == "pypi":
        await _sync_pypi_data(db, linked_account)
    elif provider == "huggingface":
        await _sync_huggingface_data(db, linked_account)
    elif provider == "docker":
        await _sync_docker_data(db, linked_account)
    elif provider == "api_health":
        await _sync_api_health_data(db, linked_account)
    else:
        logger.warning("Unknown provider: %s", provider)


async def _sync_npm_data(db, linked_account) -> None:
    """Fetch npm package data and compute score."""
    package_name = linked_account.provider_username
    if not package_name:
        return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Registry metadata
            reg_resp = await client.get(
                f"https://registry.npmjs.org/{package_name}"
            )
            package_data = reg_resp.json() if reg_resp.status_code == 200 else {}

            # Download counts
            dl_resp = await client.get(
                f"https://api.npmjs.org/downloads/point/last-month/{package_name}"
            )
            if dl_resp.status_code == 200:
                package_data["downloads"] = dl_resp.json().get("downloads", 0)
    except Exception:
        logger.exception("npm API fetch failed for %s", package_name)
        return

    score, metrics = compute_npm_reputation(package_data)
    linked_account.profile_data = {
        "name": package_name,
        "description": package_data.get("description", ""),
    }
    linked_account.reputation_data = metrics
    linked_account.reputation_score = score
    linked_account.last_synced_at = datetime.now(timezone.utc)
    await db.flush()


async def _sync_pypi_data(db, linked_account) -> None:
    """Fetch PyPI package data and compute score."""
    package_name = linked_account.provider_username
    if not package_name:
        return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://pypi.org/pypi/{package_name}/json"
            )
            package_data = resp.json() if resp.status_code == 200 else {}
    except Exception:
        logger.exception("PyPI API fetch failed for %s", package_name)
        return

    score, metrics = compute_pypi_reputation(package_data)
    linked_account.profile_data = {
        "name": package_name,
        "summary": package_data.get("info", {}).get("summary", ""),
    }
    linked_account.reputation_data = metrics
    linked_account.reputation_score = score
    linked_account.last_synced_at = datetime.now(timezone.utc)
    await db.flush()


async def _sync_huggingface_data(db, linked_account) -> None:
    """Fetch HuggingFace model data and compute score."""
    model_id = linked_account.provider_username
    if not model_id:
        return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://huggingface.co/api/models/{model_id}"
            )
            model_data = resp.json() if resp.status_code == 200 else {}
    except Exception:
        logger.exception("HuggingFace API fetch failed for %s", model_id)
        return

    score, metrics = compute_huggingface_reputation(model_data)
    linked_account.profile_data = {
        "model_id": model_id,
        "pipeline_tag": model_data.get("pipeline_tag", ""),
    }
    linked_account.reputation_data = metrics
    linked_account.reputation_score = score
    linked_account.last_synced_at = datetime.now(timezone.utc)
    await db.flush()


async def _sync_docker_data(db, linked_account) -> None:
    """Fetch Docker Hub repository data and compute score."""
    identifier = linked_account.provider_username
    if not identifier:
        return

    # identifier is "namespace/name"
    parts = identifier.split("/", 1)
    if len(parts) != 2:
        return
    namespace, name = parts

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://hub.docker.com/v2/repositories/{namespace}/{name}"
            )
            repo_data = resp.json() if resp.status_code == 200 else {}
    except Exception:
        logger.exception("Docker Hub API fetch failed for %s", identifier)
        return

    score, metrics = compute_docker_reputation(repo_data)
    linked_account.profile_data = {
        "namespace": namespace,
        "name": name,
        "description": repo_data.get("description", ""),
    }
    linked_account.reputation_data = metrics
    linked_account.reputation_score = score
    linked_account.last_synced_at = datetime.now(timezone.utc)
    await db.flush()


async def _sync_api_health_data(db, linked_account) -> None:
    """Compute API health reputation from ApiHealthCheck records."""
    from sqlalchemy import select

    from src.models import ApiHealthCheck

    entity_id = linked_account.entity_id
    result = await db.execute(
        select(ApiHealthCheck).where(
            ApiHealthCheck.entity_id == entity_id,
            ApiHealthCheck.is_active.is_(True),
        )
    )
    checks = list(result.scalars().all())
    if not checks:
        return

    # Aggregate across all endpoints
    total_checks = sum(c.total_checks or 0 for c in checks)
    successful = sum(c.successful_checks or 0 for c in checks)
    uptime_pct = (successful / total_checks * 100) if total_checks > 0 else 0.0

    # Average response time from checks that have data
    response_times = [c.last_response_ms for c in checks if c.last_response_ms is not None]
    avg_response_ms = int(sum(response_times) / len(response_times)) if response_times else None

    health_data = {
        "uptime_pct_30d": round(uptime_pct, 2),
        "last_response_ms": avg_response_ms,
        "total_checks": total_checks,
        "endpoint_count": len(checks),
    }

    score, metrics = compute_api_health_reputation(health_data)
    linked_account.reputation_data = metrics
    linked_account.reputation_score = score
    linked_account.last_synced_at = datetime.now(timezone.utc)
    await db.flush()
