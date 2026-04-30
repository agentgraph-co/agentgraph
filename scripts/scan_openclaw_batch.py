"""Auto-discover and batch-scan OpenClaw skills from GitHub.

Discovers 500+ repos via multiple GitHub search strategies, deduplicates
against prior scans, and batch-scans with rate limiting and resume support.

Usage:
    python3 scripts/scan_openclaw_batch.py

Outputs:
    data/openclaw_batch_progress.json — incremental progress (for resume)
    data/openclaw_scan_report_full.json — merged full report
    Prints summary table to stdout
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scanner.scan import ScanResult, scan_repo  # noqa: E402

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EXISTING_REPORT = DATA_DIR / "openclaw_scan_report.json"
PROGRESS_PATH = DATA_DIR / "openclaw_batch_progress.json"
OUTPUT_PATH = DATA_DIR / "openclaw_scan_report_full.json"

# ── Rate limiting ──────────────────────────────────────────────────────────────
PAUSE_BETWEEN_REPOS = 2       # seconds between each repo scan
PAUSE_EVERY_N = 20            # pause longer every N repos
LONG_PAUSE = 10               # seconds for the longer pause
API_RETRY_WAIT = 60           # seconds to wait on 403/429
API_MAX_RETRIES = 3           # max retries per API call


def _load_github_token() -> str | None:
    """Load GITHUB_TOKEN from env or .env.secrets."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token

    secrets_path = PROJECT_ROOT / ".env.secrets"
    if secrets_path.exists():
        for line in secrets_path.read_text().splitlines():
            if line.startswith("GITHUB_TOKEN="):
                candidate = line.split("=", 1)[1].strip().strip("'\"")
                if candidate:
                    return candidate
    return None


def _gh_api_headers(token: str | None) -> dict[str, str]:
    """Build headers for GitHub REST API."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _github_search(
    query: str,
    token: str | None,
    max_pages: int = 5,
) -> list[dict[str, Any]]:
    """Search GitHub repos via REST API with pagination and rate limit handling.

    Returns list of dicts with keys: full_name, description, stargazers_count.
    """
    import httpx

    headers = _gh_api_headers(token)
    repos: list[dict[str, Any]] = []
    page = 1

    async with httpx.AsyncClient(timeout=30) as client:
        while page <= max_pages:
            url = "https://api.github.com/search/repositories"
            params = {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": 100,
                "page": page,
            }

            for attempt in range(API_MAX_RETRIES):
                try:
                    resp = await client.get(url, headers=headers, params=params)
                except Exception as exc:
                    print(f"  [!] Network error on page {page}: {exc}")
                    if attempt < API_MAX_RETRIES - 1:
                        await asyncio.sleep(API_RETRY_WAIT)
                        continue
                    return repos

                if resp.status_code in (403, 429):
                    # Rate limited — check Retry-After or use default
                    retry_after = int(resp.headers.get("Retry-After", API_RETRY_WAIT))
                    print(f"  [!] Rate limited (HTTP {resp.status_code}), waiting {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    continue

                if resp.status_code == 422:
                    # Validation error (e.g., page too deep)
                    return repos

                if resp.status_code != 200:
                    print(f"  [!] GitHub API returned {resp.status_code} on page {page}")
                    return repos

                # Success
                break
            else:
                # Exhausted retries
                return repos

            data = resp.json()
            items = data.get("items", [])
            if not items:
                break

            for item in items:
                repos.append({
                    "full_name": item["full_name"],
                    "description": item.get("description") or "",
                    "stars": item.get("stargazers_count", 0),
                })

            # GitHub search API caps at 1000 results (10 pages of 100)
            total_count = data.get("total_count", 0)
            if page * 100 >= min(total_count, 1000):
                break

            page += 1
            # Small pause between pages to be polite
            await asyncio.sleep(1)

    return repos


async def discover_repos(token: str | None) -> list[dict[str, Any]]:
    """Discover OpenClaw repos using multiple search strategies.

    Returns deduplicated list of repo dicts.
    """
    seen: set[str] = set()
    all_repos: list[dict[str, Any]] = []

    def _add(repos: list[dict[str, Any]], source: str) -> int:
        added = 0
        for r in repos:
            key = r["full_name"].lower()
            if key not in seen:
                seen.add(key)
                r["discovery_source"] = source
                all_repos.append(r)
                added += 1
        return added

    # Strategy 1: topic search
    print("[1/4] Searching repos with topic 'openclaw'...")
    results = await _github_search("topic:openclaw", token, max_pages=10)
    count = _add(results, "topic:openclaw")
    print(f"  Found {len(results)} repos, {count} new")

    # Strategy 2: name/description search for "openclaw skill"
    print("[2/4] Searching repos matching 'openclaw skill'...")
    results = await _github_search("openclaw skill", token, max_pages=5)
    count = _add(results, "search:openclaw-skill")
    print(f"  Found {len(results)} repos, {count} new")

    # Strategy 3: org search
    print("[3/4] Searching repos in 'openclaw' org...")
    results = await _github_search("org:openclaw", token, max_pages=5)
    count = _add(results, "org:openclaw")
    print(f"  Found {len(results)} repos, {count} new")

    # Strategy 4: broader search for "openclaw" in name
    print("[4/4] Searching repos with 'openclaw' in name...")
    results = await _github_search("openclaw in:name", token, max_pages=10)
    count = _add(results, "search:openclaw-in-name")
    print(f"  Found {len(results)} repos, {count} new")

    print(f"\nTotal discovered: {len(all_repos)} unique repos")
    return all_repos


def _load_existing_report() -> dict[str, Any]:
    """Load existing scan report (from hand-picked scan) if present."""
    if EXISTING_REPORT.exists():
        try:
            return json.loads(EXISTING_REPORT.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _load_progress() -> dict[str, Any]:
    """Load batch progress file for resume capability."""
    if PROGRESS_PATH.exists():
        try:
            return json.loads(PROGRESS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"scanned": {}, "errors": {}, "last_index": -1}


def _save_progress(progress: dict[str, Any]) -> None:
    """Save progress after each repo scan."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2))


