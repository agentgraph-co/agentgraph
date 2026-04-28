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

BAZAAR_LISTINGS_URL = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"
TARGETS_PATH = _common.DATA_DIR / "x402-targets.json"
RESULTS_PATH = _common.DATA_DIR / "x402-results.json"
PROGRESS_PATH = _common.DATA_DIR / "x402-progress.json"


def discover() -> list[dict]:
    """Fetch the Bazaar listings via CDP discovery API. Paginated, no auth."""
    import httpx

    targets: list[dict] = []
    offset = 0
    page_size = 1000  # max per CDP docs
    seen: set[str] = set()
    policy = _common.RateLimitPolicy("x402")

    with httpx.Client(timeout=30.0) as client:
        while True:
            r = client.get(
                BAZAAR_LISTINGS_URL,
                params={"type": "http", "limit": page_size, "offset": offset},
            )
            r.raise_for_status()
            data = r.json()
            items = data.get("items") or []
            for item in items:
                endpoint = item.get("resource") or item.get("endpoint") or item.get("url")
                if not endpoint or endpoint in seen:
                    continue
                seen.add(endpoint)
                meta = item.get("metadata") or {}
                accepts = item.get("accepts") or []
                # Operator: closest signal is the payTo wallet on the first accept option
                pay_to = None
                if accepts and isinstance(accepts[0], dict):
                    pay_to = accepts[0].get("payTo") or accepts[0].get("pay_to")
                targets.append({
                    "name": meta.get("description", endpoint).split(".")[0][:80] or endpoint,
                    "endpoint_url": endpoint,
                    "description": meta.get("description", ""),
                    "input_schema": meta.get("input"),
                    "output_schema": meta.get("output"),
                    "accepts": accepts,
                    "pay_to": pay_to,
                    "last_updated": item.get("lastUpdated"),
                    "x402_version": item.get("x402Version"),
                })
            pagination = data.get("pagination") or {}
            total = pagination.get("total")
            offset += len(items)
            if not items or (total is not None and offset >= total):
                break
            policy.wait()
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
