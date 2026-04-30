#!/usr/bin/env bash
# Weekly re-scan: re-runs the four launch-scan datasets (x402 / MCP /
# npm / PyPI) and invalidates the /scans catalog in-memory cache.
#
# Press story: "we publish the trail, not a frozen PDF" — only works
# if the trail keeps growing. This script is the cadence anchor.
#
# Crontab (EC2): every Sunday at 02:00 UTC
#   0 2 * * 0 cd /home/ec2-user/agentgraph && bash scripts/weekly_rescan.sh >> data/launch-scans/weekly.log 2>&1
#
# Manual run:
#   bash scripts/weekly_rescan.sh
#
# Each scan respects rate limits and pacing per the script's own
# config. The MCP scan is the slowest (~30-60 min); x402 next (~20
# min). npm + PyPI under 5 min each. Total ~60-90 min.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

LOG_TS() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { printf '[%s] %s\n' "$(LOG_TS)" "$*"; }

log "weekly_rescan: start"

# Each scan is independent; failure of one shouldn't kill the others.
# Rate-limit pacing is per-script.
for SCRIPT in scan_x402.py scan_mcp_registry.py scan_npm_agents.py scan_pypi_agents.py; do
  log "running $SCRIPT"
  if python3 "scripts/launch_scans/$SCRIPT"; then
    log "$SCRIPT OK"
  else
    log "$SCRIPT FAILED (exit $?), continuing with next surface"
  fi
done

# Invalidate the /scans catalog in-memory cache so next request rebuilds.
# Localhost-only endpoint; ignore failure (catalog will eventually rebuild
# on the 1-hour TTL anyway).
log "refreshing catalog cache"
curl -fsS -X POST "http://localhost:8000/api/v1/public/scan-catalog/refresh" \
  -H "Content-Type: application/json" --max-time 30 \
  || log "catalog refresh failed (cache will rebuild on next request)"

log "weekly_rescan: done"
