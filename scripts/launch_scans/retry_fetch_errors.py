"""Retry the GitHub-fetch-errored scans from npm + MCP runs with extended pacing.

The Apr 26 burst hit GitHub's rate limit on a chunk of repos despite a token.
This runner re-tries each errored target with a longer pause (3s/req, 30s long
pause every 20 reqs) and merges the new results back into the original
results files.

Usage:
    python3 scripts/launch_scans/retry_fetch_errors.py --source npm
    python3 scripts/launch_scans/retry_fetch_errors.py --source mcp
    python3 scripts/launch_scans/retry_fetch_errors.py --source both
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import _common  # noqa: E402

PLAN = {
    "npm": {
        "retry_targets": _common.DATA_DIR / "npm-agents-retry-targets.json",
        "results": _common.DATA_DIR / "npm-agents-results.json",
        "framework": "",
    },
    "mcp": {
        "retry_targets": _common.DATA_DIR / "mcp-registry-retry-targets.json",
        "results": _common.DATA_DIR / "mcp-registry-results.json",
        "framework": "mcp",
    },
}

# Slower than the original POLICIES — these are the GitHub-rate-limit retries
RETRY_PAUSE_S = 3.0
RETRY_LONG_PAUSE_EVERY = 20
RETRY_LONG_PAUSE_S = 30.0


def _scan_one(full_name: str, framework: str, token: str | None) -> dict:
    from src.scanner.scan import scan_repo  # noqa: WPS433
    try:
        result = asyncio.run(scan_repo(full_name, framework=framework, token=token))
        return _common.summarize_scan_result(result)
    except Exception as exc:  # noqa: BLE001
        return {"scan_error": str(exc)}


def retry_source(source: str) -> None:
    cfg = PLAN[source]
    retry_path = cfg["retry_targets"]
    results_path = cfg["results"]
    framework = cfg["framework"]

    targets = json.load(open(retry_path))["targets"]
    print(f"[{source}] retrying {len(targets)} fetch-errored repos")

    existing = json.load(open(results_path))
    by_name = {r["name"]: i for i, r in enumerate(existing["results"])}
    token = _common.load_secret("GITHUB_TOKEN")

    fixed = 0
    still_failing = 0
    count = 0
    for tgt in targets:
        name = tgt["name"]
        full_name = tgt["full_name"]
        count += 1
        print(f"[{source}] {count}/{len(targets)}: {name} ({full_name})")
        summary = _scan_one(full_name, framework, token)
        if summary.get("scan_error") is None and "trust_score" in summary:
            fixed += 1
            print(f"    ✓ trust={summary['trust_score']} crit={summary.get('critical', 0)} high={summary.get('high', 0)}")
        else:
            still_failing += 1
            err = summary.get("scan_error", "unknown")
            print(f"    ✗ {err[:100]}")

        # Merge into existing results
        if name in by_name:
            row = existing["results"][by_name[name]]
            row.update({"full_name": full_name, "repository_url": tgt.get("repository_url"), **summary})
            if "error" in row and "trust_score" in summary:
                # Old top-level error key — clear it; we replaced with a successful summary
                row.pop("error", None)
        else:
            existing["results"].append({"name": name, "repository_url": tgt.get("repository_url"), "full_name": full_name, **summary})
            by_name[name] = len(existing["results"]) - 1

        # Persist incrementally
        with open(results_path, "w") as f:
            json.dump(existing, f, indent=2)

        if count % RETRY_LONG_PAUSE_EVERY == 0:
            time.sleep(RETRY_LONG_PAUSE_S)
        else:
            time.sleep(RETRY_PAUSE_S)

    print(f"\n[{source}] complete. fixed={fixed} still_failing={still_failing}")


def main() -> int:
    _common.require_py39()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["npm", "mcp", "both"], default="both")
    args = parser.parse_args()
    sources = ["npm", "mcp"] if args.source == "both" else [args.source]
    for s in sources:
        retry_source(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
