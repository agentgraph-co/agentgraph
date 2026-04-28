"""Discover + scan PyPI packages in the agent-framework ecosystem.

PyPI doesn't have a JSON search API like npm does. We use two strategies:
  1. PyPI Simple index + curated seed list (framework bridges, MCP libs)
  2. libraries.io / Google search for "agent" keyword as a fallback

The curated seed is the primary signal — we want framework bridges, not
every agent-adjacent library.

Dry-run (default): expands seeds + keyword searches, writes target list.
Run mode (--run): scans each package's source repo.

Usage:
    python3 scripts/launch_scans/scan_pypi_agents.py           # dry run
    python3 scripts/launch_scans/scan_pypi_agents.py --run     # actually scan
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import _common  # noqa: E402

PYPI_PKG_URL = "https://pypi.org/pypi/{name}/json"

# Curated seed — agent framework + MCP clients + known bridges. Expand as needed.
SEED_PACKAGES = [
    # Framework bridges (ours + upstream)
    "agentgraph-trust",
    "agentgraph-bridge-langchain",
    "agentgraph-bridge-crewai",
    "agentgraph-bridge-autogen",
    "agentgraph-pydantic",
    "agentgraph-agt",
    "open-agent-trust",
    # Major agent frameworks
    "langchain",
    "langgraph",
    "crewai",
    "pyautogen",
    "pydantic-ai",
    "llama-index",
    "haystack-ai",
    "smolagents",
    # MCP ecosystem
    "mcp",
    "mcp-python-sdk",
    "fastmcp",
    # Known bridges/tools
    "magentic",
    "instructor",
    "guidance",
    "outlines",
    "dspy-ai",
    "autogenstudio",
]

TARGETS_PATH = _common.DATA_DIR / "pypi-agents-targets.json"
RESULTS_PATH = _common.DATA_DIR / "pypi-agents-results.json"
PROGRESS_PATH = _common.DATA_DIR / "pypi-agents-progress.json"


def _pypi_metadata(client, name: str) -> dict | None:
    """Return PyPI JSON metadata or None if package not found."""
    r = client.get(PYPI_PKG_URL.format(name=name))
    if r.status_code != 200:
        return None
    return r.json()


def _extract_repo_url(meta: dict) -> str | None:
    info = meta.get("info") or {}
    urls = info.get("project_urls") or {}
    # Try common keys that point at a source repo
    for key in ("Source", "Repository", "GitHub", "Source Code", "Homepage"):
        url = urls.get(key)
        if url and ("github.com" in url or "gitlab.com" in url):
            return url
    home = info.get("home_page")
    if home and ("github.com" in home or "gitlab.com" in home):
        return home
    return None


def discover() -> list[dict]:
    import httpx

    targets: list[dict] = []
    policy = _common.RateLimitPolicy("pypi")

    with httpx.Client(timeout=30.0) as client:
        for name in SEED_PACKAGES:
            meta = _pypi_metadata(client, name)
            if not meta:
                print(f"[pypi] SKIP (not found): {name}")
                policy.wait()
                continue
            info = meta.get("info") or {}
            repo = _extract_repo_url(meta)
            targets.append({
                "name": name,
                "version": info.get("version"),
                "summary": info.get("summary", ""),
                "repository_url": repo,
                "project_urls": info.get("project_urls") or {},
                "author": info.get("author"),
            })
            policy.wait()
    return targets


def scan_one(target: dict) -> dict:
    import asyncio

    from src.scanner.scan import scan_repo  # noqa: WPS433

    repo_url = target.get("repository_url")
    if not repo_url:
        return {"name": target["name"], "skipped": "no_repository_url"}
    full_name = _common.extract_owner_repo(repo_url)
    if not full_name:
        return {"name": target["name"], "repository_url": repo_url, "skipped": "non_github_repo"}
    try:
        token = _common.load_secret("GITHUB_TOKEN")
        result = asyncio.run(scan_repo(full_name, token=token))
        summary = _common.summarize_scan_result(result)
        return {
            "name": target["name"],
            "repository_url": repo_url,
            "full_name": full_name,
            "source_type": "pypi",
            **summary,
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

    print("[pypi] fetching metadata for seed packages…")
    targets = discover()
    _common.write_json_atomic(
        TARGETS_PATH, {"targets": targets, "count": len(targets)},
    )

    if not args.run:
        _common.dry_run_banner("pypi", len(targets), TARGETS_PATH)
        return 0

    _common.run_banner("pypi", len(targets))
    policy = _common.RateLimitPolicy("pypi")
    results: list[dict] = []
    progress = _common.read_json(PROGRESS_PATH, default={"done": []})
    done = set(progress.get("done", []))

    for i, target in enumerate(targets):
        if target["name"] in done:
            continue
        print(f"[pypi] {i+1}/{len(targets)}: {target['name']}")
        results.append(scan_one(target))
        done.add(target["name"])
        _common.write_json_atomic(PROGRESS_PATH, {"done": sorted(done)})
        _common.write_json_atomic(RESULTS_PATH, {"results": results})
        policy.wait()

    print(f"[pypi] complete. {len(results)} scanned -> {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
