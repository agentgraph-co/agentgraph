"""Discover + scan MCP servers from the official MCP Registry.

The MCP Registry is the canonical directory of Model Context Protocol servers
that clients like Claude Code and Cursor can install. Scanning all of them gives
us the clearest picture of the agent-tool supply chain.

Dry-run (default): fetches the server list and writes target list.
Run mode (--run): scans each server's source repo via our scanner.

Usage:
    python3 scripts/launch_scans/scan_mcp_registry.py           # dry run
    python3 scripts/launch_scans/scan_mcp_registry.py --run     # actually scan
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import _common  # noqa: E402

REGISTRY_URL = "https://registry.modelcontextprotocol.io/v1/servers"
TARGETS_PATH = _common.DATA_DIR / "mcp-registry-targets.json"
RESULTS_PATH = _common.DATA_DIR / "mcp-registry-results.json"
PROGRESS_PATH = _common.DATA_DIR / "mcp-registry-progress.json"


def discover() -> list[dict]:
    import httpx

    targets: list[dict] = []
    cursor: str | None = None
    policy = _common.RateLimitPolicy("mcp")

    with httpx.Client(timeout=30.0) as client:
        while True:
            params = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            r = client.get(REGISTRY_URL, params=params)
            r.raise_for_status()
            data = r.json()
            servers = data.get("servers") or data.get("data") or []
            for s in servers:
                repo = (
                    s.get("repository") or s.get("repo_url") or s.get("source_url")
                )
                if not repo:
                    continue
                targets.append({
                    "name": s.get("name") or s.get("id"),
                    "repository_url": repo,
                    "description": s.get("description", ""),
                    "publisher": s.get("publisher") or s.get("author"),
                    "version": s.get("version"),
                })
            cursor = (data.get("metadata") or {}).get("next_cursor")
            if not cursor or not servers:
                break
            policy.wait()
    return targets


def scan_one(target: dict) -> dict:
    """Scan the MCP server's source repo via our internal scanner."""
    import asyncio

    from src.scanner.scan import scan_repo  # noqa: WPS433

    repo_url = target["repository_url"]
    try:
        result = asyncio.run(scan_repo(repo_url))
        return {
            "name": target["name"],
            "repository_url": repo_url,
            "trust_score": result.trust_score,
            "scan_result": result.scan_result,
            "critical": result.critical_count,
            "high": result.high_count,
            "framework": "mcp",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": target["name"],
            "repository_url": repo_url,
            "error": str(exc),
        }


def main() -> int:
    _common.require_py39()
    _common.ensure_data_dir()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true",
                        help="Actually scan targets (default is dry-run)")
    args = parser.parse_args()

    print("[mcp] paginating MCP Registry…")
    targets = discover()
    _common.write_json_atomic(
        TARGETS_PATH, {"targets": targets, "count": len(targets)},
    )

    if not args.run:
        _common.dry_run_banner("mcp", len(targets), TARGETS_PATH)
        return 0

    _common.run_banner("mcp", len(targets))
    policy = _common.RateLimitPolicy("mcp")
    results: list[dict] = []
    progress = _common.read_json(PROGRESS_PATH, default={"done": []})
    done = set(progress.get("done", []))

    for i, target in enumerate(targets):
        key = target["repository_url"]
        if key in done:
            continue
        print(f"[mcp] {i+1}/{len(targets)}: {target['name']}")
        results.append(scan_one(target))
        done.add(key)
        _common.write_json_atomic(PROGRESS_PATH, {"done": sorted(done)})
        _common.write_json_atomic(RESULTS_PATH, {"results": results})
        policy.wait()

    print(f"[mcp] complete. {len(results)} scanned -> {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