def _result_to_dict(r: ScanResult) -> dict[str, Any]:
    """Convert ScanResult to serializable dict."""
    return {
        "repo": r.repo,
        "description": r.description,
        "framework": r.framework,
        "stars": r.stars,
        "primary_language": r.primary_language,
        "files_scanned": r.files_scanned,
        "has_readme": r.has_readme,
        "has_license": r.has_license,
        "has_tests": r.has_tests,
        "trust_score": r.trust_score,
        "error": r.error,
        "findings_count": len(r.findings),
        "critical_count": r.critical_count,
        "high_count": r.high_count,
        "medium_count": r.medium_count,
        "positive_signals": list(set(r.positive_signals)),
        "findings": [
            {
                "category": f.category,
                "name": f.name,
                "severity": f.severity,
                "file_path": f.file_path,
                "line_number": f.line_number,
            }
            for f in r.findings
        ],
    }


async def main() -> None:
    token = _load_github_token()
    if not token:
        print("WARNING: No GITHUB_TOKEN found — rate limit is 60 req/hour")
        print("Discovery will be limited. Set GITHUB_TOKEN in .env.secrets.\n")

    # ── Phase 1: Discovery ─────────────────────────────────────────────────
    print("=" * 70)
    print("PHASE 1: REPO DISCOVERY")
    print("=" * 70)

    discovered = await discover_repos(token)

    # ── Phase 2: Deduplicate with existing scans ───────────────────────────
    existing_report = _load_existing_report()
    already_scanned: set[str] = set()
    existing_results: list[dict[str, Any]] = []

    if existing_report:
        for repo_data in existing_report.get("repos", []):
            repo_name = repo_data.get("repo", "").lower()
            already_scanned.add(repo_name)
            existing_results.append(repo_data)
        print(f"\nLoaded {len(already_scanned)} already-scanned repos from {EXISTING_REPORT.name}")

    # Also load any partial progress from previous batch runs
    progress = _load_progress()
    for repo_name in progress.get("scanned", {}):
        already_scanned.add(repo_name.lower())
    if progress["scanned"]:
        print(f"Loaded {len(progress['scanned'])} repos from previous batch progress")

    # Filter to only new repos
    repos_to_scan = [
        r for r in discovered
        if r["full_name"].lower() not in already_scanned
    ]

    print(f"\nRepos to scan (new): {len(repos_to_scan)}")
    print(f"Already scanned:     {len(already_scanned)}")
    print(f"Total after merge:   {len(already_scanned) + len(repos_to_scan)}")

    if not repos_to_scan:
        print("\nNo new repos to scan. Exiting.")
        return

    # ── Phase 3: Batch scan ────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PHASE 2: BATCH SCANNING")
    print("=" * 70)
    print(f"\n{'Repo':<55} {'Score':>5} {'Crit':>4} {'High':>4} {'Med':>4} {'Files':>5} {'Status'}")
    print("-" * 95)

    batch_results: list[dict[str, Any]] = []
    errors = 0
    start = time.time()

    for i, repo in enumerate(repos_to_scan):
        full_name = repo["full_name"]

        result = await scan_repo(
            full_name=full_name,
            description=repo.get("description", ""),
            framework="openclaw",
            stars=repo.get("stars", 0),
            token=token,
        )

        result_dict = _result_to_dict(result)
        result_dict["discovery_source"] = repo.get("discovery_source", "unknown")
        batch_results.append(result_dict)

        if result.error:
            errors += 1
            status = f"ERROR: {result.error[:30]}"
        elif result.critical_count > 0:
            status = "CRITICAL"
        elif result.high_count > 0:
            status = "WARNINGS"
        else:
            status = "CLEAN"

        print(
            f"{result.repo:<55} {result.trust_score:>5} "
            f"{result.critical_count:>4} {result.high_count:>4} "
            f"{result.medium_count:>4} {result.files_scanned:>5} {status}"
        )

        # Save progress after each repo
        progress["scanned"][full_name.lower()] = result_dict
        if result.error:
            progress["errors"][full_name.lower()] = result.error
        progress["last_index"] = i
        _save_progress(progress)

        # Rate limiting
        if i < len(repos_to_scan) - 1:
            if (i + 1) % PAUSE_EVERY_N == 0:
                print(f"\n  [pause] Scanned {i + 1}/{len(repos_to_scan)}, resting {LONG_PAUSE}s...\n")
                await asyncio.sleep(LONG_PAUSE)
            else:
                await asyncio.sleep(PAUSE_BETWEEN_REPOS)

    elapsed = time.time() - start

    # ── Phase 4: Merge results ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PHASE 3: MERGING RESULTS")
    print("=" * 70)

    # Combine existing results + batch results + previous progress results
    merged_repos: dict[str, dict[str, Any]] = {}

    # Add existing report results
    for rd in existing_results:
        key = rd.get("repo", "").lower()
        if key:
            merged_repos[key] = rd

    # Add previous progress results
    for key, rd in progress.get("scanned", {}).items():
        if key not in merged_repos or key.lower() not in {
            k.lower() for k in merged_repos
        }:
            merged_repos[key.lower()] = rd

    # Add current batch results (overwrite if re-scanned)
    for rd in batch_results:
        key = rd.get("repo", "").lower()
        if key:
            merged_repos[key] = rd

    all_results = list(merged_repos.values())
    print(f"Merged {len(all_results)} total repo results")

    # ── Build summary ──────────────────────────────────────────────────────
    scanned = [r for r in all_results if not r.get("error")]
    total_findings = sum(r.get("findings_count", 0) for r in scanned)
    total_critical = sum(r.get("critical_count", 0) for r in scanned)
    total_high = sum(r.get("high_count", 0) for r in scanned)
    total_medium = sum(r.get("medium_count", 0) for r in scanned)
    avg_score = (
        sum(r.get("trust_score", 0) for r in scanned) / len(scanned)
        if scanned
        else 0
    )
    repos_with_critical = sum(1 for r in scanned if r.get("critical_count", 0) > 0)

    # Category breakdown
    categories: dict[str, int] = {}
    for r in scanned:
        for f in r.get("findings", []):
            cat = f.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1

    # Score distribution
    score_dist = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
    for r in scanned:
        s = r.get("trust_score", 0)
        if s <= 20:
            score_dist["0-20"] += 1
        elif s <= 40:
            score_dist["21-40"] += 1
        elif s <= 60:
            score_dist["41-60"] += 1
        elif s <= 80:
            score_dist["61-80"] += 1
        else:
            score_dist["81-100"] += 1

    report = {
        "scan_date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scanner": "AgentGraph Security Scanner",
        "target": "OpenClaw Skills — Auto-Discovered Batch Scan",
        "discovery": {
            "total_discovered": len(discovered),
            "new_scanned_this_run": len(repos_to_scan),
            "from_existing_report": len(existing_results),
            "from_previous_progress": len(progress.get("scanned", {})) - len(batch_results),
        },
        "summary": {
            "total_repos": len(all_results),
            "successfully_scanned": len(scanned),
            "errors": sum(1 for r in all_results if r.get("error")),
            "total_findings": total_findings,
            "critical_findings": total_critical,
            "high_findings": total_high,
            "medium_findings": total_medium,
            "repos_with_critical": repos_with_critical,
            "average_trust_score": round(avg_score, 1),
            "category_breakdown": categories,
            "score_distribution": score_dist,
            "scan_duration_seconds": round(elapsed, 1),
        },
        "repos": sorted(all_results, key=lambda r: r.get("trust_score", 0)),
    }

    # Write merged report
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2))
    print(f"Report written to {OUTPUT_PATH}")

    # ── Print summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("OPENCLAW BATCH SCAN SUMMARY")
    print("=" * 70)
    print(f"Discovery:            {len(discovered)} repos found")
    print(f"New scanned (this run): {len(repos_to_scan)}")
    print(f"Total in report:      {len(all_results)}")
    print(f"Successfully scanned: {len(scanned)}")
    print(f"Total findings:       {total_findings}")
    print(f"  Critical:           {total_critical}")
    print(f"  High:               {total_high}")
    print(f"  Medium:             {total_medium}")
    print(f"Repos with critical:  {repos_with_critical}/{len(scanned)}")
    print(f"Average trust score:  {avg_score:.1f}/100")
    print(f"Scan duration:        {elapsed:.1f}s")
    print(f"\nFull report: {OUTPUT_PATH}")
    print(f"Progress:    {PROGRESS_PATH}")

    if categories:
        print("\nFindings by category:")
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"  {cat:<20} {count}")

    print("\nScore distribution:")
    for bucket, count in score_dist.items():
        bar = "#" * count
        print(f"  {bucket:<8} {count:>3} {bar}")


if __name__ == "__main__":
    asyncio.run(main())
