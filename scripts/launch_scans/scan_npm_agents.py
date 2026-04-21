"""Discover + scan npm packages in the agent-framework ecosystem.

Query terms target agent frameworks and MCP client libraries. We sort by
popularity (weekly downloads) so the top N most-used packages surface first —
those are the high-leverage targets for the launch litepaper.

Dry-run (default): searches npm and writes target list.
Run mode (--run): pulls each package tarball and scans it.

Usage:
    python3 scripts/launch_scans/scan_npm_agents.py           # dry run
    python3 scripts/launch_scans/scan_npm_agents.py --run     # actually scan
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import _common  # noqa: E402

SEARCH_URL = "https://registry.npmjs.org/-/v1/search"
SEARCH_TERMS = [
    "mcp server",
    "agent framework",
    "langchain",
    "crewai",
    "autogen",
    "@modelcontextprotocol",
    "ai agent tool",
    "x402 payment",
]
PACKAGE_CAP_PER_TERM = 60   # npm returns up to 250/call; cap per term to avoid noise
TARGETS_PATH = _common.DATA_DIR / "npm-agents-targets.json"
RESULTS_PATH = _common.DATA_DIR / "npm-agents-results.json"
PROGRESS_PATH = _common.DATA_DIR / "npm-agents-progress.json"


def discover() -> list[dict]:
    import httpx

    seen: dict[str, dict] = {}
    policy = _common.RateLimitPolicy("npm")

    with httpx.Client(timeout=30.0) as client:
        for term in SEARCH_TERMS:
            print(f"[npm] searching: {term!r}")
            params = {
                "text": term,
                "size": PACKAGE_CAP_PER_TERM,
                "popularity": 1.0,
            }
            r = client.get(SEARCH_URL, params=params)
            r.raise_for_status()
            data = r.json()
            for obj in data.get("objects", []):
                pkg = obj.get("package", {})
                name = pkg.get("name")
                if not name or name in seen:
                    continue
                seen[name] = {
                    "name": name,
                    "version": pkg.get("version"),
                    "description": pkg.get("description", ""),
                    "repository_url": (pkg.get("links") or {}).get("repository"),
                    "homepage": (pkg.get("links") or {}).get("homepage"),
                    "npm_url": f"https://www.npmjs.com/package/{name}",
                    "publisher": (pkg.get("publisher") or {}).get("username"),
                    "search_term": term,
                }
            policy.wait()
    return list(seen.values())


def scan_one(target: dict) -> dict:
    """Scan the package's linked repo, falling back to skipping if no repo."""
    import asyncio

    from src.scanner.scan import scan_repo  # noqa: WPS433

    repo_url = target.get("repository_url")
    if not repo_url:
        return {"name": target["name"], "skipped": "no_repository_url"}
    try:
        result = asyncio.run(scan_repo(repo_url))
        return {
            "name": target["name"],
            "repository_url": repo_url,
            "trust_score": result.trust_score,
            "scan_result": result.scan_result,
            "critical": result.critical_count,
            "high": result.high_count,
            "source_type": "npm",
        }
    except Exception as exc:  # noqa: BLE001
        return {"name": target["name"], "repository_url": repo_url, "error": str(exc)}


def main() -> int:
    _common.require_py39()
    _common.ensure_data_dir()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true",
                        help="Actually scan targets (default is dry-run)")
    args = parser.parse_args()

    print("[npm] running searches…")
    targets = discover()
    _common.write_json_atomic(
        TARGETS_PATH, {"targets": targets, "count": len(targets)},
    )

    if not args.run:
        _common.dry_run_banner("npm", len(targets), TARGETS_PATH)
        return 0

    _common.run_banner("npm", len(targets))
    policy = _common.RateLimitPolicy("npm")
    results: list[dict] = []
    progress = _common.read_json(PROGRESS_PATH, default={"done": []})
    done = set(progress.get("done", []))

    for i, target in enumerate(targets):
        if target["name"] in done:
            continue
        print(f"[npm] {i+1}/{len(targets)}: {target['name']}")
        results.append(scan_one(target))
        done.add(target["name"])
        _common.write_json_atomic(PROGRESS_PATH, {"done": sorted(done)})
        _common.write_json_atomic(RESULTS_PATH, {"results": results})
        policy.wait()

    print(f"[npm] complete. {len(results)} scanned -> {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
