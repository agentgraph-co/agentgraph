"""Discover + scan x402 Bazaar listed endpoints.

x402 is Coinbase's agent-to-agent USDC micropayment protocol on Base.
The Bazaar is the public directory of endpoints that accept x402 payments.

Dry-run (default): fetches the listings and writes target list.
Run mode (--run): scans each endpoint's HTTP surface via our scanner API.

Usage:
    python3 scripts/launch-scans/scan_x402.py           # dry run
    python3 scripts/launch-scans/scan_x402.py --run     # actually scan

Rate-limit posture:
    The Bazaar API has no published limit. We pace 1 req/s and long-pause
    every 25 calls. If Coinbase posts a limit before launch day, update
    _common.py RateLimitPolicy.POLICIES['x402'].
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add package dir so _common is importable regardless of cwd
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common  # noqa: E402

BAZAAR_LISTINGS_URL = "https://bazaar.x402.org/api/v1/listings"
TARGETS_PATH = _common.DATA_DIR / "x402-targets.json"
RESULTS_PATH = _common.DATA_DIR / "x402-results.json"
PROGRESS_PATH = _common.DATA_DIR / "x402-progress.json"


def discover() -> list[dict]:
    """Fetch the Bazaar listings index. Does NOT hit per-endpoint URLs."""
    import httpx

    with httpx.Client(timeout=30.0) as client:
        r = client.get(BAZAAR_LISTINGS_URL)
        r.raise_for_status()
        data = r.json()

    # Shape is in flux — Bazaar has changed response structure before.
    # Normalize to a flat list of {name, endpoint_url, description, price_usdc}.
    listings = data.get("listings") or data.get("items") or data.get("data") or []
    targets = []
    for item in listings:
        endpoint = item.get("endpoint") or item.get("url") or item.get("resource")
        if not endpoint:
            continue
        targets.append({
            "name": item.get("name") or item.get("title") or endpoint,
            "endpoint_url": endpoint,
            "description": item.get("description", ""),
            "price_usdc": item.get("price") or item.get("price_usdc"),
            "operator": item.get("operator") or item.get("maintainer"),
        })
    return targets


def scan_one(target: dict) -> dict:
    """Scan a single x402 endpoint via our public scan API.

    Currently a thin wrapper — full scanner integration will land in
    src/scanner/scan_x402.py before we flip this to --run.
    """
    import httpx

    url = target["endpoint_url"]
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            head = client.head(url)
            probe = client.get(url, headers={"Accept": "application/json"})
        return {
            "endpoint_url": url,
            "http_status": probe.status_code,
            "head_status": head.status_code,
            "has_x402_header": "x-402-payment" in {
                k.lower() for k in probe.headers
            } or "www-authenticate" in {k.lower() for k in probe.headers},
            "content_length": int(probe.headers.get("content-length", 0) or 0),
            "content_type": probe.headers.get("content-type", ""),
        }
    except Exception as exc:  # noqa: BLE001
        return {"endpoint_url": url, "error": str(exc)}


def main() -> int:
    _common.require_py39()
    _common.ensure_data_dir()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true",
                        help="Actually scan targets (default is dry-run)")
    args = parser.parse_args()

    print("[x402] fetching Bazaar listings…")
    targets = discover()
    _common.write_json_atomic(TARGETS_PATH, {"targets": targets, "count": len(targets)})

    if not args.run:
        _common.dry_run_banner("x402", len(targets), TARGETS_PATH)
        return 0

    _common.run_banner("x402", len(targets))
    policy = _common.RateLimitPolicy("x402")
    results: list[dict] = []
    progress = _common.read_json(PROGRESS_PATH, default={"done": []})
    done = set(progress.get("done", []))

    for i, target in enumerate(targets):
        key = target["endpoint_url"]
        if key in done:
            continue
        print(f"[x402] {i+1}/{len(targets)}: {key}")
        results.append(scan_one(target))
        done.add(key)
        _common.write_json_atomic(PROGRESS_PATH, {"done": sorted(done)})
        _common.write_json_atomic(RESULTS_PATH, {"results": results})
        policy.wait()

    print(f"[x402] complete. {len(results)} scanned -> {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
